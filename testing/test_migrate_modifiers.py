"""Carrying a legacy mesh modifier stack over to a new sketch.

Drives the per-modifier translators and the ``_migrate_modifiers`` driver
directly (setting up a full legacy scene is heavy). Verifies that a modifier
standing for one of this addon's tools becomes that tool with mapped
parameters, that a plain mesh modifier is kept as itself, and that anything
else is skipped and recorded.
"""

from ..operators.modifiers import boolean_input_ids, get_modifier_input
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

    def _target(self):
        """Where a migrated stack lands: the body the sketch is realised on."""
        from ..utilities.body import body_of

        return body_of(self.sketch.target_object)

    def _run(self, old_mesh):
        summary = {"modifiers": 0, "modifiers_skipped": []}
        _migrate_modifiers(old_mesh, self.sketch, summary)
        return summary

    def _sketch_mods(self):
        return [m for m in self._target().modifiers if m.type == "NODES"]

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
        from ..utilities.extrude_nodes import _input_ids

        ids = _input_ids(extrude.node_group)
        self.assertAlmostEqual(get_modifier_input(extrude, ids["Size"]), 0.3, places=5)

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
        ids = boolean_input_ids(mod.node_group)
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
        from ..utilities.array_nodes import _input_ids

        ids = _input_ids(arr.node_group)
        self.assertEqual(int(get_modifier_input(arr, ids["Count"])), 4)
        self.assertAlmostEqual(
            get_modifier_input(arr, ids["Spacing / Total distance"]), 3.0, places=4
        )

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
        from ..utilities.revolve_nodes import _input_ids

        ids = _input_ids(rev.node_group)
        self.assertAlmostEqual(get_modifier_input(rev, ids["Angle"]), math.pi, places=4)
        # Axis Direction is Y.
        axis = tuple(get_modifier_input(rev, ids["Axis Direction"]))
        self.assertLess(abs(axis[1] - 1.0), 1e-4)
        self.assertAlmostEqual(
            get_modifier_input(rev, ids["Angular Resolution"]), math.pi / 12, places=4
        )

    def test_weld_is_kept_as_it_is(self):
        old = self._old_mesh()
        old.modifiers.new("w", "WELD").merge_threshold = 0.05

        summary = self._run(old)

        self.assertEqual(summary["modifiers"], 1)
        kept = self._target().modifiers["w"]
        self.assertEqual(kept.type, "WELD")
        self.assertAlmostEqual(kept.merge_threshold, 0.05, places=5)

    def test_subsurf_is_kept_as_it_is(self):
        old = self._old_mesh()
        old.modifiers.new("s", "SUBSURF").levels = 3

        summary = self._run(old)

        self.assertEqual(summary["modifiers"], 1)
        kept = self._target().modifiers["s"]
        self.assertEqual(kept.type, "SUBSURF")
        self.assertEqual(kept.levels, 3)

    def test_triangulate_is_kept_as_it_is(self):
        old = self._old_mesh()
        old.modifiers.new("t", "TRIANGULATE")

        summary = self._run(old)

        self.assertEqual(summary["modifiers"], 1)
        self.assertEqual(self._target().modifiers["t"].type, "TRIANGULATE")

    def test_mirror_is_kept_as_it_is(self):
        # Rebuilt in nodes it could not be made again from scratch, since there
        # is no Mirror tool and none is wanted: it is Blender's own modifier on
        # what is now a mesh (issue #740).
        old = self._old_mesh()
        mi = old.modifiers.new("mi", "MIRROR")
        mi.use_axis = (True, False, True)
        mi.merge_threshold = 0.01

        summary = self._run(old)

        self.assertEqual(summary["modifiers"], 1)
        kept = self._target().modifiers["mi"]
        self.assertEqual(kept.type, "MIRROR")
        self.assertEqual(tuple(kept.use_axis), (True, False, True))
        self.assertAlmostEqual(kept.merge_threshold, 0.01, places=5)

    def test_a_mirror_about_another_object_is_kept_too(self):
        # It was skipped for having no clean node equivalent; as itself it needs
        # none, and the pivot comes with it.
        old = self._old_mesh()
        pivot = self._old_mesh()
        mi = old.modifiers.new("mi", "MIRROR")
        mi.mirror_object = pivot

        summary = self._run(old)

        self.assertEqual(summary["modifiers"], 1)
        self.assertEqual(self._target().modifiers["mi"].mirror_object, pivot)

    def test_a_bevel_is_kept_instead_of_being_dropped(self):
        old = self._old_mesh()
        old.modifiers.new("b", "BEVEL").width = 0.25

        summary = self._run(old)

        self.assertEqual(summary["modifiers"], 1)
        self.assertEqual(summary["modifiers_skipped"], [])
        self.assertAlmostEqual(self._target().modifiers["b"].width, 0.25, places=5)

    def test_a_modifier_with_no_answer_is_still_skipped(self):
        # Cloth is neither one of this addon's tools nor a plain mesh modifier
        # to carry over.
        old = self._old_mesh()
        old.modifiers.new("cloth", "CLOTH")

        summary = self._run(old)

        self.assertEqual(summary["modifiers"], 0)
        self.assertEqual(len(summary["modifiers_skipped"]), 1)
        self.assertIn("CLOTH", summary["modifiers_skipped"][0])

    def test_stack_order_and_mixed(self):
        # A mixed stack: solidify + boolean translate, cloth is skipped, order
        # preserved among the translated ones.
        old = self._old_mesh()
        cutter = self._old_mesh()
        old.modifiers.new("s", "SOLIDIFY").thickness = 0.1
        old.modifiers.new("cloth", "CLOTH")
        old.modifiers.new("b", "BOOLEAN").object = cutter
        summary = self._run(old)
        self.assertEqual(summary["modifiers"], 2)
        self.assertEqual(len(summary["modifiers_skipped"]), 1)
        groups = [m.node_group.name for m in self._sketch_mods() if m.node_group]
        self.assertLess(
            groups.index("CAD Sketcher Extrude"),
            groups.index("CAD Sketcher Boolean"),
            "translated modifiers keep their original order",
        )
