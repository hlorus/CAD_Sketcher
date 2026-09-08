"""The code-built ``CAD Sketcher Linear Array`` node group.

Replaces the binary asset that used to ship in ``resources/assets.blend``. The
snapshot cases were captured from that asset before it was removed, so they pin
the migration to identical output (vertex/edge/face counts and total surface area)
across count/spacing, direction, flip, total-distance, align-rotation, realize,
show-axes and merge.
"""

import bmesh
import bpy

from ..operators.modifiers import View3D_OT_node_array_linear, set_modifier_input
from ..utilities.array_nodes import (
    ARRAY_NODE_GROUP,
    ARRAY_VERSION,
    build_array_node_group,
)
from .utils import BgsTestCase


def _cube():
    mesh = bpy.data.meshes.new("cube")
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new("cube", mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


class TestArrayNodeGroup(BgsTestCase):
    def _stats(self, **inputs):
        group = build_array_node_group()
        obj = _cube()
        try:
            mod = obj.modifiers.new("A", "NODES")
            mod.node_group = group
            ids = {
                s.name: s.identifier
                for s in group.interface.items_tree
                if getattr(s, "in_out", "") == "INPUT"
            }
            for name, value in inputs.items():
                set_modifier_input(mod, ids[name], value)
            bpy.context.view_layer.update()
            evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
            mesh = evaluated.to_mesh()
            counts = (len(mesh.vertices), len(mesh.edges), len(mesh.polygons))
            area = sum(p.area for p in mesh.polygons)
            evaluated.to_mesh_clear()
            return counts, round(area, 4)
        finally:
            bpy.data.objects.remove(obj, do_unlink=True)

    # -- build contract ---------------------------------------------------

    def test_build_is_idempotent(self):
        first = build_array_node_group()
        self.assertEqual(first.get("cad_array_version"), ARRAY_VERSION)
        self.assertIs(build_array_node_group(), first)
        self.assertEqual(first.name, ARRAY_NODE_GROUP)

    def test_stale_version_rebuilds_in_place(self):
        group = build_array_node_group()
        group["cad_array_version"] = ARRAY_VERSION - 1
        rebuilt = build_array_node_group()
        self.assertIs(rebuilt, group)
        self.assertEqual(rebuilt.get("cad_array_version"), ARRAY_VERSION)

    def test_operator_socket_contract(self):
        group = build_array_node_group()
        names = {
            s.name
            for s in group.interface.items_tree
            if getattr(s, "in_out", "") == "INPUT"
        }
        for name in (
            "Direction",
            "Count",
            "Spacing / Total distance",
            "Use Total Distance",
            "Align Rotation",
            "Merge by Distance",
            "Merge Distance",
            "Flip Direciton",
        ):
            self.assertIn(name, names)
        self.assertIs(View3D_OT_node_array_linear.resources, ())

    # -- geometry snapshots (captured from the retired asset) -------------

    def test_default_count_spacing(self):
        counts, area = self._stats(**{"Count": 5, "Spacing / Total distance": 3.0})
        self.assertEqual(counts, (40, 60, 30))
        self.assertAlmostEqual(area, 30.0, places=4)

    def test_direction_and_count(self):
        counts, area = self._stats(
            **{
                "Count": 3,
                "Spacing / Total distance": 2.0,
                "Direction": (1.0, 0.0, 0.0),
            }
        )
        self.assertEqual(counts, (24, 36, 18))
        self.assertAlmostEqual(area, 18.0, places=4)

    def test_flip_direction(self):
        counts, _ = self._stats(
            **{"Count": 4, "Spacing / Total distance": 3.0, "Flip Direciton": True}
        )
        self.assertEqual(counts, (32, 48, 24))

    def test_use_total_distance(self):
        counts, _ = self._stats(
            **{"Count": 4, "Spacing / Total distance": 9.0, "Use Total Distance": True}
        )
        self.assertEqual(counts, (32, 48, 24))

    def test_align_rotation(self):
        counts, area = self._stats(
            **{
                "Count": 5,
                "Spacing / Total distance": 3.0,
                "Align Rotation": True,
                "Direction": (1.0, 0.0, 1.0),
            }
        )
        self.assertEqual(counts, (40, 60, 30))
        self.assertAlmostEqual(area, 30.0, places=4)

    def test_realize_off_yields_no_realized_mesh(self):
        counts, _ = self._stats(
            **{"Count": 5, "Spacing / Total distance": 3.0, "Realize Instances": False}
        )
        self.assertEqual(counts, (0, 0, 0))

    def test_show_axes_adds_geometry(self):
        counts, _ = self._stats(
            **{"Count": 5, "Spacing / Total distance": 3.0, "Show Axies": True}
        )
        self.assertEqual(counts, (45, 64, 30))

    def test_merge_by_distance(self):
        counts, _ = self._stats(
            **{
                "Count": 6,
                "Spacing / Total distance": 3.0,
                "Merge by Distance": True,
                "Merge Distance": 0.01,
            }
        )
        self.assertEqual(counts, (48, 72, 36))
