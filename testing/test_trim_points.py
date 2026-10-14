"""Trimming at points, and trimming points away.

A point sitting on a line is a cut mark to the user, whether or not a
constraint ties it there, and a point left over from an earlier trim should be
clickable away with the same tool.
"""

from mathutils import Vector

from ..model.constants import SketchCurveType
from ..model.curve_ref import ArcRef, CircleRef, LineRef, PointRef, curve_ref
from ..operators.trim import View3D_OT_slvs_trim
from ..utilities.curve_data import read_curve_id_list
from .utils import OpHarness, Sketch2dTestCase


def _geometry(sketch):
    """Lines as sorted endpoint pairs and points as coordinates, both rounded."""
    curve_data = sketch.data
    type_attr = curve_data.attributes.get("sketch_type")
    lines, points = [], []
    for index, cid in enumerate(read_curve_id_list(curve_data)):
        ref = curve_ref(sketch, cid)
        if not ref.valid:
            continue
        kind = type_attr.data[index].value
        if kind == SketchCurveType.LINE:
            ends = tuple(
                tuple(round(v, 3) for v in point.co[:2]) for point in (ref.p1, ref.p2)
            )
            lines.append(tuple(sorted(ends)))
        elif kind == SketchCurveType.POINT:
            points.append(tuple(round(v, 3) for v in ref.co[:2]))
    return sorted(lines), sorted(points)


class TestTrimAtPoints(Sketch2dTestCase):
    def _trim(self, target, mouse=None):
        harness = OpHarness(View3D_OT_slvs_trim, self.sketch, self.context)
        harness.op._state_data = {}
        harness.op.state_index = 0
        harness.pick(target)
        if mouse is not None:
            harness.op.get_state_data(0)["mouse_pos"] = mouse
        harness.finish()

    def _wall(self, a=(0.0, 0.0), b=(10.0, 0.0)):
        return LineRef.create(
            self.sketch,
            PointRef.create(self.sketch, a),
            PointRef.create(self.sketch, b),
        )

    def test_a_doorway_between_two_points_on_the_line(self):
        # Reported: points dropped on a wall did not cut it, and trimming
        # between them took the whole wall instead.
        wall = self._wall()
        PointRef.create(self.sketch, (4.0, 0.0))
        PointRef.create(self.sketch, (6.0, 0.0))

        self._trim(wall, (5.0, 0.0))

        lines, _points = _geometry(self.sketch)
        self.assertEqual(
            lines,
            [((0.0, 0.0), (4.0, 0.0)), ((6.0, 0.0), (10.0, 0.0))],
            "the span between the two points is what goes",
        )

    def test_the_points_on_the_line_are_reused_not_duplicated(self):
        # The marks become the new ends, rather than a second point being
        # stacked on each of them. The wall's own ends stay, holding the two
        # pieces that survive.
        wall = self._wall()
        PointRef.create(self.sketch, (4.0, 0.0))
        PointRef.create(self.sketch, (6.0, 0.0))

        self._trim(wall, (5.0, 0.0))

        _lines, points = _geometry(self.sketch)
        self.assertEqual(points, [(0.0, 0.0), (4.0, 0.0), (6.0, 0.0), (10.0, 0.0)])

    def test_a_point_past_the_end_is_not_a_cut(self):
        # On the infinite line, but not on this segment.
        wall = self._wall()
        PointRef.create(self.sketch, (14.0, 0.0))

        self._trim(wall, (5.0, 0.0))

        lines, _points = _geometry(self.sketch)
        self.assertEqual(lines, [], "nothing bounds the click, so the wall goes")

    def test_a_point_off_the_line_is_not_a_cut(self):
        wall = self._wall()
        PointRef.create(self.sketch, (5.0, 1.0))

        self._trim(wall, (5.0, 0.0))

        lines, _points = _geometry(self.sketch)
        self.assertEqual(lines, [])

    def test_trimming_a_corner_span_leaves_no_stray_point(self):
        # A corner reaches the trim twice, as this line's own end and as the
        # crossing with the neighbour sharing it. Counted twice it bounds a
        # zero-length piece, whose points used to be left on the corner.
        corners = [
            PointRef.create(self.sketch, co)
            for co in ((0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0))
        ]
        edges = [
            LineRef.create(self.sketch, corners[i], corners[(i + 1) % 4])
            for i in range(4)
        ]

        self._trim(edges[0], (5.0, 0.0))

        lines, points = _geometry(self.sketch)
        self.assertEqual(len(lines), 3, "the clicked edge goes")
        self.assertEqual(
            points,
            [(0.0, 0.0), (0.0, 10.0), (10.0, 0.0), (10.0, 10.0)],
            "the three remaining corners, and nothing stacked on them",
        )

    def test_trimming_a_crossed_edge_leaves_no_stray_point(self):
        corners = [
            PointRef.create(self.sketch, co)
            for co in ((0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0))
        ]
        edges = [
            LineRef.create(self.sketch, corners[i], corners[(i + 1) % 4])
            for i in range(4)
        ]
        LineRef.create(
            self.sketch,
            PointRef.create(self.sketch, (5.0, -5.0)),
            PointRef.create(self.sketch, (5.0, 5.0)),
        )

        self._trim(edges[0], (2.0, 0.0))

        lines, points = _geometry(self.sketch)
        self.assertIn(((5.0, 0.0), (10.0, 0.0)), lines, "the far half survives")
        self.assertEqual(
            points.count((0.0, 0.0)), 1, "no second point stacked on the corner"
        )


class TestTrimRemovesPoints(Sketch2dTestCase):
    def _trim(self, target):
        harness = OpHarness(View3D_OT_slvs_trim, self.sketch, self.context)
        harness.op._state_data = {}
        harness.op.state_index = 0
        harness.pick(target)
        harness.finish()

    def test_a_clicked_point_is_removed(self):
        stray = PointRef.create(self.sketch, (3.0, 3.0))

        self._trim(stray)

        _lines, points = _geometry(self.sketch)
        self.assertEqual(points, [])

    def test_a_point_a_line_is_built_from_is_kept(self):
        # Removing it would take the line too, which a click on the point did
        # not ask for.
        p1 = PointRef.create(self.sketch, (0.0, 0.0))
        p2 = PointRef.create(self.sketch, (10.0, 0.0))
        LineRef.create(self.sketch, p1, p2)

        self._trim(p1)

        lines, points = _geometry(self.sketch)
        self.assertEqual(lines, [((0.0, 0.0), (10.0, 0.0))])
        self.assertEqual(points, [(0.0, 0.0), (10.0, 0.0)])

    def test_an_arc_centre_is_kept(self):
        ct = PointRef.create(self.sketch, (0.0, 0.0))
        start = PointRef.create(self.sketch, (1.0, 0.0))
        end = PointRef.create(self.sketch, (0.0, 1.0))
        ArcRef.create(self.sketch, ct, start, end)

        self._trim(ct)

        _lines, points = _geometry(self.sketch)
        self.assertIn((0.0, 0.0), points, "the arc still needs its centre")

    def test_a_circle_centre_is_kept(self):
        ct = PointRef.create(self.sketch, (0.0, 0.0))
        CircleRef.create(self.sketch, ct, radius=2.0)

        self._trim(ct)

        _lines, points = _geometry(self.sketch)
        self.assertIn((0.0, 0.0), points)

    def test_a_point_freed_by_a_trim_can_then_be_clicked_away(self):
        # The pair a user actually performs: cut a doorway, then clear the
        # marks that bounded it.
        wall = LineRef.create(
            self.sketch,
            PointRef.create(self.sketch, (0.0, 0.0)),
            PointRef.create(self.sketch, (10.0, 0.0)),
        )
        mark = PointRef.create(self.sketch, (4.0, 0.0))
        PointRef.create(self.sketch, (6.0, 0.0))

        harness = OpHarness(View3D_OT_slvs_trim, self.sketch, self.context)
        harness.op._state_data = {}
        harness.op.state_index = 0
        harness.pick(wall)
        harness.op.get_state_data(0)["mouse_pos"] = (5.0, 0.0)
        harness.finish()

        # The mark now ends a wall piece, so it is not leftover and stays.
        self._trim(mark)
        _lines, points = _geometry(self.sketch)
        self.assertIn((4.0, 0.0), points)

    def test_a_point_pickable_by_the_tool(self):
        from ..model.categories import POINT

        types = View3D_OT_slvs_trim.states[0].types
        for point_type in POINT:
            self.assertIn(point_type, types)


class TestTrimStillCuts(Sketch2dTestCase):
    """The crossing cases keep working, now that points also bound a cut."""

    def _trim(self, target, mouse):
        harness = OpHarness(View3D_OT_slvs_trim, self.sketch, self.context)
        harness.op._state_data = {}
        harness.op.state_index = 0
        harness.pick(target)
        harness.op.get_state_data(0)["mouse_pos"] = mouse
        harness.finish()

    def test_a_crossed_line_keeps_the_far_side(self):
        line = LineRef.create(
            self.sketch,
            PointRef.create(self.sketch, (0.0, 0.0)),
            PointRef.create(self.sketch, (10.0, 0.0)),
        )
        LineRef.create(
            self.sketch,
            PointRef.create(self.sketch, (5.0, -5.0)),
            PointRef.create(self.sketch, (5.0, 5.0)),
        )

        self._trim(line, (2.0, 0.0))

        lines, _points = _geometry(self.sketch)
        self.assertIn(((5.0, 0.0), (10.0, 0.0)), lines)

    def test_a_lone_line_is_still_removed_whole(self):
        line = LineRef.create(
            self.sketch,
            PointRef.create(self.sketch, (0.0, 0.0)),
            PointRef.create(self.sketch, (10.0, 0.0)),
        )

        self._trim(line, (5.0, 0.0))

        lines, points = _geometry(self.sketch)
        self.assertEqual(lines, [])
        self.assertEqual(points, [], "its endpoints go with it")

    def test_a_circle_crossed_twice_becomes_an_arc(self):
        circle = CircleRef.create(
            self.sketch, PointRef.create(self.sketch, (0.0, 0.0)), radius=5.0
        )
        LineRef.create(
            self.sketch,
            PointRef.create(self.sketch, (-10.0, 3.0)),
            PointRef.create(self.sketch, (10.0, 3.0)),
        )

        self._trim(circle, (0.0, 5.0))

        curve_data = self.sketch.data
        type_attr = curve_data.attributes.get("sketch_type")
        kinds = [
            type_attr.data[i].value for i in range(len(read_curve_id_list(curve_data)))
        ]
        self.assertIn(SketchCurveType.ARC, kinds, "the cut circle becomes an arc")
        self.assertNotIn(SketchCurveType.CIRCLE, kinds)


class TestTrimPointGeometry(Sketch2dTestCase):
    def test_a_point_on_an_arc_cuts_it(self):
        ct = PointRef.create(self.sketch, (0.0, 0.0))
        start = PointRef.create(self.sketch, (5.0, 0.0))
        end = PointRef.create(self.sketch, (-5.0, 0.0))
        arc = ArcRef.create(self.sketch, ct, start, end)
        # Two marks on the arc, at 45 and 135 degrees.
        import math

        for angle in (math.pi / 4, 3 * math.pi / 4):
            PointRef.create(self.sketch, (5.0 * math.cos(angle), 5.0 * math.sin(angle)))

        harness = OpHarness(View3D_OT_slvs_trim, self.sketch, self.context)
        harness.op._state_data = {}
        harness.op.state_index = 0
        harness.pick(arc)
        harness.op.get_state_data(0)["mouse_pos"] = (0.0, 5.0)
        harness.finish()

        curve_data = self.sketch.data
        type_attr = curve_data.attributes.get("sketch_type")
        arcs = [
            i
            for i in range(len(read_curve_id_list(curve_data)))
            if type_attr.data[i].value == SketchCurveType.ARC
        ]
        self.assertEqual(len(arcs), 2, "the top of the arc is cut out")

    def test_the_cut_point_is_where_the_mark_was(self):
        wall = LineRef.create(
            self.sketch,
            PointRef.create(self.sketch, (0.0, 0.0)),
            PointRef.create(self.sketch, (10.0, 0.0)),
        )
        PointRef.create(self.sketch, (4.0, 0.0))
        PointRef.create(self.sketch, (6.0, 0.0))

        harness = OpHarness(View3D_OT_slvs_trim, self.sketch, self.context)
        harness.op._state_data = {}
        harness.op.state_index = 0
        harness.pick(wall)
        harness.op.get_state_data(0)["mouse_pos"] = (5.0, 0.0)
        harness.finish()

        lines, _points = _geometry(self.sketch)
        for line in lines:
            for end in line:
                self.assertLess(
                    min(
                        (Vector(end) - Vector(c)).length
                        for c in ((0.0, 0.0), (4.0, 0.0), (6.0, 0.0), (10.0, 0.0))
                    ),
                    1e-4,
                )
