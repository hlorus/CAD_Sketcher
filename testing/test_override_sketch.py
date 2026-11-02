"""Stateful tools on a scene that holds an overridden sketch (#802).

An override of a sketch's Curves data refuses ``add()``/``remove()`` on its
constraint collections, so rolling the tools' previews back used to raise as
soon as such a sketch sat in the scene, even when the tool was working on a
different, local sketch.
"""

from ..model.sketch_ref import is_sketch_object, set_active_sketch
from ..operators.add_circle import View3D_OT_slvs_add_circle2d
from ..operators.base_stateful import GenericEntityOp
from ..utilities.collections import is_editable
from .utils import Sketch2dTestCase, make_operator_double


def _sketch_state(obj):
    data = obj.data
    return len(data.curves), len(data.points), len(data.sketch_constraints.distance)


class TestOverriddenSketchRestore(Sketch2dTestCase):
    def test_fixture_is_an_override_with_overridden_data(self):
        override = self.library_sketch(override_data=True)
        self.assertTrue(is_sketch_object(override))
        self.assertIsNotNone(override.data.override_library)
        self.assertFalse(is_editable(override.data))
        self.assertEqual(_sketch_state(override)[2], 1)

    def test_full_restore_with_an_override_in_the_scene(self):
        self.add_dimensioned_line()
        override = self.library_sketch(override_data=True)
        before = _sketch_state(self.sketch.target_object)
        op = make_operator_double(GenericEntityOp)()
        snapshot = op.create_snapshot(self.context)

        self.add_dimensioned_line()
        op.restore_snapshot(self.context, snapshot)

        self.assertEqual(_sketch_state(self.sketch.target_object), before)
        self.assertEqual(_sketch_state(override)[2], 1)

    def test_active_override_sketch_is_left_alone_by_the_2d_restore(self):
        override = self.library_sketch(override_data=True)
        set_active_sketch(self.context, override)
        op = make_operator_double(View3D_OT_slvs_add_circle2d)()
        snapshot = op.create_snapshot(self.context)

        op.restore_snapshot(self.context, snapshot)

        self.assertEqual(_sketch_state(override)[2], 1)

    def test_a_linked_sketch_is_not_written_through_a_local_namesake(self):
        linked = self.library_sketch()
        self.add_dimensioned_line()
        self.add_line(self.add_point((0, 3)), self.add_point((4, 3)))
        self.sketch.target_object.name = linked.name
        linked_before = _sketch_state(linked)
        local_before = _sketch_state(self.sketch.target_object)
        op = make_operator_double(GenericEntityOp)()
        snapshot = op.create_snapshot(self.context)

        op.restore_snapshot(self.context, snapshot)

        self.assertEqual(_sketch_state(linked), linked_before)
        self.assertEqual(_sketch_state(self.sketch.target_object), local_before)
