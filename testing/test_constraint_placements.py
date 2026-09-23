"""Where a constraint's icons go.

A constraint is marked on each entity it references, which shows what it ties
together. Constraints whose entities sit in the same spot by definition mark
only one of them: a second icon there would just cover the first.
"""

from .utils import Sketch2dTestCase


class TestConstraintPlacements(Sketch2dTestCase):
    def test_a_coincidence_is_marked_once(self):
        a = self.add_point((0.0, 0.0))
        b = self.add_point((0.0, 0.0))
        constraint = self.sketch.constraints.add_coincident(a.curve_id, b.curve_id)

        self.assertEqual(constraint.curve_id_placements(), [a.curve_id])

    def test_a_midpoint_is_marked_once(self):
        p0 = self.add_point((0.0, 0.0))
        p1 = self.add_point((2.0, 0.0))
        line = self.add_line(p0, p1)
        middle = self.add_point((1.0, 0.0))
        constraint = self.sketch.constraints.add_midpoint(
            middle.curve_id, line.curve_id
        )

        # The point is the line's midpoint, which is where the line's own marker
        # sits, so the line is not marked again.
        self.assertEqual(constraint.curve_id_placements(), [middle.curve_id])

    def test_constraints_between_separate_entities_are_marked_on_both(self):
        p0 = self.add_point((0.0, 0.0))
        p1 = self.add_point((2.0, 0.0))
        p2 = self.add_point((0.0, 1.0))
        p3 = self.add_point((2.0, 2.0))
        first = self.add_line(p0, p1)
        second = self.add_line(p2, p3)
        constraint = self.sketch.constraints.add_parallel(
            first.curve_id, second.curve_id
        )

        self.assertEqual(
            constraint.curve_id_placements(), [first.curve_id, second.curve_id]
        )
