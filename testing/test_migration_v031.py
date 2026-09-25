"""Updating a file saved by 0.31, where the sketch object carried the stack.

``fixtures/v0_31_part.blend`` was authored by the real v0.31.1 add-on (see
``scripts/make_v031_fixture.py``), so this is the shape users actually have on
disk between the native-curves refactor and the source/body split: Curves
objects with the tool modifiers on them, no bodies, no parts.

The cases below run the one button users press, ``Update File``, and assert what
they get back: the same geometry, in the same place, under the same names, with
the same things hidden.
"""

import os
import unittest

import bpy

from ..model.sketch_ref import get_sketches
from ..utilities.body import body_of, sketch_of

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "v0_31_part.blend")


def _update_file():
    bpy.ops.wm.open_mainfile(filepath=FIXTURE)
    bpy.ops.view3d.slvs_migrate_legacy()


def _sketches():
    return {s.target_object.name: s for s in get_sketches(bpy.context)}


def _bodies():
    return {
        body_of(s.target_object).name: body_of(s.target_object)
        for s in _sketches().values()
    }


def _evaluated_bounds(obj):
    """(vertex count, world-space dimensions) of an object's evaluated mesh."""
    obj.update_tag()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    depsgraph.update()
    mesh = obj.evaluated_get(depsgraph).to_mesh()
    lo = [1e18] * 3
    hi = [-1e18] * 3
    for vertex in mesh.vertices:
        world = obj.matrix_world @ vertex.co
        for i in range(3):
            lo[i] = min(lo[i], world[i])
            hi[i] = max(hi[i], world[i])
    count = len(mesh.vertices)
    obj.to_mesh_clear()
    return count, [hi[i] - lo[i] for i in range(3)]


class TestMigrationFrom031(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        # Opening a file replaces everything, the window's scene included. Leave
        # an empty one behind so the next test class starts from a clean file
        # rather than inheriting this fixture's objects and scene.
        bpy.ops.wm.read_homefile(use_empty=True)

    def test_every_sketch_lands_on_a_body(self):
        _update_file()
        sketches = _sketches()
        self.assertEqual(len(sketches), 3)
        for sketch in sketches.values():
            obj = sketch.target_object
            body = body_of(obj)
            self.assertIsNotNone(body, f"{obj.name} has no body")
            self.assertEqual(sketch_of(body), obj)
            # Nothing that changes the sketch's type is left on it (issue #723).
            self.assertEqual(list(obj.modifiers), [])

    def test_the_stack_keeps_its_order_on_the_body(self):
        _update_file()
        body = bpy.data.objects["Plate"]
        self.assertEqual(
            [m.name for m in body.modifiers],
            [
                "CAD Sketcher Convert",
                "CAD_Sketcher Extrude",
                "CAD_Sketcher Boolean Hole",
                "CAD_Sketcher Linear Array",
            ],
        )

    def test_the_boolean_cuts_with_the_cutter_s_body(self):
        from ..operators.modifiers import boolean_input_ids, get_modifier_input

        _update_file()
        body = bpy.data.objects["Plate"]
        modifier = body.modifiers["CAD_Sketcher Boolean Hole"]
        cutter = get_modifier_input(
            modifier, boolean_input_ids(modifier.node_group)["Cutter"]
        )
        # The cutter moved to the body too: the curves alone cut nothing.
        self.assertIsNotNone(sketch_of(cutter), f"cutter {cutter!r} is not a body")
        self.assertEqual(cutter, bpy.data.objects["Hole"])

    def test_the_part_keeps_the_names_the_user_gave_it(self):
        _update_file()
        for name in ("Plate", "Hole", "Outline"):
            body = bpy.data.objects.get(name)
            self.assertIsNotNone(body, f"no body named {name}")
            self.assertEqual(body.type, "MESH")
            self.assertIsNotNone(bpy.data.objects.get(f"{name} Sketch"))

    def test_a_hidden_cutter_stays_hidden(self):
        # The file has the cutter put away, eye and viewport both. Before the
        # split the sketch object was what hiding hid, so the body inherits it.
        _update_file()
        hole = bpy.data.objects["Hole"]
        self.assertTrue(hole.hide_viewport)
        self.assertTrue(hole.hide_get())
        plate = bpy.data.objects["Plate"]
        self.assertFalse(plate.hide_viewport)
        self.assertFalse(plate.hide_get())

    def test_the_geometry_survives(self):
        _update_file()
        count, dims = _evaluated_bounds(bpy.data.objects["Plate"])
        # Three arrayed copies of a 40 x 24 x 8 plate with a hole through it.
        self.assertGreater(count, 100)
        for got, want in zip(dims, (140.0, 24.0, 8.0)):
            self.assertAlmostEqual(got, want, delta=0.5)

    def test_updating_twice_changes_nothing(self):
        _update_file()
        before = sorted(o.name for o in bpy.data.objects)
        bpy.ops.view3d.slvs_migrate_legacy()
        self.assertEqual(sorted(o.name for o in bpy.data.objects), before)
