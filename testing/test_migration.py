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
        # Migration must rebuild those as GN siblings on the new Curves sketches,
        # remap boolean cutters onto the migrated sketches, and delete the old
        # meshes so the geometry is not duplicated.
        from ..model.sketch_ref import is_sketch_object
        from ..operators.modifiers import boolean_input_ids, get_modifier_input

        _open("CAD_Sketcher_Part.blend")
        sketches = list(get_sketches(bpy.context))

        extrudes = booleans = 0
        for s in sketches:
            for m in s.target_object.modifiers:
                if m.type != "NODES" or m.node_group is None:
                    continue
                name = m.node_group.name
                if name == "CAD Sketcher Extrude":
                    extrudes += 1
                elif name == "CAD Sketcher Boolean":
                    booleans += 1
                    ids = boolean_input_ids(m.node_group)
                    cutter = get_modifier_input(m, ids["Cutter"])
                    # The cutter is another migrated sketch, not an old mesh.
                    self.assertTrue(
                        is_sketch_object(cutter),
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
        # whose bounds match the legacy part (150 x 80 x 100). The GN chain turns
        # the Curves into a mesh, so the realized geometry is a depsgraph instance
        # rather than the evaluated object's own data.
        from ..utilities.curve_data import refresh_curve_geometry

        _open("CAD_Sketcher_Part.blend")
        sketches = list(get_sketches(bpy.context))
        for s in sketches:
            refresh_curve_geometry(s)  # force the GN modifiers to re-evaluate
        bpy.context.view_layer.update()
        dg = bpy.context.evaluated_depsgraph_get()

        ours = {s.target_object.original for s in sketches}
        total_v = 0
        lo = [1e18] * 3
        hi = [-1e18] * 3
        for inst in dg.object_instances:
            if inst.object.original not in ours:
                continue
            try:
                me = inst.object.to_mesh()
            except RuntimeError:
                continue  # the Curves object itself yields no mesh
            if len(me.vertices):
                mw = inst.matrix_world
                for v in me.vertices:
                    w = mw @ v.co
                    for i in range(3):
                        lo[i] = min(lo[i], w[i])
                        hi[i] = max(hi[i], w[i])
                total_v += len(me.vertices)
            inst.object.to_mesh_clear()

        dims = [hi[i] - lo[i] for i in range(3)]
        # A substantial solid, not the flat sketch profile (Extrude + Booleans ran).
        # n-gon fills feed cleaner, lower-vertex geometry into the booleans than the
        # old triangulated fills did, so this stays a loose "not flat" floor -- the
        # bounds check below is the real 3D assertion.
        self.assertGreater(total_v, 500)
        # Overall bounds match the legacy dimensions; each axis is real 3D depth.
        for got, want in zip(dims, (150.0, 80.0, 100.0)):
            self.assertAlmostEqual(got, want, delta=1.0)

    def test_idempotent(self):
        # Re-running migration on an already-migrated scene is a no-op.
        from ..utilities.migrate import migrate_scene, scene_needs_migration

        _open("simple_line.blend")
        self.assertFalse(scene_needs_migration(bpy.context))  # already auto-migrated
        before = len(list(get_sketches(bpy.context)))
        migrate_scene(bpy.context)
        self.assertEqual(len(list(get_sketches(bpy.context))), before)
