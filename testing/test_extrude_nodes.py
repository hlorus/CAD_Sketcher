"""The code-built ``CAD Sketcher Extrude`` node group.

Replaces the binary asset that used to ship in ``resources/assets.blend``. The
snapshot cases below were captured from that asset before it was removed, so they
pin the migration to byte-for-byte identical output (vertex/edge/face counts and
total surface area) across the filled face path, the wire wall path, and the
sign / mirror / asymmetry switches.
"""

import bpy

from ..operators.modifiers import View3D_OT_node_extrude, set_modifier_input
from ..utilities.extrude_nodes import (
    EXTRUDE_NODE_GROUP,
    EXTRUDE_VERSION,
    build_extrude_node_group,
    ensure_extrude_edge_walls,
)
from .utils import BgsTestCase


def _grid_2x2():
    """3x3 vertices, 4 coplanar quads sharing internal edges (a filled profile
    whose interior edges make ``Individual`` extrude visibly wrong if set)."""
    verts = [(x * 2.0, y * 2.0, 0.0) for y in range(3) for x in range(3)]
    faces = []
    for gy in range(2):
        for gx in range(2):
            a = gy * 3 + gx
            faces.append((a, a + 1, a + 4, a + 3))
    mesh = bpy.data.meshes.new("grid")
    mesh.from_pydata(verts, [], faces)
    obj = bpy.data.objects.new("grid", mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def _wire():
    """An open polyline (edges, no faces): exercises the edge-wall path."""
    mesh = bpy.data.meshes.new("wire")
    mesh.from_pydata([(0, 0, 0), (2, 0, 0), (2, 2, 0)], [(0, 1), (1, 2)], [])
    obj = bpy.data.objects.new("wire", mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


class TestExtrudeNodeGroup(BgsTestCase):
    def _group(self):
        group = build_extrude_node_group()
        ensure_extrude_edge_walls(group)
        return group

    def _stats(self, profile, **inputs):
        group = self._group()
        obj = profile()
        try:
            mod = obj.modifiers.new("E", "NODES")
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
            stats = (
                len(mesh.vertices),
                len(mesh.edges),
                len(mesh.polygons),
                round(sum(p.area for p in mesh.polygons), 4),
            )
            evaluated.to_mesh_clear()
            return stats
        finally:
            bpy.data.objects.remove(obj, do_unlink=True)

    # -- build contract ---------------------------------------------------

    def test_build_is_idempotent(self):
        first = build_extrude_node_group()
        self.assertEqual(first.get("cad_extrude_version"), EXTRUDE_VERSION)
        self.assertIs(build_extrude_node_group(), first)
        self.assertEqual(first.name, EXTRUDE_NODE_GROUP)

    def test_stale_version_rebuilds_in_place(self):
        group = build_extrude_node_group()
        group["cad_extrude_version"] = EXTRUDE_VERSION - 1
        rebuilt = build_extrude_node_group()
        self.assertIs(rebuilt, group)
        self.assertEqual(rebuilt.get("cad_extrude_version"), EXTRUDE_VERSION)

    def test_operator_socket_contract(self):
        # Names the operator's set_props writes (Size etc.) must exist by name;
        # the framework binds them by identifier at runtime.
        group = build_extrude_node_group()
        names = {
            s.name
            for s in group.interface.items_tree
            if getattr(s, "in_out", "") == "INPUT"
        }
        for name in (
            "Size",
            "Mirror Extrude",
            "Asymmetry Override",
            "Asymmetry Distance",
        ):
            self.assertIn(name, names)
        self.assertIs(View3D_OT_node_extrude.resources, ())

    # -- geometry snapshots (captured from the retired asset) -------------

    def test_filled_simple_extrude(self):
        self.assertEqual(self._stats(_grid_2x2, Size=0.6), (18, 32, 16, 41.6))

    def test_filled_negative_size_matches_positive(self):
        # The sign only flips which cap is reversed; the solid is identical.
        self.assertEqual(self._stats(_grid_2x2, Size=-0.6), (18, 32, 16, 41.6))

    def test_filled_mirror_extrude(self):
        self.assertEqual(
            self._stats(_grid_2x2, Size=0.6, **{"Mirror Extrude": True}),
            (26, 48, 24, 51.2),
        )

    def test_filled_asymmetric_extrude(self):
        self.assertEqual(
            self._stats(
                _grid_2x2,
                Size=0.6,
                **{"Asymmetry Override": True, "Asymmetry Distance": 0.3},
            ),
            (26, 48, 24, 46.4),
        )

    def test_wire_profile_makes_walls(self):
        self.assertEqual(self._stats(_wire, Size=0.6), (6, 7, 2, 2.4))

    def test_wire_profile_mirror_walls(self):
        self.assertEqual(
            self._stats(_wire, Size=0.6, **{"Mirror Extrude": True}),
            (9, 12, 4, 4.8),
        )
