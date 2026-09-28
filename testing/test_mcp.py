"""The MCP endpoint: the tools, the op checks, and the HTTP transport.

Tools are driven through ``handlers`` rather than over a socket, since a
background Blender runs no timers and so never reaches the main-thread hop.
The transport is tested separately, on the methods that answer without touching
Blender data.
"""

import json
import urllib.error
import urllib.request

from ..mcp import activity, describe, handlers, server, tools
from ..mcp.handlers import ToolError
from ..mcp.ops import OpError, apply_ops
from .utils import Sketch2dTestCase


class TestMcpTools(Sketch2dTestCase):
    def _edit(self, ops, sketch=None):
        return handlers.edit_sketch(
            self.context, {"sketch": (sketch or self.sketch).name, "ops": ops}
        )

    def test_describe_scene_lists_the_sketch(self):
        data = describe.scene_data(self.context)
        names = [s["name"] for s in data["sketches"]]
        self.assertIn(self.sketch.name, names)
        self.assertIn("scale_length", data["units"])

    def test_describe_sketch_reports_geometry_by_name(self):
        point = self.add_point((1.0, 2.0))
        point.name = "corner"
        data = describe.sketch_data(self.sketch)
        entities = {e["name"]: e for e in data["entities"]}
        self.assertIn("corner", entities)
        self.assertEqual(entities["corner"]["kind"], "point")
        self.assertEqual(entities["corner"]["co"], [1.0, 2.0])

    def test_edit_builds_geometry_and_names_it(self):
        result = self._edit(
            [
                {"op": "point", "name": "a", "co": [0.0, 0.0]},
                {"op": "point", "name": "b", "co": [5.0, 0.0]},
                {"op": "line", "name": "base", "p1": "a", "p2": "b"},
            ]
        )
        self.assertEqual(result["applied"]["entities_added"], 3)
        names = {e["name"] for e in result["entities"]}
        self.assertLessEqual({"a", "b", "base"}, names)

    def test_inline_coordinates_create_their_points(self):
        result = self._edit(
            [{"op": "line", "name": "diag", "p1": [0.0, 0.0], "p2": [3.0, 4.0]}]
        )
        line = next(e for e in result["entities"] if e["name"] == "diag")
        self.assertAlmostEqual(line["length"], 5.0, places=5)
        # The two inline points are entities too, and counted as such.
        self.assertEqual(result["applied"]["entities_added"], 3)

    def test_a_dimension_drives_the_geometry(self):
        self._edit(
            [
                {"op": "point", "name": "a", "co": [0.0, 0.0], "fixed": True},
                {"op": "point", "name": "b", "co": [5.0, 0.0]},
                {"op": "line", "name": "base", "p1": "a", "p2": "b"},
                {"op": "constrain", "type": "horizontal", "refs": ["base"]},
                {
                    "op": "constrain",
                    "type": "distance",
                    "refs": ["a", "b"],
                    "value": 12.0,
                },
            ]
        )
        data = describe.sketch_data(self.sketch)
        line = next(e for e in data["entities"] if e["name"] == "base")
        self.assertAlmostEqual(line["length"], 12.0, places=4)

    def test_an_omitted_value_measures_the_geometry(self):
        result = self._edit(
            [
                {"op": "point", "name": "a", "co": [0.0, 0.0]},
                {"op": "point", "name": "b", "co": [7.0, 0.0]},
                {"op": "line", "name": "base", "p1": "a", "p2": "b"},
                {"op": "constrain", "type": "distance", "refs": ["a", "b"]},
            ]
        )
        distance = next(c for c in result["constraints"] if c["type"] == "DISTANCE")
        self.assertAlmostEqual(distance["value"], 7.0, places=4)

    def test_constraints_reduce_the_degrees_of_freedom(self):
        loose = self._edit(
            [
                {"op": "point", "name": "a", "co": [0.0, 0.0]},
                {"op": "point", "name": "b", "co": [5.0, 1.0]},
                {"op": "line", "name": "base", "p1": "a", "p2": "b"},
            ]
        )
        tightened = self._edit(
            [{"op": "constrain", "type": "horizontal", "refs": ["base"]}]
        )
        self.assertLess(tightened["dof"], loose["dof"])

    def test_deleting_a_point_takes_its_line_and_constraints(self):
        self._edit(
            [
                {"op": "point", "name": "a", "co": [0.0, 0.0]},
                {"op": "point", "name": "b", "co": [5.0, 0.0]},
                {"op": "line", "name": "base", "p1": "a", "p2": "b"},
                {"op": "constrain", "type": "horizontal", "refs": ["base"]},
            ]
        )
        result = self._edit([{"op": "delete", "target": "a"}])
        names = {e["name"] for e in result["entities"]}
        self.assertNotIn("a", names)
        self.assertNotIn("base", names)
        self.assertEqual(result["constraints"], [])

    def test_set_value_changes_an_existing_dimension(self):
        self._edit(
            [
                {"op": "point", "name": "a", "co": [0.0, 0.0], "fixed": True},
                {"op": "point", "name": "b", "co": [5.0, 0.0]},
                {"op": "line", "name": "base", "p1": "a", "p2": "b"},
                {"op": "constrain", "type": "horizontal", "refs": ["base"]},
                {
                    "op": "constrain",
                    "type": "distance",
                    "name": "length",
                    "refs": ["a", "b"],
                    "value": 10.0,
                },
            ]
        )
        data = describe.sketch_data(self.sketch)
        uid = next(c["uid"] for c in data["constraints"] if c["type"] == "DISTANCE")
        result = self._edit([{"op": "set_value", "target": uid, "value": 4.0}])
        line = next(e for e in result["entities"] if e["name"] == "base")
        self.assertAlmostEqual(line["length"], 4.0, places=4)


class TestMcpOpChecks(Sketch2dTestCase):
    """The checks that keep bad arguments away from the solver.

    solvespace aborts the process on a wrong argument type, which would take the
    user's unsaved work with it, so every one of these must be refused in Python.
    """

    def test_a_line_where_a_point_is_wanted_is_refused(self):
        p1 = self.add_point((0.0, 0.0))
        p2 = self.add_point((5.0, 0.0))
        line = self.add_line(p1, p2)
        line.name = "base"

        with self.assertRaises(OpError) as caught:
            apply_ops(
                self.sketch,
                [{"op": "constrain", "type": "midpoint", "refs": ["base", "base"]}],
            )
        self.assertIn("must be a point", str(caught.exception))

    def test_a_point_where_a_line_is_wanted_is_refused(self):
        point = self.add_point((1.0, 1.0))
        point.name = "lonely"

        with self.assertRaises(OpError) as caught:
            apply_ops(
                self.sketch,
                [{"op": "constrain", "type": "parallel", "refs": ["lonely", "lonely"]}],
            )
        self.assertIn("must be a line", str(caught.exception))

    def test_equal_between_a_line_and_a_circle_is_refused(self):
        p1 = self.add_point((0.0, 0.0))
        p2 = self.add_point((5.0, 0.0))
        line = self.add_line(p1, p2)
        line.name = "base"
        center = self.add_point((10.0, 10.0))
        circle = self.add_circle(center, 3.0)
        circle.name = "hole"

        # solvespace has no line-vs-circle equality and crashes on the pair, so
        # it must be refused; which of the two checks catches it does not matter.
        with self.assertRaises(OpError) as caught:
            apply_ops(
                self.sketch,
                [{"op": "constrain", "type": "equal", "refs": ["base", "hole"]}],
            )
        self.assertIn("circle", str(caught.exception))
        self.assertEqual(list(self.sketch.constraints.all), [])

    def test_a_constraint_short_of_an_entity_is_refused(self):
        point = self.add_point((1.0, 1.0))
        point.name = "solo"

        with self.assertRaises(OpError) as caught:
            apply_ops(
                self.sketch,
                [{"op": "constrain", "type": "horizontal", "refs": ["solo"]}],
            )
        self.assertIn("still needs", str(caught.exception))

    def test_horizontal_on_a_line_needs_no_second_entity(self):
        p1 = self.add_point((0.0, 0.0))
        p2 = self.add_point((5.0, 1.0))
        line = self.add_line(p1, p2)
        line.name = "base"

        apply_ops(
            self.sketch, [{"op": "constrain", "type": "horizontal", "refs": ["base"]}]
        )
        types = [c.type for c in self.sketch.constraints.all]
        self.assertIn("HORIZONTAL", types)

    def test_an_unknown_name_says_what_is_known(self):
        with self.assertRaises(OpError) as caught:
            apply_ops(self.sketch, [{"op": "line", "p1": "nope", "p2": [1.0, 1.0]}])
        self.assertIn("nope", str(caught.exception))

    def test_an_unknown_op_lists_the_known_ops(self):
        with self.assertRaises(OpError) as caught:
            apply_ops(self.sketch, [{"op": "extrude"}])
        self.assertIn("unknown op", str(caught.exception))

    def test_an_unknown_constraint_type_lists_the_known_types(self):
        point = self.add_point((0.0, 0.0))
        point.name = "a"
        with self.assertRaises(OpError) as caught:
            apply_ops(
                self.sketch, [{"op": "constrain", "type": "welded", "refs": ["a"]}]
            )
        self.assertIn("unknown constraint type", str(caught.exception))

    def test_the_origin_cannot_be_deleted(self):
        # The harness builds a bare sketch, so give it the origin a real one has.
        origin = self.add_point((0.0, 0.0), fixed=True, is_origin=True)
        origin.name = "Origin"

        with self.assertRaises(OpError) as caught:
            apply_ops(self.sketch, [{"op": "delete", "target": "Origin"}])
        self.assertIn("origin", str(caught.exception))
        self.assertTrue(origin.valid)

    def test_a_negative_radius_is_refused(self):
        with self.assertRaises(OpError):
            apply_ops(
                self.sketch,
                [{"op": "circle", "center": [0.0, 0.0], "radius": -1.0}],
            )


class TestMcpCreateSketch(Sketch2dTestCase):
    def test_a_new_sketch_has_exactly_one_origin(self):
        # The origin is minted both here and by the self-heal, which can run
        # against the half-built sketch when the create is driven from a timer.
        created = handlers.create_sketch(self.context, {"name": "Made", "plane": "XY"})
        origins = [e for e in created["entities"] if e.get("origin")]
        self.assertEqual(len(origins), 1, created["entities"])

    def test_a_new_sketch_is_named_and_active(self):
        created = handlers.create_sketch(self.context, {"name": "Plate", "plane": "XZ"})
        self.assertIn("Plate", created["sketch"])
        scene = describe.scene_data(self.context)
        self.assertEqual(scene["active_sketch"], created["sketch"])


class TestMcpActivity(Sketch2dTestCase):
    """The log the sidebar shows, so the agent's work is visible in Blender."""

    def setUp(self):
        super().setUp()
        activity.clear()

    def test_a_call_is_logged_with_what_it_did(self):
        handlers.edit_sketch(
            self.context,
            {
                "sketch": self.sketch.name,
                "ops": [{"op": "point", "name": "a", "co": [0.0, 0.0]}],
            },
        )
        # The log is written by the dispatcher, so drive it the way a call does.
        entries = activity.entries()
        self.assertEqual(entries, [], "handlers alone should not log")

        activity.note_result("edit_sketch", describe.sketch_data(self.sketch), None)
        entry = activity.entries()[-1]
        self.assertEqual(entry.tool, "edit_sketch")
        self.assertTrue(entry.ok)
        self.assertIn(self.sketch.name, entry.detail)

    def test_a_failure_is_logged_as_one(self):
        activity.note_result("edit_sketch", None, ToolError("no such sketch 'Nope'"))
        entry = activity.entries()[-1]
        self.assertFalse(entry.ok)
        self.assertIn("Nope", entry.detail)

    def test_the_log_keeps_only_the_recent_ones(self):
        for i in range(activity.LIMIT + 5):
            activity.note_result(f"tool_{i}", {}, None)
        entries = activity.entries()
        self.assertEqual(len(entries), activity.LIMIT)
        self.assertEqual(entries[-1].tool, f"tool_{activity.LIMIT + 4}")

    def test_an_edit_summary_says_what_was_added(self):
        result = {
            "sketch": "Plate",
            "applied": {"entities_added": 4, "constraints_added": 2},
        }
        detail = activity.summarise("edit_sketch", result)
        self.assertIn("+4 entities", detail)
        self.assertIn("+2 constraints", detail)

    def test_a_fully_defined_sketch_says_so(self):
        detail = activity.summarise(
            "solve_sketch", {"sketch": "Plate", "dof": 0, "fully_defined": True}
        )
        self.assertIn("fully defined", detail)

    def test_a_render_is_summarised_without_its_bytes(self):
        detail = activity.summarise("render_sketch", (b"\x89PNG" * 500, "image/png"))
        self.assertEqual(detail, "rendered")

    def test_clearing_empties_the_log(self):
        activity.note_result("describe_scene", {}, None)
        self.assertTrue(activity.entries())
        activity.clear()
        self.assertEqual(activity.entries(), [])


class TestMcpToolSchemas(Sketch2dTestCase):
    def test_every_tool_has_a_schema_and_a_handler(self):
        for tool in tools.TOOLS:
            self.assertTrue(tool["description"], tool["name"])
            self.assertEqual(tool["inputSchema"]["type"], "object")
            self.assertTrue(callable(tool["handler"]))

    def test_the_listing_hides_the_local_handler(self):
        for entry in tools.listing():
            self.assertNotIn("handler", entry)

    def test_the_constraint_enum_matches_what_can_be_created(self):
        from ..mcp.ops import ADDERS
        from ..model.types import SlvsConstraints

        for constraint_type, adder in ADDERS.items():
            self.assertIsNotNone(
                SlvsConstraints.cls_from_type(constraint_type), constraint_type
            )
            self.assertTrue(hasattr(SlvsConstraints, adder), adder)


class TestMcpTransport(Sketch2dTestCase):
    """The HTTP endpoint: what it refuses, and the methods it answers."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Port 0 lets the OS pick a free one, so a developer's own endpoint or a
        # parallel test run cannot collide with this.
        cls.server = server.MCPServer(port=0)
        cls.server.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()
        super().tearDownClass()

    def _url(self, token=None):
        token = self.server.token if token is None else token
        return f"http://127.0.0.1:{self.server.port}/mcp/{token}"

    def _post(self, body, headers=None, token=None):
        request = urllib.request.Request(
            self._url(token),
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", **(headers or {})},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read() or b"{}")

    def _post_expecting_error(self, body, headers=None, token=None):
        try:
            self._post(body, headers=headers, token=token)
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")
        self.fail("expected the request to be refused")

    def test_discover_reports_versions_and_instructions(self):
        # The 2026-07-28 revision requires every server to answer this.
        status, body = self._post(
            {"jsonrpc": "2.0", "id": 10, "method": "server/discover", "params": {}}
        )
        self.assertEqual(status, 200)
        result = body["result"]
        self.assertIn(server.PROTOCOL_VERSION, result["supportedVersions"])
        self.assertIn("tools", result["capabilities"])
        self.assertIn("describe_scene", result["instructions"])
        info = result["_meta"]["io.modelcontextprotocol/serverInfo"]
        self.assertEqual(info["name"], "cad-sketcher")

    def test_initialize_carries_the_instructions_too(self):
        _, body = self._post(
            {"jsonrpc": "2.0", "id": 11, "method": "initialize", "params": {}}
        )
        self.assertIn("edit_sketch", body["result"]["instructions"])

    def test_initialize_reports_the_tools_capability(self):
        status, body = self._post(
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
        )
        self.assertEqual(status, 200)
        self.assertIn("tools", body["result"]["capabilities"])
        self.assertEqual(body["result"]["serverInfo"]["name"], "cad-sketcher")

    def test_every_result_carries_a_result_type(self):
        # The modern revision puts resultType on every result, and a client
        # rejects the whole response without it: no tools reach the agent.
        # tools/call is covered by the failing-call test below, which answers
        # without the main-thread hop that a background Blender never runs.
        for method, params in (
            ("server/discover", {}),
            ("tools/list", {}),
            ("ping", {}),
        ):
            _, body = self._post(
                {"jsonrpc": "2.0", "id": 20, "method": method, "params": params}
            )
            self.assertEqual(body["result"].get("resultType"), "complete", method)

    def test_a_failed_tool_call_still_carries_a_result_type(self):
        _, body = self._post(
            {
                "jsonrpc": "2.0",
                "id": 21,
                "method": "tools/call",
                "params": {"name": "no_such_tool", "arguments": {}},
            }
        )
        self.assertEqual(body["result"]["resultType"], "complete")
        self.assertTrue(body["result"]["isError"])

    def test_the_legacy_handshake_has_no_result_type(self):
        # initialize predates the field; a legacy client should not meet it.
        _, body = self._post(
            {"jsonrpc": "2.0", "id": 22, "method": "initialize", "params": {}}
        )
        self.assertNotIn("resultType", body["result"])

    def test_tools_list_returns_the_tools(self):
        _, body = self._post({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = {tool["name"] for tool in body["result"]["tools"]}
        self.assertIn("edit_sketch", names)
        self.assertIn("describe_scene", names)

    def test_a_request_with_an_origin_header_is_refused(self):
        # Browsers always send Origin and MCP clients never do, so this is what
        # keeps a visited web page from driving the user's CAD session.
        code, body = self._post_expecting_error(
            {"jsonrpc": "2.0", "id": 3, "method": "tools/list"},
            headers={"Origin": "https://evil.example"},
        )
        self.assertEqual(code, 403)
        self.assertIn("Origin", body["error"]["message"])

    def test_the_wrong_token_is_not_found(self):
        code, _ = self._post_expecting_error(
            {"jsonrpc": "2.0", "id": 4, "method": "tools/list"}, token="guessed"
        )
        self.assertEqual(code, 404)

    def test_an_unknown_method_is_reported_as_such(self):
        code, body = self._post_expecting_error(
            {"jsonrpc": "2.0", "id": 5, "method": "resources/list"}
        )
        self.assertEqual(code, 404)
        self.assertEqual(body["error"]["code"], server.METHOD_NOT_FOUND)

    def test_a_header_that_contradicts_the_body_is_refused(self):
        code, body = self._post_expecting_error(
            {"jsonrpc": "2.0", "id": 6, "method": "tools/list"},
            headers={"Mcp-Method": "tools/call"},
        )
        self.assertEqual(code, 400)
        self.assertEqual(body["error"]["code"], server.HEADER_MISMATCH)

    def test_an_unsupported_protocol_version_lists_what_is_supported(self):
        code, body = self._post_expecting_error(
            {"jsonrpc": "2.0", "id": 7, "method": "tools/list"},
            headers={"MCP-Protocol-Version": "1999-01-01"},
        )
        self.assertEqual(code, 400)
        self.assertIn(server.PROTOCOL_VERSION, body["error"]["data"]["supported"])

    def test_a_notification_is_acknowledged_without_an_answer(self):
        status, body = self._post(
            {"jsonrpc": "2.0", "method": "notifications/initialized"}
        )
        self.assertEqual(status, 202)
        self.assertEqual(body, {})

    def test_there_is_no_get_stream(self):
        request = urllib.request.Request(self._url(), method="GET")
        try:
            urllib.request.urlopen(request, timeout=5)
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 405)
        else:
            self.fail("GET should not be served")

    def test_the_url_carries_the_token(self):
        self.assertIn(self.server.token, self.server.url)
        self.assertTrue(self.server.url.startswith("http://127.0.0.1:"))

    def test_every_client_format_carries_the_url(self):
        from ..mcp import clients

        for client_format, _label, _desc in clients.FORMAT_ITEMS:
            snippet = self.server.connect_snippet(client_format)
            self.assertIn(self.server.url, snippet, client_format)

    def test_the_plain_url_is_the_default_and_carries_nothing_else(self):
        # The transport is standard, so the bare address is what works
        # everywhere; anything client-shaped is a convenience on top.
        self.assertEqual(self.server.connect_snippet(), self.server.url)
        self.assertEqual(self.server.connect_snippet("URL"), self.server.url)

    def test_the_json_formats_parse_as_the_client_expects(self):
        import json

        from ..mcp import clients

        entry = json.loads(clients.mcp_servers_json(self.server.url))
        self.assertEqual(entry["mcpServers"]["cad-sketcher"]["url"], self.server.url)

        # VS Code keys on `servers` and insists the transport is named.
        entry = json.loads(clients.vscode_json(self.server.url))
        self.assertEqual(entry["servers"]["cad-sketcher"]["type"], "http")
        self.assertEqual(entry["servers"]["cad-sketcher"]["url"], self.server.url)

    def test_an_unknown_format_falls_back_to_the_url(self):
        from ..mcp import clients

        self.assertEqual(clients.snippet(self.server.url, "nonsense"), self.server.url)


class TestMcpToken(Sketch2dTestCase):
    """The token is remembered, so an agent is registered once, not per session."""

    def test_the_token_survives_a_restart(self):
        first = server.read_token()
        self.assertTrue(first)
        self.assertEqual(server.read_token(), first)
        # A new server picks up the stored one rather than minting its own.
        self.assertEqual(server.MCPServer(port=0).token, first)

    def test_a_new_token_replaces_the_old_one(self):
        first = server.read_token()
        second = server.new_token()
        self.assertNotEqual(first, second)
        self.assertEqual(server.read_token(), second)

    def test_the_stored_token_is_not_world_readable(self):
        import stat

        server.new_token()
        mode = server._token_file().stat().st_mode
        self.assertFalse(mode & (stat.S_IRGRP | stat.S_IROTH), oct(mode))
