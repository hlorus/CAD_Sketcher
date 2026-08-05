"""Dimension-constraint behaviour fixes (#450, #416)."""

import bpy

from .utils import Sketch2dTestCase


class TestDimension(Sketch2dTestCase):
    def test_450_bevel_offset_use_length_units(self):
        """Bevel radius / offset distance must respect the scene unit system."""
        for op, prop in (
            (bpy.ops.view3d.slvs_bevel, "radius"),
            (bpy.ops.view3d.slvs_offset, "distance"),
        ):
            p = op.get_rna_type().properties[prop]
            self.assertEqual(p.subtype, "DISTANCE", f"{prop} subtype")
            self.assertEqual(p.unit, "LENGTH", f"{prop} unit")

    def test_416_angle_keeps_placement_on_reference_toggle(self):
        """Toggling 'Only measure' must not move the angle's label."""
        sc = self.sketch.constraints
        p0 = self.add_point((0, 0), fixed=True)
        p1 = self.add_point((2, 0), fixed=True)
        p2 = self.add_point((0, 2), fixed=True)
        l1 = self.add_line(p0, p1)
        l2 = self.add_line(p0, p2)

        c = sc.add_angle(init=True, curve_id_1=l1.curve_id, curve_id_2=l2.curve_id)

        # User-placed label position.
        c.draw_offset = 3.7
        c.draw_outset = 0.25

        c.is_reference = True
        self.assertAlmostEqual(c.draw_offset, 3.7, places=4)
        self.assertAlmostEqual(c.draw_outset, 0.25, places=4)

        c.is_reference = False
        self.assertAlmostEqual(c.draw_offset, 3.7, places=4)
        self.assertAlmostEqual(c.draw_outset, 0.25, places=4)

    def test_479_angle_supplementary_remeasures_without_deform(self):
        """Supplementary toggle flips the shown value, never moves geometry."""
        import math

        sc = self.sketch.constraints
        p0 = self.add_point((0, 0), fixed=True)
        pa = self.add_point((2, 0), fixed=True)
        pb = self.add_point((2, 2))
        l1 = self.add_line(p0, pa)
        l2 = self.add_line(p0, pb)

        c = sc.add_angle(init=True, curve_id_1=l1.curve_id, curve_id_2=l2.curve_id)
        self.solve()
        self.assertAlmostEqual(math.degrees(c.value), 45.0, places=2)

        c.setting = True          # supplementary
        self.solve()
        self.assertAlmostEqual(math.degrees(c.value), 135.0, places=2)
        self.assertAlmostEqual(pb.co.x, 2.0, places=3)   # geometry unchanged
        self.assertAlmostEqual(pb.co.y, 2.0, places=3)

    def test_479_distance_align_remeasures_without_deform(self):
        """Switching alignment re-measures the current geometry, no deform."""
        sc = self.sketch.constraints
        p0 = self.add_point((0, 0), fixed=True)
        p1 = self.add_point((3, 3))

        c = sc.add_distance(init=True, curve_id_1=p0.curve_id, curve_id_2=p1.curve_id)
        self.solve()

        c.align = "VERTICAL"
        self.solve()
        self.assertAlmostEqual(c.value, 3.0, places=3)   # vertical component
        self.assertAlmostEqual(p1.co.x, 3.0, places=3)   # geometry unchanged
        self.assertAlmostEqual(p1.co.y, 3.0, places=3)
