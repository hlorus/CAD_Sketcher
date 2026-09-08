"""Issue #674: reference ("measure only") dimensions must not reach the solver.

A reference dimension only reports a measurement; it must not act as a driving
constraint. If it does, it consumes a degree of freedom and, when the measured
quantity is already implied by other constraints, pushes the system into
REDUNDANT_OK -- flagging the redundant group (and unrelated constraints) failed.
"""

from .utils import Sketch2dTestCase


class TestReferenceDimension(Sketch2dTestCase):
    def test_reference_distance_does_not_consume_dof(self):
        # A free segment; a driving distance would remove one DOF, a reference one
        # must not.
        self.add_point((0, 0), fixed=True)
        p1 = self.add_point((1, 0))
        p2 = self.add_point((1, 1))
        self.add_line(p1, p2)
        self.solve()
        dof_free = self.sketch.dof

        c = self.sketch.constraints.add_distance(
            init=True, curve_id_1=p1.curve_id, curve_id_2=p2.curve_id
        )
        c.is_reference = True
        self.solve()
        self.assertEqual(self.sketch.dof, dof_free, "reference distance consumed a DOF")

    def test_reference_distance_does_not_overconstrain(self):
        # Fully constrain a segment's length with a driving distance, then add a
        # second, reference, distance on the same pair. The reference one is a
        # pure measurement, so the sketch must stay OKAY with nothing failed.
        origin = self.add_point((0, 0), fixed=True)
        p1 = self.add_point((3, 0))
        self.add_line(origin, p1)
        sc = self.sketch.constraints
        driving = sc.add_distance(
            init=True, curve_id_1=origin.curve_id, curve_id_2=p1.curve_id
        )
        driving.value = 3.0
        self.solve()

        ref = sc.add_distance(
            init=True, curve_id_1=origin.curve_id, curve_id_2=p1.curve_id
        )
        ref.is_reference = True
        self.solve()

        self.assertEqual(self.sketch.get_solver_state().identifier, "OKAY")
        failed = [c.type for c in sc.all if getattr(c, "failed", False)]
        self.assertEqual(failed, [], f"reference dim over-constrained: {failed} failed")
