"""Auto-detection of boolean targets and the default operation."""

import types

from ..utilities.boolean_targets import (
    default_operation,
    overlapping_bodies,
    sketch_source_body,
)
from ..utilities.face_anchor import KEY_SOURCE
from .utils import BgsTestCase

# Cube surface as 6 quads over vertices ordered by (x<y<z) sign bits.
_CUBE_FACES = [
    (0, 1, 3, 2),
    (4, 6, 7, 5),
    (0, 4, 5, 1),
    (2, 3, 7, 6),
    (0, 2, 6, 4),
    (1, 5, 7, 3),
]


class TestBooleanTargets(BgsTestCase):
    def _box(self, name, center, half=1.0):
        cx, cy, cz = center
        verts = [
            (cx + sx * half, cy + sy * half, cz + sz * half)
            for sx in (-1, 1)
            for sy in (-1, 1)
            for sz in (-1, 1)
        ]
        me = self.data.meshes.new(name)
        me.from_pydata(verts, [], _CUBE_FACES)
        me.update()
        ob = self.data.objects.new(name, me)
        self.scene.collection.objects.link(ob)
        self.context.view_layer.update()
        return ob

    def test_overlapping_bodies_finds_only_intersecting(self):
        cutter = self._box("Cutter", (0, 0, 0))  # [-1,1]^3
        overlap = self._box("Overlap", (1, 1, 1))  # [0,2]^3, interpenetrates
        far = self._box("Far", (10, 0, 0))  # disjoint
        depsgraph = self.context.evaluated_depsgraph_get()

        hits = overlapping_bodies(cutter, [overlap, far], depsgraph)
        self.assertEqual(hits, [overlap])

    def test_overlap_ignores_a_profile_with_no_solid(self):
        # A flat profile (no faces) can't participate: no BVH, no overlap.
        cutter = self._box("Cutter2", (0, 0, 0))
        me = self.data.meshes.new("FlatEdge")
        me.from_pydata([(0.0, 0.0, 0.0), (0.5, 0.0, 0.0)], [(0, 1)], [])
        me.update()
        flat = self.data.objects.new("FlatEdge", me)
        self.scene.collection.objects.link(flat)
        self.context.view_layer.update()
        depsgraph = self.context.evaluated_depsgraph_get()

        self.assertEqual(overlapping_bodies(cutter, [flat], depsgraph), [])

    def test_sketch_source_body_from_workplane_anchor(self):
        body = self._box("Body", (0, 0, 0))
        wp = self.data.objects.new("WP", None)  # empty
        self.scene.collection.objects.link(wp)
        wp[KEY_SOURCE] = body
        sketch = types.SimpleNamespace(workplane_object=wp, target_object=None)

        self.assertIs(sketch_source_body(sketch), body)

        # No anchor -> None.
        bare = types.SimpleNamespace(workplane_object=None, target_object=None)
        self.assertIsNone(sketch_source_body(bare))

    def test_default_operation_heuristic(self):
        # Push out from the sketched face adds material; push in removes it.
        self.assertEqual(default_operation(1.0, has_source_body=True), "Union")
        self.assertEqual(default_operation(-1.0, has_source_body=True), "Difference")
        # Without a source body to orient against, default to a cut.
        self.assertEqual(default_operation(1.0, has_source_body=False), "Difference")
