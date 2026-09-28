"""The MCP endpoint: the tools, the op checks, and the HTTP transport.

Tools are driven through ``handlers`` rather than over a socket, since a
background Blender runs no timers and so never reaches the main-thread hop.
The transport is tested separately, on the methods that answer without touching
Blender data.
"""

import json
import urllib.error
import urllib.request

from ..mcp import describe, handlers, server, tools
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

    def test_initialize_reports_the_tools_capability(self):
        status, body = self._post(
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
        )
        self.assertEqual(status, 200)
        self.assertIn("tools", body["result"]["capabilities"])
        self.assertEqual(body["result"]["serverInfo"]["name"], "cad-sketcher")

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
