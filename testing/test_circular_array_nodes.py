"""The code-built CAD Sketcher Circular Array node group.

Repeats geometry around an axis, the circular counterpart of the linear array, so
these drive it on plain meshes: count, sweep angle, the axis and centre, and what
Align Rotation changes.
"""

import math
import unittest
from unittest import TestCase

import bpy


def _box(offset=(2.0, 0.0, 0.0), size=(0.2, 0.2, 0.2)):
    """A small box sitting ``offset`` from the object's origin.

    The offset lives in the mesh, not the object's transform: the array works in
    the object's local space, so geometry centred on the origin would only spin
    in place.
    """
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, 0.0, 0.0))
    ob = bpy.context.active_object
    for vertex in ob.data.vertices:
        vertex.co = [c * s + o for c, s, o in zip(vertex.co, size, offset)]
    return ob


class TestCircularArrayNodes(TestCase):
    def _add(self, ob, **values):
        from ..operators.modifiers import set_modifier_input
        from ..utilities.circular_array_nodes import (
            _input_ids,
            build_circular_array_node_group,
        )

        group = build_circular_array_node_group()
        mod = ob.modifiers.new("circular", "NODES")
        mod.node_group = group
        ids = _input_ids(group)
        for name, value in values.items():
            set_modifier_input(mod, ids[name], value)
        return mod, ids

    def _eval(self, ob):
        ob.update_tag()
        dg = bpy.context.evaluated_depsgraph_get()
        dg.update()
        me = ob.evaluated_get(dg).to_mesh()
        result = (
            len(me.vertices),
            len(me.polygons),
            [ob.matrix_world @ v.co for v in me.vertices],
        )
        ob.evaluated_get(dg).to_mesh_clear()
        return result

    def test_group_builds_with_the_expected_inputs(self):
        from ..utilities.circular_array_nodes import build_circular_array_node_group

        group = build_circular_array_node_group("test_circular_build")
        try:
            self.assertTrue(group.is_modifier)
            names = {s.name for s in group.interface.items_tree}
            for expected in (
                "Geometry",
                "Axis",
                "Center",
                "Count",
                "Angle / Total angle",
                "Use Total Angle",
                "Align Rotation",
                "Merge by Distance",
                "Merge Distance",
            ):
                self.assertIn(expected, names)
        finally:
            bpy.data.node_groups.remove(group)

    def test_count_copies_the_geometry(self):
        ob = _box()
        try:
            base_verts, base_faces, _ = self._eval(ob)
            self._add(ob, Count=4)
            verts, faces, _ = self._eval(ob)
            self.assertEqual(verts, base_verts * 4)
            self.assertEqual(faces, base_faces * 4)
        finally:
            bpy.data.objects.remove(ob, do_unlink=True)

    def test_a_full_turn_spreads_the_copies_evenly(self):
        """Four copies of a cube 2 away from the Z axis land on the four quadrants."""
        ob = _box()
        try:
            self._add(ob, Count=4)
            _verts, _faces, points = self._eval(ob)
            # One copy per quadrant, each about 2 from the axis.
            self.assertGreater(max(p.x for p in points), 1.8)
            self.assertLess(min(p.x for p in points), -1.8)
            self.assertGreater(max(p.y for p in points), 1.8)
            self.assertLess(min(p.y for p in points), -1.8)
        finally:
            bpy.data.objects.remove(ob, do_unlink=True)

    def test_a_partial_sweep_keeps_the_copies_within_it(self):
        ob = _box()
        try:
            self._add(ob, Count=3, **{"Angle / Total angle": math.pi / 2})
            _verts, _faces, points = self._eval(ob)
            # A quarter turn spread over three copies: none may cross into -X/-Y.
            self.assertGreater(min(p.x for p in points), -0.5)
            self.assertGreater(min(p.y for p in points), -0.5)
            self.assertGreater(max(p.y for p in points), 1.0, "the sweep does turn")
            self.assertLess(max(p.y for p in points), 2.1, "and not past the angle")
        finally:
            bpy.data.objects.remove(ob, do_unlink=True)

    def test_the_angle_is_the_step_without_use_total_angle(self):
        ob = _box()
        try:
            self._add(
                ob,
                Count=2,
                **{"Angle / Total angle": math.pi, "Use Total Angle": False},
            )
            _verts, _faces, points = self._eval(ob)
            # Two copies half a turn apart: one at +X, one at -X.
            self.assertGreater(max(p.x for p in points), 1.0)
            self.assertLess(min(p.x for p in points), -1.0)
        finally:
            bpy.data.objects.remove(ob, do_unlink=True)

    def test_the_axis_and_centre_decide_the_ring(self):
        """Around X through the origin, the copies ride in the YZ plane."""
        ob = _box(offset=(0.0, 2.0, 0.0))
        try:
            self._add(ob, Count=4, Axis=(1.0, 0.0, 0.0))
            _verts, _faces, points = self._eval(ob)
            self.assertLess(max(abs(p.x) for p in points), 0.5, "no travel along X")
            self.assertGreater(max(p.z for p in points), 1.0, "a copy turned up")
            self.assertLess(min(p.z for p in points), -1.0, "and one down")
        finally:
            bpy.data.objects.remove(ob, do_unlink=True)

    def test_align_rotation_turns_the_copies_with_the_pattern(self):
        """A bolt circle turns each copy; without it they keep their orientation."""
        # A bar, so its orientation is measurable: long along X, thin along Y.
        ob = _box(size=(0.8, 0.1, 0.1))
        try:
            mod, ids = self._add(ob, Count=4)
            _v, _f, aligned = self._eval(ob)
            from ..operators.modifiers import set_modifier_input

            set_modifier_input(mod, ids["Align Rotation"], False)
            _v, _f, free = self._eval(ob)

            def spread_y(points):
                """How far the copy standing on +Y reaches along X."""
                on_y = [p for p in points if p.y > 1.0]
                return max(p.x for p in on_y) - min(p.x for p in on_y)

            # The copy at +Y: turned with the pattern it is thin along X; kept
            # upright it stays wide along X.
            self.assertLess(spread_y(aligned), 0.3)
            self.assertGreater(spread_y(free), 0.7)
        finally:
            bpy.data.objects.remove(ob, do_unlink=True)

    def test_rebuilding_keeps_the_modifier_values(self):
        from ..operators.modifiers import get_modifier_input
        from ..utilities import circular_array_nodes

        ob = _box()
        try:
            mod, ids = self._add(ob, Count=7)
            group = mod.node_group
            group["cad_circular_array_version"] = -1  # force a rebuild
            circular_array_nodes.build_circular_array_node_group(group.name)
            ids = circular_array_nodes._input_ids(mod.node_group)
            self.assertEqual(get_modifier_input(mod, ids["Count"]), 7)
        finally:
            bpy.data.objects.remove(ob, do_unlink=True)


if __name__ == "__main__":
    unittest.main()
