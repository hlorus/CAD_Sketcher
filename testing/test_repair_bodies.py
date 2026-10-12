"""A body whose Convert modifier was deleted is reported, and repairable.

The modifier builds the body's geometry from its sketch. Deleting it in the
modifier panel is one click, nothing puts it back, and the node group is not
offered in Blender's own modifier menu, so the body stays empty with no way
out. It is not restored behind the user's back: it is reported, with a button.
"""

import bpy

from ..model.curve_ref import LineRef, PointRef
from ..operators.add_sketch import build_sketch_on_workplane
from ..utilities.body import (
    body_of,
    broken_bodies,
    convert_modifier_of,
    ensure_body,
    repair_body,
)
from ..utilities.curve_data import CONVERT_MODIFIER_NAME, refresh_curve_geometry
from ..utilities.workplane import ensure_origin_workplane_empties
from .utils import BgsTestCase


class TestRepairBodies(BgsTestCase):
    def setUp(self):
        super().setUp()
        self.entities.ensure_origin_elements(self.context)
        ensure_origin_workplane_empties(self.context)
        self.sketch = build_sketch_on_workplane(
            self.context, self.context.scene.sketcher.wp_xy
        )
        obj = self.sketch.target_object
        pts = [
            PointRef.create(self.sketch, c) for c in ((0, 0), (4, 0), (4, 4), (0, 4))
        ]
        for i in range(4):
            LineRef.create(self.sketch, pts[i], pts[(i + 1) % 4])
        refresh_curve_geometry(self.sketch)
        self.body = body_of(obj) or ensure_body(self.context, obj, "Body")
        self.context.view_layer.update()

    def _faces(self):
        depsgraph = self.context.evaluated_depsgraph_get()
        mesh = getattr(self.body.evaluated_get(depsgraph), "data", None)
        if mesh is None or not hasattr(mesh, "polygons"):
            return 0
        return len(mesh.polygons)

    def _delete_modifier(self):
        self.body.modifiers.remove(self.body.modifiers[CONVERT_MODIFIER_NAME])
        self.context.view_layer.update()

    def test_a_healthy_body_is_not_reported(self):
        self.assertIsNotNone(convert_modifier_of(self.body))
        self.assertNotIn(self.body, broken_bodies(self.scene))
        self.assertEqual(self._faces(), 1)

    def test_a_deleted_modifier_is_reported(self):
        self._delete_modifier()
        self.assertIsNone(convert_modifier_of(self.body))
        self.assertIn(self.body, broken_bodies(self.scene))
        self.assertEqual(self._faces(), 0, "the body should be empty")

    def test_a_modifier_pointed_at_nothing_is_reported(self):
        """Present but unwired looks identical to the user, so it counts."""
        self.body.modifiers[CONVERT_MODIFIER_NAME].node_group = None
        self.context.view_layer.update()
        self.assertIn(self.body, broken_bodies(self.scene))

    def test_repairing_rebuilds_the_geometry(self):
        self._delete_modifier()
        self.assertTrue(repair_body(self.context, self.body))
        self.context.view_layer.update()
        self.assertNotIn(self.body, broken_bodies(self.scene))
        self.assertEqual(self._faces(), 1, "the face did not come back")

    def test_the_operator_repairs_and_polls_off_when_healthy(self):
        self._delete_modifier()
        self.assertTrue(bpy.ops.view3d.slvs_repair_bodies.poll())
        bpy.ops.view3d.slvs_repair_bodies()
        self.context.view_layer.update()
        self.assertEqual(self._faces(), 1)
        self.assertNotIn(self.body, broken_bodies(self.scene))

    def test_nothing_is_repaired_behind_the_users_back(self):
        """A depsgraph pass must leave the deletion alone."""
        self._delete_modifier()
        refresh_curve_geometry(self.sketch)
        self.context.view_layer.update()
        self.assertIn(self.body, broken_bodies(self.scene))
