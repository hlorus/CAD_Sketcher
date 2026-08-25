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

    def _gn_solid(self, name, center, half=1.0):
        """A Curves object whose GN modifier OUTPUTS a cube.

        Mimics an extruded/revolved sketch: the solid is Geometry-Nodes output on
        a non-mesh object, so ``to_mesh``/``new_from_object`` raise on it and
        detection must read the GN mesh from the depsgraph instance instead.
        """
        curves = self.data.hair_curves.new(name)
        obj = self.data.objects.new(name, curves)
        self.scene.collection.objects.link(obj)
        ng = self.data.node_groups.new(name + "_ng", "GeometryNodeTree")
        ng.interface.new_socket(
            "Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry"
        )
        out = ng.nodes.new("NodeGroupOutput")
        cube = ng.nodes.new("GeometryNodeMeshCube")
        cube.inputs["Size"].default_value = (2 * half, 2 * half, 2 * half)
        xf = ng.nodes.new("GeometryNodeTransform")
        xf.inputs["Translation"].default_value = center
        ng.links.new(cube.outputs["Mesh"], xf.inputs["Geometry"])
        ng.links.new(xf.outputs["Geometry"], out.inputs["Geometry"])
        obj.modifiers.new("Convert", "NODES").node_group = ng
        self.context.view_layer.update()
        return obj

    def test_overlapping_bodies_finds_only_intersecting(self):
        cutter = self._box("Cutter", (0, 0, 0))  # [-1,1]^3
        overlap = self._box("Overlap", (1, 1, 1))  # [0,2]^3, interpenetrates
        far = self._box("Far", (10, 0, 0))  # disjoint
        depsgraph = self.context.evaluated_depsgraph_get()

        hits = overlapping_bodies(cutter, [overlap, far], depsgraph)
        self.assertEqual(hits, [overlap])

    def test_gn_solid_cutter_overlaps_multiple_bodies(self):
        # The real case: the cutter is a Curves object whose modifier OUTPUTS the
        # solid (an extruded sketch). to_mesh() gives nothing for it, so detection
        # must evaluate the GN geometry -- and it must find EVERY overlapping body,
        # not just one (the "only detects one target" bug).
        # The bodies poke transversally through the rod's side faces (half 0.5,
        # so they cross rather than sit flush -- BVHTree.overlap needs a crossing).
        cutter = self._gn_solid("Rod", (0.0, 0.0, 0.0))  # [-1,1]^3
        b1 = self._box("B1", (1, 0, 0), half=0.5)  # crosses +X face
        b2 = self._box("B2", (0, 1, 0), half=0.5)  # crosses +Y face
        far = self._box("Far", (0, 0, 6), half=0.5)  # disjoint
        depsgraph = self.context.evaluated_depsgraph_get()

        hits = overlapping_bodies(cutter, [b1, b2, far], depsgraph)
        self.assertEqual(set(hits), {b1, b2}, "must find both overlapping bodies")

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

    def test_detect_then_apply_adds_boolean_to_overlapping_body(self):
        # The core of finish_booleans: auto-detected targets get a boolean of the
        # cutter (here without a source body, so overlap alone drives it).
        from ..operators.modifiers import apply_boolean, boolean_modifier_name
        from ..utilities.boolean_targets import detect_targets

        cutter = self._box("Cutter", (0, 0, 0))  # [-1,1]^3
        body = self._box("Body", (1, 1, 1))  # overlaps
        far = self._box("Far", (10, 0, 0))  # does not

        targets = detect_targets(self.context, cutter, None)
        self.assertIn(body, targets)
        self.assertNotIn(far, targets)
        self.assertNotIn(cutter, targets)

        for t in targets:
            apply_boolean(t, cutter, "Difference")
        self.assertIsNotNone(
            body.modifiers.get(boolean_modifier_name(cutter)),
            "the overlapping body must receive the cutter's boolean",
        )
        self.assertIsNone(far.modifiers.get(boolean_modifier_name(cutter)))
