"""The MCP endpoint: the tools, the op checks, and the HTTP transport.

Tools are driven through ``handlers`` rather than over a socket, since a
background Blender runs no timers and so never reaches the main-thread hop.
The transport is tested separately, on the methods that answer without touching
Blender data.
"""

import http.client
import json
import select
import time

from ..mcp import activity, describe, handlers, render, server, tools
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

    def test_a_distance_to_a_line_keeps_the_side_it_was_placed_on(self):
        # Distance to a line is signed, and the side is settled while measuring.
        # A value given up front used to skip that and mirror the point through
        # the line: holes placed inside a part came out beyond its edge.
        result = self._edit(
            [
                {"op": "point", "name": "a", "co": [0.0, 0.0], "fixed": True},
                {"op": "point", "name": "b", "co": [0.0, 10.0]},
                {"op": "line", "name": "edge", "p1": "a", "p2": "b"},
                {"op": "constrain", "type": "vertical", "refs": ["edge"]},
                {"op": "point", "name": "inside", "co": [3.0, 5.0]},
                {
                    "op": "constrain",
                    "type": "distance",
                    "refs": ["inside", "edge"],
                    "value": 4.0,
                },
            ]
        )
        point = next(e for e in result["entities"] if e["name"] == "inside")
        self.assertAlmostEqual(abs(point["co"][0]), 4.0, places=4)
        self.assertGreater(
            point["co"][0], 0.0, f"placed at x=+3 but solved to {point['co']}"
        )

    def test_a_distance_to_a_line_keeps_a_negative_side_too(self):
        result = self._edit(
            [
                {"op": "point", "name": "a", "co": [0.0, 0.0], "fixed": True},
                {"op": "point", "name": "b", "co": [0.0, 10.0]},
                {"op": "line", "name": "edge", "p1": "a", "p2": "b"},
                {"op": "constrain", "type": "vertical", "refs": ["edge"]},
                {"op": "point", "name": "outside", "co": [-3.0, 5.0]},
                {
                    "op": "constrain",
                    "type": "distance",
                    "refs": ["outside", "edge"],
                    "value": 4.0,
                },
            ]
        )
        point = next(e for e in result["entities"] if e["name"] == "outside")
        self.assertAlmostEqual(abs(point["co"][0]), 4.0, places=4)
        self.assertLess(
            point["co"][0], 0.0, f"placed at x=-3 but solved to {point['co']}"
        )

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

    def test_a_new_sketch_is_named_and_listed(self):
        created = handlers.create_sketch(self.context, {"name": "Plate", "plane": "XZ"})
        self.assertIn("Plate", created["sketch"])
        scene = describe.scene_data(self.context)
        self.assertIn(created["sketch"], [s["name"] for s in scene["sketches"]])


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


class TestMcpFeatures(Sketch2dTestCase):
    """Turning sketches into solids through the feature tools."""

    def _plate(self, name="Plate", size=0.05):
        sketch = handlers.create_sketch(self.context, {"name": name, "plane": "XY"})
        target = sketch["sketch"]
        handlers.edit_sketch(
            self.context,
            {
                "sketch": target,
                "ops": [
                    {"op": "point", "name": "a", "co": [0, 0], "fixed": True},
                    {"op": "point", "name": "b", "co": [size, 0.001]},
                    {"op": "point", "name": "c", "co": [size, size]},
                    {"op": "point", "name": "d", "co": [0.001, size]},
                    {"op": "line", "name": "s1", "p1": "a", "p2": "b"},
                    {"op": "line", "name": "s2", "p1": "b", "p2": "c"},
                    {"op": "line", "name": "s3", "p1": "c", "p2": "d"},
                    {"op": "line", "name": "s4", "p1": "d", "p2": "a"},
                    {"op": "constrain", "type": "horizontal", "refs": ["s1"]},
                    {"op": "constrain", "type": "horizontal", "refs": ["s3"]},
                    {"op": "constrain", "type": "vertical", "refs": ["s2"]},
                    {"op": "constrain", "type": "vertical", "refs": ["s4"]},
                    {
                        "op": "constrain",
                        "type": "distance",
                        "refs": ["a", "b"],
                        "value": size,
                    },
                    {
                        "op": "constrain",
                        "type": "distance",
                        "refs": ["a", "d"],
                        "value": size,
                    },
                ],
            },
        )
        return target

    def test_an_extrude_builds_a_solid_on_the_sketch(self):
        sketch = self._plate()
        body = handlers.extrude(self.context, {"sketch": sketch, "distance": 0.01})
        self.assertEqual(body["from_sketch"], sketch)
        self.assertTrue(any("Extrude" in f for f in body["features"]), body["features"])
        self.assertTrue(body["visible"])

    def test_a_solid_with_no_boolean_stays_its_own_visible_body(self):
        # The tool re-decides an "undecided" operation from what the solid
        # overlaps whenever the file's Auto Boolean is on, which used to
        # overrule the choice made here and hide the result as a cutter.
        self.context.scene.sketcher.use_auto_boolean = True
        first = self._plate("One")
        handlers.extrude(self.context, {"sketch": first, "distance": 0.01})
        second = self._plate("Two")
        body = handlers.extrude(
            self.context, {"sketch": second, "distance": 0.01, "boolean": "none"}
        )
        self.assertTrue(body["visible"], "a boolean of none must leave it standing")

    def test_an_explicit_boolean_adds_one_to_the_target(self):
        plate = self._plate("Base")
        base = handlers.extrude(self.context, {"sketch": plate, "distance": 0.01})
        pin = self._plate("Pin", size=0.01)
        cutter = handlers.extrude(self.context, {"sketch": pin, "distance": 0.02})

        result = handlers.boolean(
            self.context,
            {
                "target": base["name"],
                "cutter": cutter["name"],
                "operation": "difference",
            },
        )
        self.assertTrue(
            any("Boolean" in f for f in result["features"]), result["features"]
        )

    def test_a_sketch_name_resolves_to_its_body(self):
        from ..mcp import features

        sketch = self._plate()
        body = handlers.extrude(self.context, {"sketch": sketch, "distance": 0.01})
        # Naming either the sketch or the body reaches the same object.
        self.assertEqual(
            features.find_target(self.context, sketch).name,
            features.find_target(self.context, body["name"]).name,
        )

    def test_a_revolve_axis_is_read_in_world_space(self):
        # The operators store the axis in the object's own space, so a world
        # axis has to be converted. Passed through raw, "about world Z" became
        # "about the sketch normal" and swept the profile flat in its own plane.
        import math

        sketch = handlers.create_sketch(
            self.context, {"name": "Profile", "plane": "XZ", "activate": False}
        )["sketch"]
        handlers.edit_sketch(
            self.context,
            {
                "sketch": sketch,
                "ops": [
                    {"op": "point", "name": "a", "co": [0.04, 0], "fixed": True},
                    {"op": "point", "name": "b", "co": [0.2, 0.001]},
                    {"op": "point", "name": "c", "co": [0.2, 0.1]},
                    {"op": "point", "name": "d", "co": [0.041, 0.1]},
                    {"op": "line", "name": "s1", "p1": "a", "p2": "b"},
                    {"op": "line", "name": "s2", "p1": "b", "p2": "c"},
                    {"op": "line", "name": "s3", "p1": "c", "p2": "d"},
                    {"op": "line", "name": "s4", "p1": "d", "p2": "a"},
                    {"op": "constrain", "type": "horizontal", "refs": ["s1"]},
                    {"op": "constrain", "type": "vertical", "refs": ["s2"]},
                ],
            },
        )
        body = handlers.revolve(
            self.context,
            {
                "sketch": sketch,
                "angle": 2 * math.pi,
                "axis_origin": [0, 0, 0],
                "axis_direction": [0, 0, 1],
            },
        )

        import bpy

        self.context.view_layer.update()
        obj = bpy.data.objects[body["name"]]
        evaluated = obj.evaluated_get(self.context.evaluated_depsgraph_get())
        spans = [
            max(c[axis] for c in evaluated.bound_box)
            - min(c[axis] for c in evaluated.bound_box)
            for axis in range(3)
        ]
        # Sweeping about Z gives width in both X and Y; the broken axis left it
        # flat in Y, with everything still in the sketch's own plane.
        self.assertGreater(spans[1], 0.1, f"revolve came out flat: spans {spans}")
        self.assertAlmostEqual(spans[0], spans[1], places=3)

    def test_an_axis_origin_without_a_direction_is_refused(self):
        sketch = self._plate()
        with self.assertRaises(ToolError) as caught:
            handlers.revolve(
                self.context,
                {"sketch": sketch, "angle": 1.0, "axis_origin": [0, 0, 0]},
            )
        self.assertIn("axis_direction", str(caught.exception))

    def test_an_unknown_target_says_what_is_there(self):
        with self.assertRaises(ToolError) as caught:
            handlers.extrude(self.context, {"sketch": "Nope", "distance": 0.01})
        self.assertIn("Nope", str(caught.exception))

    def test_a_zero_distance_is_refused(self):
        sketch = self._plate()
        with self.assertRaises(ToolError):
            handlers.extrude(self.context, {"sketch": sketch, "distance": 0})

    def test_an_unknown_boolean_is_refused(self):
        sketch = self._plate()
        with self.assertRaises(ToolError) as caught:
            handlers.extrude(
                self.context, {"sketch": sketch, "distance": 0.01, "boolean": "carve"}
            )
        self.assertIn("carve", str(caught.exception))

    def test_a_solid_cannot_be_booleaned_with_itself(self):
        sketch = self._plate()
        body = handlers.extrude(self.context, {"sketch": sketch, "distance": 0.01})
        with self.assertRaises(ToolError) as caught:
            handlers.boolean(
                self.context, {"target": body["name"], "cutter": body["name"]}
            )
        self.assertIn("itself", str(caught.exception))

    def test_the_scene_lists_bodies_so_a_target_can_be_named(self):
        sketch = self._plate()
        body = handlers.extrude(self.context, {"sketch": sketch, "distance": 0.01})
        scene = describe.scene_data(self.context)
        self.assertIn(body["name"], [b["name"] for b in scene["bodies"]])


class TestMcpSketchMode(Sketch2dTestCase):
    """Who decides whether the user is left sitting in sketch mode."""

    def _active(self):
        return describe.scene_data(self.context)["active_sketch"]

    def test_drawing_a_sketch_ends_in_that_sketch(self):
        created = handlers.create_sketch(self.context, {"name": "Entered"})
        self.assertEqual(self._active(), created["sketch"])

    def test_a_sketch_can_be_made_without_going_there(self):
        # For a sketch that is a step towards a solid, not the point of the job.
        before = self._active()
        handlers.create_sketch(self.context, {"name": "Quiet", "activate": False})
        self.assertEqual(self._active(), before)

    def test_leaving_takes_no_name(self):
        handlers.create_sketch(self.context, {"name": "Somewhere", "activate": True})
        result = handlers.set_active_sketch(self.context, {})
        self.assertIsNone(result["active_sketch"])
        self.assertFalse(result["in_sketch_mode"])
        self.assertIsNone(self._active())

    def test_entering_by_name_goes_there(self):
        first = handlers.create_sketch(self.context, {"name": "First"})["sketch"]
        handlers.create_sketch(self.context, {"name": "Second", "activate": True})
        result = handlers.set_active_sketch(self.context, {"sketch": first})
        self.assertEqual(result["active_sketch"], first)
        self.assertEqual(self._active(), first)

    def test_entering_a_sketch_that_is_not_there_is_refused(self):
        with self.assertRaises(ToolError) as caught:
            handlers.set_active_sketch(self.context, {"sketch": "Nope"})
        self.assertIn("Nope", str(caught.exception))

    def test_building_from_the_sketch_you_are_in_brings_you_out(self):
        # Going on to make a solid from it means the sketching is done.
        sketch = handlers.create_sketch(self.context, {"name": "Slab"})["sketch"]
        handlers.edit_sketch(
            self.context,
            {
                "sketch": sketch,
                "ops": [
                    {"op": "point", "name": "a", "co": [0, 0], "fixed": True},
                    {"op": "point", "name": "b", "co": [0.05, 0.001]},
                    {"op": "point", "name": "c", "co": [0.05, 0.05]},
                    {"op": "point", "name": "d", "co": [0.001, 0.05]},
                    {"op": "line", "name": "s1", "p1": "a", "p2": "b"},
                    {"op": "line", "name": "s2", "p1": "b", "p2": "c"},
                    {"op": "line", "name": "s3", "p1": "c", "p2": "d"},
                    {"op": "line", "name": "s4", "p1": "d", "p2": "a"},
                    {"op": "constrain", "type": "horizontal", "refs": ["s1"]},
                    {"op": "constrain", "type": "vertical", "refs": ["s2"]},
                ],
            },
        )
        self.assertEqual(self._active(), sketch, "still sketching at this point")

        handlers.extrude(self.context, {"sketch": sketch, "distance": 0.01})
        self.assertIsNone(self._active(), "the solid ends the sketching")

    def test_building_from_another_sketch_leaves_you_where_you_are(self):
        # A user sitting in their own sketch must not be thrown out of it
        # because the agent built something elsewhere.
        other = self._slab("Elsewhere")
        mine = handlers.create_sketch(self.context, {"name": "Mine"})["sketch"]
        self.assertEqual(self._active(), mine)

        handlers.extrude(self.context, {"sketch": other, "distance": 0.01})
        self.assertEqual(self._active(), mine, "the agent moved the user")

    def _slab(self, name):
        sketch = handlers.create_sketch(
            self.context, {"name": name, "activate": False}
        )["sketch"]
        handlers.edit_sketch(
            self.context,
            {
                "sketch": sketch,
                "ops": [
                    {"op": "point", "name": "a", "co": [0, 0], "fixed": True},
                    {"op": "point", "name": "b", "co": [0.05, 0.001]},
                    {"op": "point", "name": "c", "co": [0.05, 0.05]},
                    {"op": "point", "name": "d", "co": [0.001, 0.05]},
                    {"op": "line", "name": "s1", "p1": "a", "p2": "b"},
                    {"op": "line", "name": "s2", "p1": "b", "p2": "c"},
                    {"op": "line", "name": "s3", "p1": "c", "p2": "d"},
                    {"op": "line", "name": "s4", "p1": "d", "p2": "a"},
                    {"op": "constrain", "type": "horizontal", "refs": ["s1"]},
                    {"op": "constrain", "type": "vertical", "refs": ["s2"]},
                ],
            },
        )
        return sketch


class TestMcpRenderPart(Sketch2dTestCase):
    """Framing and view selection for the solid render.

    The draw itself needs a GPU and a viewport, so what is checked here is the
    camera it would use, not the pixels.
    """

    def test_every_named_view_looks_from_a_different_side(self):
        directions = render.VIEW_DIRECTIONS
        self.assertIn("iso", directions)
        seen = {tuple(round(c, 6) for c in v.normalized()) for v in directions.values()}
        self.assertEqual(len(seen), len(directions), "two views look the same way")

    def test_opposite_views_are_opposite(self):
        directions = render.VIEW_DIRECTIONS
        for a, b in (("front", "back"), ("left", "right"), ("top", "bottom")):
            self.assertAlmostEqual((directions[a] + directions[b]).length, 0.0)

    def test_the_bounds_cover_every_object_shown(self):
        import bpy

        one = bpy.data.objects.new("one", bpy.data.meshes.new("one"))
        two = bpy.data.objects.new("two", bpy.data.meshes.new("two"))
        self.scene.collection.objects.link(one)
        self.scene.collection.objects.link(two)
        one.location = (0.0, 0.0, 0.0)
        two.location = (4.0, 0.0, 0.0)
        try:
            center, half = render._world_bounds(self.context, [one, two])
            # Two empty meshes are points, so the centre sits between them.
            self.assertAlmostEqual(center.x, 2.0, places=4)
            self.assertGreater(half, 0.0)
        finally:
            bpy.data.objects.remove(one, do_unlink=True)
            bpy.data.objects.remove(two, do_unlink=True)

    def test_nothing_solid_is_a_readable_refusal(self):
        with self.assertRaises(ToolError) as caught:
            handlers.render_part(self.context, {})
        self.assertIn("nothing solid", str(caught.exception))

    def test_an_unknown_view_is_refused(self):
        with self.assertRaises(render.RenderUnavailable) as caught:
            render.objects_png(self.context, [], "sideways", 256)
        self.assertIn("sideways", str(caught.exception))


class TestMcpRenderBounds(Sketch2dTestCase):
    """What the render frames. Every sketch owns an origin point at (0, 0), and
    counting it would stretch the frame back there, shrinking work placed away
    from it."""

    def _origin(self):
        return self.add_point((0.0, 0.0), fixed=True, is_origin=True)

    def test_the_origin_does_not_drag_the_frame(self):
        self._origin()
        for co in ((1.0, 1.0), (1.0, 2.0), (2.0, 2.0), (2.0, 1.0)):
            self.add_point(co)

        center, half = render._bounds(self.sketch)
        self.assertAlmostEqual(center.x, 1.5, places=5)
        self.assertAlmostEqual(center.y, 1.5, places=5)
        # The square is 1 across, so the half-extent is 0.5 plus the margin.
        self.assertAlmostEqual(half, 0.5 * render._MARGIN, places=5)

    def test_a_sketch_with_only_its_origin_still_frames_something(self):
        self._origin()
        center, half = render._bounds(self.sketch)
        self.assertEqual(tuple(center), (0.0, 0.0))
        self.assertEqual(half, render._EMPTY_EXTENT)

    def test_an_empty_sketch_frames_something(self):
        center, half = render._bounds(self.sketch)
        self.assertEqual(tuple(center), (0.0, 0.0))
        self.assertEqual(half, render._EMPTY_EXTENT)

    def test_a_circle_is_framed_by_its_rim_not_its_centre(self):
        self._origin()
        center_point = self.add_point((5.0, 5.0))
        self.add_circle(center_point, 2.0)

        center, half = render._bounds(self.sketch)
        self.assertAlmostEqual(center.x, 5.0, places=5)
        # Rim to rim is 4 across, so 2 plus the margin.
        self.assertAlmostEqual(half, 2.0 * render._MARGIN, places=5)

    def test_geometry_at_the_origin_is_still_framed(self):
        self._origin()
        for co in ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0)):
            self.add_point(co)

        center, half = render._bounds(self.sketch)
        self.assertAlmostEqual(center.x, 0.5, places=5)
        self.assertAlmostEqual(half, 0.5 * render._MARGIN, places=5)


class TestMcpFirstRun(Sketch2dTestCase):
    """The sidebar offers setup only until something has actually connected."""

    def setUp(self):
        super().setUp()
        self._seen = server._seen_file()
        self._had = self._seen.exists()
        if self._had:
            self._seen.unlink()
        server._client_seen = None

    def tearDown(self):
        self._seen.unlink(missing_ok=True)
        if self._had:
            self._seen.write_text("1", encoding="utf-8")
        server._client_seen = None
        super().tearDown()

    def test_a_fresh_install_has_not_connected(self):
        self.assertFalse(server.client_ever_connected())

    def test_a_request_records_the_connection(self):
        server.note_client_connected()
        self.assertTrue(server.client_ever_connected())
        self.assertTrue(self._seen.exists())

    def test_the_connection_is_remembered_across_restarts(self):
        server.note_client_connected()
        # A fresh Blender reads it back off disk rather than from memory.
        server._client_seen = None
        self.assertTrue(server.client_ever_connected())

    def test_recording_twice_is_harmless(self):
        server.note_client_connected()
        server.note_client_connected()
        self.assertTrue(server.client_ever_connected())


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

    def _path(self, token=None):
        token = self.server.token if token is None else token
        return f"/mcp/{token}"

    def _request(self, method, body=None, headers=None, token=None):
        """Send one request, serve it the way the timer would, then read it.

        The endpoint is pumped from Blender's main thread and the test runs on
        that same thread, so waiting on the socket for an answer would wait for
        a pump that cannot run. Send first, serve by hand, read after.
        """
        conn = http.client.HTTPConnection(server.HOST, self.server.port, timeout=5)
        try:
            payload = None if body is None else json.dumps(body).encode()
            sent = {"Content-Type": "application/json"} if payload else {}
            sent.update(headers or {})
            conn.request(method, self._path(token), body=payload, headers=sent)
            self._serve_one()
            response = conn.getresponse()
            return response.status, json.loads(response.read() or b"{}")
        finally:
            conn.close()

    def _serve_one(self, timeout=5.0):
        """Run the pump by hand until it has taken the waiting request."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if select.select([self.server.socket], [], [], 0.05)[0]:
                self.server.poll()
                return
        self.fail("the endpoint never saw the request")

    def _post(self, body, headers=None, token=None):
        return self._request("POST", body=body, headers=headers, token=token)

    def _post_expecting_error(self, body, headers=None, token=None):
        status, payload = self._post(body, headers=headers, token=token)
        self.assertGreaterEqual(status, 400, "expected the request to be refused")
        return status, payload

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
        status, _ = self._request("GET")
        self.assertEqual(status, 405)

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

    def test_the_stored_token_is_not_world_readable(self):
        import stat

        server.new_token()
        mode = server._token_file().stat().st_mode
        self.assertFalse(mode & (stat.S_IRGRP | stat.S_IROTH), oct(mode))
