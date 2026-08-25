"""World-space geometry extraction for reference curve-object picking."""

import bpy

from ..drawing.reference_pick import element_geometry, extract_pickable_geometry
from .utils import Sketch2dTestCase


class TestReferencePickGeometry(Sketch2dTestCase):
    def test_sketch_extraction_keys_by_curve_id(self):
        # A sketch source is keyed by curve_id: standalone points and line
        # endpoints are pickable points, the line is a pickable segment.
        p0 = self.add_point((0.0, 0.0))
        p1 = self.add_point((2.0, 0.0))
        line = self.add_line(p0, p1)
        standalone = self.add_point((1.0, 1.0))

        points, segments = extract_pickable_geometry(self.sketch.target_object)
        pkeys = {k for k, _ in points}
        skeys = {k for k, _, _ in segments}

        self.assertIn(standalone.curve_id, pkeys)
        self.assertIn(p0.curve_id, pkeys)
        self.assertIn(p1.curve_id, pkeys)
        self.assertIn(line.curve_id, skeys)

    def test_arc_is_hoverable_as_tessellated_segments(self):
        # Arcs must be hoverable even though projection skips them: they come out
        # as several tessellated segments, all keyed by the arc's curve_id.
        ct = self.add_point((0.0, 0.0))
        start = self.add_point((1.0, 0.0))
        end = self.add_point((0.0, 1.0))
        arc = self.add_arc(ct, start, end)

        _, segments = extract_pickable_geometry(self.sketch.target_object)
        arc_segments = [k for k, _, _ in segments if k == arc.curve_id]
        self.assertGreater(len(arc_segments), 1)

    def test_raw_curves_object_extraction(self):
        # A raw Curves object (no sketch attributes) extracts control points and
        # the polyline between them, keyed by index.
        cu = bpy.data.hair_curves.new("raw")
        cu.add_curves([3])
        coords = ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0))
        for i, co in enumerate(coords):
            cu.points[i].position = co
        obj = bpy.data.objects.new("raw", cu)
        self.scene.collection.objects.link(obj)

        points, segments = extract_pickable_geometry(obj)
        self.assertEqual(len(points), 3)  # 3 control points
        self.assertEqual(len(segments), 2)  # 3 points -> 2 spans
        got = sorted(tuple(round(c, 3) for c in p) for _, p in points)
        self.assertEqual(got, [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0)])

    def test_non_curve_object_returns_empty(self):
        me = self.data.meshes.new("m")
        me.from_pydata([(0.0, 0.0, 0.0)], [], [])
        ob = self.data.objects.new("m", me)
        self.scene.collection.objects.link(ob)
        self.assertEqual(extract_pickable_geometry(ob), ([], []))

    def test_element_geometry_isolates_one_element_for_highlight(self):
        # element_geometry returns only the requested element's geometry, so the
        # hover highlight lights up exactly that line / arc / point.
        p0 = self.add_point((0.0, 0.0))
        p1 = self.add_point((2.0, 0.0))
        line = self.add_line(p0, p1)
        obj = self.sketch.target_object

        # a line: one segment, no owned point (its endpoints are their own elems)
        lpoints, lsegments = element_geometry(obj, line.curve_id)
        self.assertEqual(len(lsegments), 1)
        self.assertEqual(lpoints, [])

        # a point: its position, no segment
        ppoints, psegments = element_geometry(obj, p0.curve_id)
        self.assertEqual(len(ppoints), 1)
        self.assertEqual(psegments, [])

    def test_project_operator_reports_curve_pointer_for_check_props(self):
        # A picked curve element has no mesh pointer; the operator must still
        # report a truthy state pointer, or check_props() blocks main() and
        # nothing projects (the "still cannot project" bug).
        from ..operators.project_geometry import VIEW3D_OT_slvs_project_geometry

        op = VIEW3D_OT_slvs_project_geometry.__new__(VIEW3D_OT_slvs_project_geometry)
        op.state_index = 0
        op._state_data = {0: {"curve_ref": ("Src", "deadbeef")}}
        self.assertTrue(bool(op.get_state_pointer(index=0)))
        self.assertEqual(op.get_state_pointer(index=0), ("Src", "deadbeef"))

    def test_element_geometry_of_arc_is_the_tessellated_arc(self):
        ct = self.add_point((0.0, 0.0))
        start = self.add_point((1.0, 0.0))
        end = self.add_point((0.0, 1.0))
        arc = self.add_arc(ct, start, end)

        points, segments = element_geometry(self.sketch.target_object, arc.curve_id)
        self.assertGreater(len(segments), 1)  # tessellated
        self.assertEqual(points, [])
