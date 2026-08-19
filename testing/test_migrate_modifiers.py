"""Translating a legacy mesh modifier stack to GN siblings on a new sketch.

Drives the per-modifier translators and the ``_migrate_modifiers`` driver
directly (setting up a full legacy scene is heavy). Verifies that translatable
modifiers become the addon's node tools with mapped parameters, and that
unsupported modifiers are skipped and recorded.
"""

from ..operators.modifiers import View3D_OT_node_boolean, get_modifier_input
from ..utilities.migrate import _migrate_modifiers
from .utils import Sketch2dTestCase


class TestMigrateModifiers(Sketch2dTestCase):
    def _old_mesh(self):
        # A legacy-style generated output mesh to carry the modifier stack.
        me = self.data.meshes.new("old_output")
        import bmesh

        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=2.0)
        bm.to_mesh(me)
        bm.free()
        obj = self.data.objects.new("old_output", me)
        self.scene.collection.objects.link(obj)
        return obj

    def _run(self, old_mesh):
        summary = {"modifiers": 0, "modifiers_skipped": []}
        _migrate_modifiers(old_mesh, self.sketch, summary)
        return summary

    def _sketch_mods(self):
        return [m for m in self.sketch.target_object.modifiers if m.type == "NODES"]

    def test_solidify_becomes_extrude(self):
        old = self._old_mesh()
        s = old.modifiers.new("s", "SOLIDIFY")
        s.thickness = 0.3
        summary = self._run(old)
        self.assertEqual(summary["modifiers"], 1)
        self.assertEqual(summary["modifiers_skipped"], [])
        extrude = next(
            m
            for m in self._sketch_mods()
            if m.node_group.name == "CAD Sketcher Extrude"
        )
        self.assertAlmostEqual(get_modifier_input(extrude, "Input_2"), 0.3, places=5)

    def test_boolean_becomes_boolean_node_group(self):
        old = self._old_mesh()
        cutter = self._old_mesh()
        cutter.name = "the_cutter"
        b = old.modifiers.new("b", "BOOLEAN")
        b.object = cutter
        b.operation = "UNION"
        summary = self._run(old)
        self.assertEqual(summary["modifiers"], 1)
        mod = next(
            m
            for m in self._sketch_mods()
            if m.node_group.name == "CAD Sketcher Boolean"
        )
        ids = View3D_OT_node_boolean._input_ids(mod.node_group)
        self.assertEqual(get_modifier_input(mod, ids["Cutter"]), cutter)
        self.assertEqual(int(get_modifier_input(mod, ids["Operation"])), 1)  # Union

    def test_boolean_without_cutter_is_skipped(self):
        old = self._old_mesh()
        old.modifiers.new("b", "BOOLEAN")  # no object set
        summary = self._run(old)
        self.assertEqual(summary["modifiers"], 0)
        self.assertEqual(len(summary["modifiers_skipped"]), 1)

    def test_array_becomes_linear_array(self):
        old = self._old_mesh()
        a = old.modifiers.new("a", "ARRAY")
        a.count = 4
        a.use_relative_offset = False
        a.use_constant_offset = True
        a.constant_offset_displace = (3.0, 0.0, 0.0)
        summary = self._run(old)
        self.assertEqual(summary["modifiers"], 1)
        arr = next(
            m
            for m in self._sketch_mods()
            if m.node_group.name == "CAD Sketcher Linear Array"
        )
        self.assertEqual(int(get_modifier_input(arr, "Input_22")), 4)  # Count
        self.assertAlmostEqual(get_modifier_input(arr, "Input_23"), 3.0, places=4)

    def test_screw_becomes_revolve(self):
        import math

        old = self._old_mesh()
        s = old.modifiers.new("sc", "SCREW")
        s.axis = "Y"
        s.angle = math.pi  # 180 degrees
        s.steps = 12
        summary = self._run(old)
        self.assertEqual(summary["modifiers"], 1)
        rev = next(
            m
            for m in self._sketch_mods()
            if m.node_group.name == "CAD Sketcher Revolve"
        )
        self.assertAlmostEqual(get_modifier_input(rev, "Socket_3"), math.pi, places=4)
        # Axis Direction is Y.
        axis = tuple(get_modifier_input(rev, "Socket_2"))
        self.assertLess(abs(axis[1] - 1.0), 1e-4)
        self.assertAlmostEqual(
            get_modifier_input(rev, "Socket_4"), math.pi / 12, places=4
        )

    def _sketch_group_named(self, name):
        return next((m for m in self._sketch_mods() if m.node_group.name == name), None)

    def test_weld_becomes_merge_by_distance(self):
        old = self._old_mesh()
        w = old.modifiers.new("w", "WELD")
        w.merge_threshold = 0.05
        summary = self._run(old)
        self.assertEqual(summary["modifiers"], 1)
        mod = self._sketch_group_named("CAD_Sketcher Weld")
        self.assertIsNotNone(mod)
        merge = next(n for n in mod.node_group.nodes if n.type == "MERGE_BY_DISTANCE")
        self.assertAlmostEqual(merge.inputs["Distance"].default_value, 0.05, places=5)

    def test_subsurf_becomes_subdivision(self):
        old = self._old_mesh()
        old.modifiers.new("s", "SUBSURF").levels = 3
        summary = self._run(old)
        self.assertEqual(summary["modifiers"], 1)
        mod = self._sketch_group_named("CAD_Sketcher Subdivision")
        self.assertIsNotNone(mod)
        sub = next(n for n in mod.node_group.nodes if n.type == "SUBDIVISION_SURFACE")
        self.assertEqual(int(sub.inputs["Level"].default_value), 3)

    def test_triangulate_translates(self):
        old = self._old_mesh()
        old.modifiers.new("t", "TRIANGULATE")
        summary = self._run(old)
        self.assertEqual(summary["modifiers"], 1)
        self.assertIsNotNone(self._sketch_group_named("CAD_Sketcher Triangulate"))

    def test_mirror_axis_translates(self):
        old = self._old_mesh()
        mi = old.modifiers.new("mi", "MIRROR")
        mi.use_axis = (True, False, False)
        summary = self._run(old)
        self.assertEqual(summary["modifiers"], 1)
        mod = self._sketch_group_named("CAD_Sketcher Mirror")
        self.assertIsNotNone(mod)
        # The construction includes a transform (scale -1) and a flip-faces.
        types = {n.type for n in mod.node_group.nodes}
        self.assertIn("TRANSFORM_GEOMETRY", types)
        self.assertIn("FLIP_FACES", types)

    def test_mirror_object_is_skipped(self):
        old = self._old_mesh()
        pivot = self._old_mesh()
        mi = old.modifiers.new("mi", "MIRROR")
        mi.mirror_object = pivot
        summary = self._run(old)
        self.assertEqual(summary["modifiers"], 0)
        self.assertEqual(len(summary["modifiers_skipped"]), 1)

    def test_bevel_is_skipped_with_record(self):
        # Bevel has no GN equivalent; it must be skipped and recorded.
        old = self._old_mesh()
        old.modifiers.new("bev", "BEVEL")
        summary = self._run(old)
        self.assertEqual(summary["modifiers"], 0)
        self.assertEqual(len(summary["modifiers_skipped"]), 1)
        self.assertIn("BEVEL", summary["modifiers_skipped"][0])

    def test_stack_order_and_mixed(self):
        # A mixed stack: solidify + boolean translate, bevel is skipped, order
        # preserved among the translated ones.
        old = self._old_mesh()
        cutter = self._old_mesh()
        old.modifiers.new("s", "SOLIDIFY").thickness = 0.1
        old.modifiers.new("bev", "BEVEL")
        old.modifiers.new("b", "BOOLEAN").object = cutter
        summary = self._run(old)
        self.assertEqual(summary["modifiers"], 2)
        self.assertEqual(len(summary["modifiers_skipped"]), 1)
        groups = [m.node_group.name for m in self._sketch_mods()]
        self.assertLess(
            groups.index("CAD Sketcher Extrude"),
            groups.index("CAD Sketcher Boolean"),
            "translated modifiers keep their original order",
        )
