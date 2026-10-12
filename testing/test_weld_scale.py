"""The weld must not care how big the sketch is.

Reported by two users on Blender 5.1: a rectangle fills correctly while it is
small and turns into a triangle with half the area once it is enlarged. Below
5.2 the converter welded coincident endpoints by distance with a fixed 1e-6
threshold, and that stops merging bit-identical points at a coordinate
magnitude of about 20, splitting the loop (see _weld_by_parking).

These force the pre-5.2 branch so the behaviour is covered on any Blender.
"""

import bpy

from ..utilities import convert_nodes as cn
from ..utilities.curve_data import refresh_curve_geometry
from .utils import Sketch2dTestCase

SIZES = (1, 5, 20, 50, 200, 1000, 5000)


class TestWeldScale(Sketch2dTestCase):
    def setUp(self):
        super().setUp()
        self._native = cn._identity_weld_available

    def tearDown(self):
        cn._identity_weld_available = self._native
        self._rebuild()
        super().tearDown()

    def _rebuild(self):
        """Rebuild the shared group in place, keeping modifier bindings."""
        ng = bpy.data.node_groups.get(cn.CONVERT_NODE_GROUP)
        if ng is not None:
            ng["cad_convert_version"] = 0
        cn.build_convert_node_group()

    def _use_legacy_weld(self):
        cn._identity_weld_available = lambda: False
        self._rebuild()

    def _rect(self, size):
        sc = self.sketch.constraints
        corners = [(0, 0), (size, 0), (size, size), (0, size)]
        pts = [self.add_point(c) for c in corners]
        for i in range(4):
            line = self.add_line(pts[i], pts[(i + 1) % 4])
            add = sc.add_horizontal if (i % 2) == 0 else sc.add_vertical
            add(curve_id_1=line.curve_id)

    def _clear(self):
        cd = self.sketch.target_object.data
        if len(cd.curves):
            cd.remove_curves(indices=list(range(len(cd.curves))))
        refresh_curve_geometry(self.sketch)

    def _converted(self):
        """The real generated mesh: (faces, per-face vertex counts, area, attrs)."""
        ob = self.sketch.target_object
        scene = self.context.scene
        dup = ob.copy()
        dup.data = ob.data.copy()
        scene.collection.objects.link(dup)
        for other in scene.collection.objects:
            other.select_set(False)
        dup.select_set(True)
        self.context.view_layer.objects.active = dup
        bpy.ops.object.convert(target="MESH")
        mesh = dup.data
        if not hasattr(mesh, "polygons"):
            bpy.data.objects.remove(dup, do_unlink=True)
            return 0, [], 0.0, []
        out = (
            len(mesh.polygons),
            sorted(len(p.vertices) for p in mesh.polygons),
            sum(p.area for p in mesh.polygons),
            [a.name for a in mesh.attributes],
        )
        bpy.data.objects.remove(dup, do_unlink=True)
        return out

    def test_a_rectangle_fills_at_every_size(self):
        self._use_legacy_weld()
        for size in SIZES:
            with self.subTest(size=size):
                self._clear()
                self._rect(size)
                self.solve()
                refresh_curve_geometry(self.sketch)
                faces, verts, area, _attrs = self._converted()
                self.assertEqual(faces, 1, f"size {size}: expected one face")
                self.assertEqual(verts, [4], f"size {size}: lost a corner")
                self.assertAlmostEqual(
                    area, float(size) ** 2, delta=float(size) ** 2 * 0.001
                )

    def test_the_native_weld_fills_at_every_size(self):
        """The 5.2 path, for comparison; skipped where the node is absent."""
        if not self._native():
            self.skipTest("Merge Points needs Blender 5.2")
        # Another test may have left the shared group built some other way.
        self._rebuild()
        for size in SIZES:
            with self.subTest(size=size):
                self._clear()
                self._rect(size)
                self.solve()
                refresh_curve_geometry(self.sketch)
                faces, verts, area, _attrs = self._converted()
                self.assertEqual((faces, verts), (1, [4]), f"size {size}: area={area}")

    def test_the_parked_position_does_not_leak_out(self):
        """It is scaffolding for the weld, not something the body should carry."""
        self._use_legacy_weld()
        self._clear()
        self._rect(200)
        self.solve()
        refresh_curve_geometry(self.sketch)
        _faces, _verts, _area, attrs = self._converted()
        self.assertNotIn(cn.PARKED_POSITION_ATTR, attrs)

    def test_rebuilding_keeps_the_modifier_inputs(self):
        """A version bump rebuilds the group; Fill must survive it (see #707)."""
        from ..operators.modifiers import get_modifier_input, set_modifier_input

        ob = self.sketch.target_object
        mod = next(
            m
            for m in ob.modifiers
            if getattr(m, "node_group", None)
            and m.node_group.name.startswith(cn.CONVERT_NODE_GROUP)
        )
        socket = next(
            item
            for item in cn._input_sockets(mod.node_group)
            if item.name == cn.ANGULAR_RESOLUTION_INPUT
        )
        set_modifier_input(mod, socket.identifier, 12.0)

        self._use_legacy_weld()

        socket = next(
            item
            for item in cn._input_sockets(mod.node_group)
            if item.name == cn.ANGULAR_RESOLUTION_INPUT
        )
        self.assertAlmostEqual(get_modifier_input(mod, socket.identifier), 12.0)
