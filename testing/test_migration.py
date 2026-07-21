"""Tests for legacy entity -> native curve migration (utilities.migrate).

Opens old entity-based .blend fixtures; the load_post handler auto-migrates them
to native curves. Each test asserts the migrated geometry and constraints match
the known contents of that file (sketch/curve/constraint counts, constraint type
breakdown, and preserved dimensional values).
"""

import os
import unittest

import bpy

from ..model.sketch_ref import get_sketches

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
DIM_TYPES = {"DISTANCE", "DIAMETER", "ANGLE", "RATIO"}


def _open(name):
    bpy.ops.wm.open_mainfile(filepath=os.path.join(FIXTURES, name))


def _summary(context):
    """(n_sketches, n_curves, n_constraints, {type: count}, sorted non-ref dim values)."""
    sketches = list(get_sketches(context))
    n_curves = sum(len(s.data.curves) for s in sketches)
    ctypes = {}
    dim_values = []
    n_con = 0
    for s in sketches:
        for c in s.constraints.all:
            n_con += 1
            ctypes[c.type] = ctypes.get(c.type, 0) + 1
            if c.type in DIM_TYPES and not c.is_reference:
                dim_values.append(round(c.value, 3))
    return sketches, n_curves, n_con, ctypes, sorted(dim_values)


class TestMigration(unittest.TestCase):
    def test_simple_line(self):
        _open("simple_line.blend")
        sk, curves, _, ctypes, _ = _summary(bpy.context)
        self.assertEqual(len(sk), 1)
        self.assertEqual(curves, 7)  # 4 points + 3 lines
        self.assertEqual(ctypes, {"HORIZONTAL": 1})

    def test_tangent(self):
        _open("tangent_test.blend")
        sk, curves, _, ctypes, vals = _summary(bpy.context)
        self.assertEqual(len(sk), 1)
        self.assertEqual(curves, 12)
        self.assertEqual(ctypes, {"COINCIDENT": 1, "DIAMETER": 1, "TANGENT": 4})
        self.assertEqual(vals, [4.0])

    def test_offset_arc(self):
        _open("offset_arc.blend")
        sk, curves, _, ctypes, vals = _summary(bpy.context)
        self.assertEqual(len(sk), 1)
        self.assertEqual(curves, 38)
        self.assertEqual(ctypes, {"DISTANCE": 1, "HORIZONTAL": 3, "VERTICAL": 3})
        self.assertEqual(vals, [4.984])

    def test_reference_dimensions(self):
        _open("test_reference_dimensions.blend")
        sk, curves, n_con, ctypes, _ = _summary(bpy.context)
        self.assertEqual(len(sk), 1)
        self.assertEqual(curves, 13)
        self.assertEqual(n_con, 8)
        self.assertEqual(
            ctypes,
            {"ANGLE": 1, "DIAMETER": 2, "DISTANCE": 2,
             "HORIZONTAL": 1, "TANGENT": 1, "VERTICAL": 1},
        )

    def test_cad_part_geometry_constraints_values(self):
        _open("CAD_Sketcher_Part.blend")
        sk, curves, n_con, ctypes, vals = _summary(bpy.context)
        self.assertEqual(len(sk), 6)
        self.assertEqual(curves, 93)
        self.assertEqual(n_con, 75)
        self.assertEqual(
            ctypes,
            {"COINCIDENT": 3, "DIAMETER": 6, "DISTANCE": 14, "EQUAL": 6,
             "HORIZONTAL": 14, "MIDPOINT": 5, "TANGENT": 10, "VERTICAL": 17},
        )
        # Dimensional values are preserved exactly from the legacy file.
        self.assertEqual(
            vals,
            [5.0, 10.0, 13.0, 18.0, 18.0, 20.0, 30.0, 30.0, 30.0, 40.0,
             53.0, 53.0, 53.0, 55.0, 55.0, 80.0, 80.0, 100.0, 150.0, 150.0],
        )

    def test_idempotent(self):
        # Re-running migration on an already-migrated scene is a no-op.
        from ..utilities.migrate import migrate_scene, scene_needs_migration

        _open("simple_line.blend")
        self.assertFalse(scene_needs_migration(bpy.context))  # already auto-migrated
        before = len(list(get_sketches(bpy.context)))
        migrate_scene(bpy.context)
        self.assertEqual(len(list(get_sketches(bpy.context))), before)
