"""Tests for legacy entity -> native curve migration (utilities.migrate).

Opens old entity-based .blend fixtures and runs migration (the same call the
``slvs_migrate_legacy`` operator makes). Each test asserts the migrated geometry
and constraints match the known contents of that file (sketch/curve/constraint
counts, constraint type breakdown, and preserved dimensional values).
"""

import os
import unittest

import bpy

from ..model.sketch_ref import get_sketches
from ..utilities.migrate import migrate_scene, scene_needs_migration
from ..versioning import do_versioning

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
DIM_TYPES = {"DISTANCE", "DIAMETER", "ANGLE", "RATIO"}


def _open(name):
    # Migration is manual now (no load/version handlers); run it explicitly on
    # open exactly the way the slvs_migrate_legacy operator does: patch the
    # legacy entity data forward, then convert it to curves.
    bpy.ops.wm.open_mainfile(filepath=os.path.join(FIXTURES, name))
    if scene_needs_migration(bpy.context):
        do_versioning()
        migrate_scene(bpy.context)


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
            {
                "ANGLE": 1,
                "DIAMETER": 2,
                "DISTANCE": 2,
                "HORIZONTAL": 1,
                "TANGENT": 1,
                "VERTICAL": 1,
            },
        )

    def test_cad_part_geometry_constraints_values(self):
        _open("CAD_Sketcher_Part.blend")
        sk, curves, n_con, ctypes, vals = _summary(bpy.context)
        self.assertEqual(len(sk), 6)
        self.assertEqual(curves, 93)
        self.assertEqual(n_con, 75)
        self.assertEqual(
            ctypes,
            {
                "COINCIDENT": 3,
                "DIAMETER": 6,
                "DISTANCE": 14,
                "EQUAL": 6,
                "HORIZONTAL": 14,
                "MIDPOINT": 5,
                "TANGENT": 10,
                "VERTICAL": 17,
            },
        )
        # Dimensional values are preserved exactly from the legacy file.
        self.assertEqual(
            vals,
            [
                5.0,
                10.0,
                13.0,
                18.0,
                18.0,
                20.0,
                30.0,
                30.0,
                30.0,
                40.0,
                53.0,
                53.0,
                53.0,
                55.0,
                55.0,
                80.0,
                80.0,
                100.0,
                150.0,
                150.0,
            ],
        )

    def test_cad_part_modifiers_translated_to_gn(self):
        # The legacy part stacks Solidify + Boolean on its generated meshes.
        # Migration must rebuild those as this addon's tools on the body each
        # sketch is realised on, remap boolean cutters onto the migrated
        # sketches, and delete the old meshes so geometry is not duplicated.
        from ..model.sketch_ref import is_sketch_object
        from ..operators.modifiers import boolean_input_ids, get_modifier_input
        from ..utilities.body import body_of, sketch_of

        _open("CAD_Sketcher_Part.blend")
        sketches = list(get_sketches(bpy.context))

        extrudes = booleans = 0
        for s in sketches:
            body = body_of(s.target_object)
            self.assertIsNotNone(body, f"{s.name} has no body")
            for m in body.modifiers:
                if m.type != "NODES" or m.node_group is None:
                    continue
                name = m.node_group.name
                if name == "CAD Sketcher Extrude":
                    extrudes += 1
                elif name == "CAD Sketcher Boolean":
                    booleans += 1
                    ids = boolean_input_ids(m.node_group)
                    cutter = get_modifier_input(m, ids["Cutter"])
                    # The cutter is another migrated sketch's body, not an old
                    # mesh -- it is the geometry that cuts.
                    source = sketch_of(cutter)
                    self.assertTrue(
                        source is not None and is_sketch_object(source),
                        f"boolean cutter {cutter!r} is not a migrated sketch",
                    )

        # Six Solidify -> Extrude, five Boolean -> Boolean node group.
        self.assertEqual(extrudes, 6)
        self.assertEqual(booleans, 5)

        # No orphaned legacy mesh (carrying the raw modifier stack) is left over.
        leftovers = [
            o.name
            for o in bpy.data.objects
            if o.type == "MESH"
            and any(mm.type in ("SOLIDIFY", "BOOLEAN") for mm in o.modifiers)
        ]
        self.assertEqual(leftovers, [])

    def test_cad_part_evaluated_geometry(self):
        # Guard the actual 3D output, not just the modifier recipe: the migrated
        # part must still evaluate (Convert -> Extrude -> Booleans) to a solid
        # whose bounds match the legacy part (150 x 80 x 100). Read from the
        # bodies, which is where the stack lives and which are plain meshes.
        from ..utilities.body import body_of
        from ..utilities.curve_data import refresh_curve_geometry

        _open("CAD_Sketcher_Part.blend")
        sketches = list(get_sketches(bpy.context))
        for s in sketches:
            refresh_curve_geometry(s)  # force the GN modifiers to re-evaluate
        bpy.context.view_layer.update()
        dg = bpy.context.evaluated_depsgraph_get()

        total_v = 0
        lo = [1e18] * 3
        hi = [-1e18] * 3
        for sketch in sketches:
            body = body_of(sketch.target_object)
            self.assertIsNotNone(body, f"{sketch.name} has no body")
            mesh = body.evaluated_get(dg).to_mesh()
            total_v += len(mesh.vertices)
            for vertex in mesh.vertices:
                world = body.matrix_world @ vertex.co
                for i in range(3):
                    lo[i] = min(lo[i], world[i])
                    hi[i] = max(hi[i], world[i])
            body.to_mesh_clear()

        dims = [hi[i] - lo[i] for i in range(3)]
        # A substantial solid, not the flat sketch profile (Extrude + Booleans ran).
        self.assertGreater(total_v, 200)
        # Overall bounds match the legacy dimensions; each axis is real 3D depth.
        for got, want in zip(dims, (150.0, 80.0, 100.0)):
            self.assertAlmostEqual(got, want, delta=1.0)

    def test_idempotent(self):
        # Re-running migration on an already-migrated scene is a no-op.
        _open("simple_line.blend")
        self.assertFalse(scene_needs_migration(bpy.context))  # _open migrated it
        before = len(list(get_sketches(bpy.context)))
        migrate_scene(bpy.context)
        self.assertEqual(len(list(get_sketches(bpy.context))), before)
