"""Trimming at points, and trimming points away.

A point cuts the segment it is constrained onto. A point that merely lies on it
does not: overlapping is not the same as being attached, and the constraint is
what says the user meant it. A point left over from an earlier trim is
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


def _kinds(sketch):
    curve_data = sketch.data
    type_attr = curve_data.attributes.get("sketch_type")
    return [
        type_attr.data[index].value
        for index, cid in enumerate(read_curve_id_list(curve_data))
        if curve_ref(sketch, cid).valid
    ]


class TrimCase(Sketch2dTestCase):
    def trim(self, target, mouse=None):
        harness = OpHarness(View3D_OT_slvs_trim, self.sketch, self.context)
        harness.op._state_data = {}
        harness.op.state_index = 0
        harness.pick(target)
        if mouse is not None:
            harness.op.get_state_data(0)["mouse_pos"] = mouse
        harness.finish()

    def wall(self, a=(0.0, 0.0), b=(10.0, 0.0)):
        return LineRef.create(
            self.sketch,
            PointRef.create(self.sketch, a),
            PointRef.create(self.sketch, b),
        )

    def mark_on(self, segment, co):
        """A point constrained onto ``segment``, the way a cut edge is set."""
        point = PointRef.create(self.sketch, co)
        self.sketch.constraints.add_coincident(
            curve_id_1=point.curve_id, curve_id_2=segment.curve_id
        )
        return point


class TestTrimAtPoints(TrimCase):
    def test_a_doorway_between_two_constrained_points(self):
        wall = self.wall()
        self.mark_on(wall, (4.0, 0.0))
        self.mark_on(wall, (6.0, 0.0))

        self.trim(wall, (5.0, 0.0))

        lines, _points = _geometry(self.sketch)
        self.assertEqual(
            lines,
            [((0.0, 0.0), (4.0, 0.0)), ((6.0, 0.0), (10.0, 0.0))],
            "the span between the two marks is what goes",
        )

    def test_a_loose_point_lying_on_the_line_is_not_a_cut(self):
        # Overlapping is not being attached: with no constraint the point is
        # just sitting there, so it does not divide the line.
        wall = self.wall()
        PointRef.create(self.sketch, (4.0, 0.0))
        PointRef.create(self.sketch, (6.0, 0.0))

        self.trim(wall, (5.0, 0.0))

        lines, _points = _geometry(self.sketch)
        self.assertEqual(lines, [], "nothing bounds the click, so the wall goes")

    def test_points_constrained_onto_an_arc_cut_it(self):
        import math

        ct = PointRef.create(self.sketch, (0.0, 0.0))
        arc = ArcRef.create(
            self.sketch,
            ct,
            PointRef.create(self.sketch, (5.0, 0.0)),
            PointRef.create(self.sketch, (-5.0, 0.0)),
        )
        for angle in (math.pi / 4, 3 * math.pi / 4):
            self.mark_on(arc, (5.0 * math.cos(angle), 5.0 * math.sin(angle)))

        self.trim(arc, (0.0, 5.0))

        self.assertEqual(
            _kinds(self.sketch).count(SketchCurveType.ARC),
            2,
            "the top of the arc is cut out",
        )

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

        self.trim(edges[0], (5.0, 0.0))

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

        self.trim(edges[0], (2.0, 0.0))

        lines, points = _geometry(self.sketch)
        self.assertIn(((5.0, 0.0), (10.0, 0.0)), lines, "the far half survives")
        self.assertEqual(
            points.count((0.0, 0.0)), 1, "no second point stacked on the corner"
        )


class TestTrimRemovesPoints(TrimCase):
    def test_a_clicked_point_is_removed(self):
        PointRef.create(self.sketch, (3.0, 3.0))

        self.trim(PointRef.create(self.sketch, (6.0, 6.0)))

        _lines, points = _geometry(self.sketch)
        self.assertEqual(points, [(3.0, 3.0)], "only the clicked one goes")

    def test_a_point_a_line_is_built_from_is_kept(self):
        # Removing it would take the line too, which a click on the point did
        # not ask for.
        wall = self.wall()

        self.trim(wall.p1)

        lines, points = _geometry(self.sketch)
        self.assertEqual(lines, [((0.0, 0.0), (10.0, 0.0))])
        self.assertEqual(points, [(0.0, 0.0), (10.0, 0.0)])

    def test_refusing_says_why(self):
        # Doing nothing without a word reads as the tool being broken.
        wall = self.wall()
        reports = []

        harness = OpHarness(View3D_OT_slvs_trim, self.sketch, self.context)
        harness.op._state_data = {}
        harness.op.state_index = 0
        harness.op.report = lambda kind, message: reports.append(message)
        harness.pick(wall.p1)
        harness.finish()

        self.assertEqual(reports, ["This point is part of a curve"])

    def test_an_arc_centre_is_kept(self):
        ct = PointRef.create(self.sketch, (0.0, 0.0))
        ArcRef.create(
            self.sketch,
            ct,
            PointRef.create(self.sketch, (1.0, 0.0)),
            PointRef.create(self.sketch, (0.0, 1.0)),
        )

        self.trim(ct)

        _lines, points = _geometry(self.sketch)
        self.assertIn((0.0, 0.0), points, "the arc still needs its centre")

    def test_a_circle_centre_is_kept(self):
        ct = PointRef.create(self.sketch, (0.0, 0.0))
        CircleRef.create(self.sketch, ct, radius=2.0)

        self.trim(ct)

        _lines, points = _geometry(self.sketch)
        self.assertIn((0.0, 0.0), points)

    def test_a_centre_left_by_a_trimmed_circle_can_be_clicked_away(self):
        # Trimming a lone circle leaves its centre behind; this is how it goes.
        ct = PointRef.create(self.sketch, (0.0, 0.0))
        circle = CircleRef.create(self.sketch, ct, radius=5.0)

        self.trim(circle, (0.0, 5.0))
        _lines, points = _geometry(self.sketch)
        self.assertEqual(points, [(0.0, 0.0)], "the centre is left over")

        self.trim(ct)
        _lines, points = _geometry(self.sketch)
        self.assertEqual(points, [])

    def test_points_are_pickable_by_the_tool(self):
        from ..model.categories import POINT

        types = View3D_OT_slvs_trim.states[0].types
        for point_type in POINT:
            self.assertIn(point_type, types)


class TestTrimStillCuts(TrimCase):
    """The crossing cases keep working alongside the point handling."""

    def test_a_crossed_line_keeps_the_far_side(self):
        line = self.wall()
        LineRef.create(
            self.sketch,
            PointRef.create(self.sketch, (5.0, -5.0)),
            PointRef.create(self.sketch, (5.0, 5.0)),
        )

        self.trim(line, (2.0, 0.0))

        lines, _points = _geometry(self.sketch)
        self.assertIn(((5.0, 0.0), (10.0, 0.0)), lines)

    def test_a_lone_line_is_still_removed_whole(self):
        self.trim(self.wall(), (5.0, 0.0))

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

        self.trim(circle, (0.0, 5.0))

        kinds = _kinds(self.sketch)
        self.assertIn(SketchCurveType.ARC, kinds, "the cut circle becomes an arc")
        self.assertNotIn(SketchCurveType.CIRCLE, kinds)

    def test_the_cut_lands_on_the_marks(self):
        wall = self.wall()
        self.mark_on(wall, (4.0, 0.0))
        self.mark_on(wall, (6.0, 0.0))

        self.trim(wall, (5.0, 0.0))

        expected = ((0.0, 0.0), (4.0, 0.0), (6.0, 0.0), (10.0, 0.0))
        lines, _points = _geometry(self.sketch)
        for line in lines:
            for end in line:
                self.assertLess(
                    min((Vector(end) - Vector(co)).length for co in expected), 1e-4
                )
