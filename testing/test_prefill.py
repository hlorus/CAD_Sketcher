"""Selection prefill + end-to-end drive for stateful operators.

When the user selects an entity and invokes a tool, that entity must fill the
tool's first pointer state -- a selected point becomes the line's start / the
circle's center / the arc's center / the rectangle's first corner; a selected
segment becomes the offset/trim/bevel target. This is the exact path ``invoke``
takes for ``wait_for_input`` tools: ``prefill_state_props`` -> ``gather_selection``
-> ``parse_selection`` (-> ``_matches_types``) -> ``next_state``.

Operators are driven through ``OpHarness`` (see ``testing/utils.py``), which runs
the real operator code on a non-bpy twin so no modal region is needed.
"""

import re
from pathlib import Path
from unittest import TestCase

from .utils import Sketch2dTestCase, OpHarness
from .. import global_data


class TestSelectionPrefill(Sketch2dTestCase):
    def _harness(self, real_cls):
        return OpHarness(real_cls, self.sketch, self.context)

    def _select_only(self, ref):
        global_data.selected.clear()
        global_data.selected.append(ref.curve_id)

    def _a_point(self):
        return self.add_point((3.0, 4.0))

    def _a_line(self):
        return self.add_line(self.add_point((0.0, 0.0)), self.add_point((5.0, 0.0)))

    # -- a selected point fills the first (point) pointer state ---------------
    def test_selected_point_prefills_first_state(self):
        from ..operators.add_line_2d import View3D_OT_slvs_add_line2d
        from ..operators.add_circle import View3D_OT_slvs_add_circle2d
        from ..operators.add_arc import View3D_OT_slvs_add_arc2d
        from ..operators.add_rectangle import View3D_OT_slvs_add_rectangle

        point_ops = (
            View3D_OT_slvs_add_line2d,     # p1  (start)
            View3D_OT_slvs_add_circle2d,   # ct  (center)
            View3D_OT_slvs_add_arc2d,      # ct  (center)
            View3D_OT_slvs_add_rectangle,  # p1  (corner)
        )
        for real_cls in point_ops:
            with self.subTest(op=real_cls.__name__):
                pt = self._a_point()
                self._select_only(pt)

                h = self._harness(real_cls)
                h.prefill()

                self.assertTrue(
                    h.op.get_state_data(0).get("is_existing_entity"),
                    "selected point was not matched for prefill",
                )
                self.assertEqual(h.state_curve_id(0), pt.curve_id)
                # get_point is what main() reads for a point state.
                self.assertEqual(h.get_point(0).curve_id, pt.curve_id)

    # -- a selected segment fills the first (segment) pointer state -----------
    def test_selected_segment_prefills_first_state(self):
        from ..operators.offset import View3D_OT_slvs_add_offset
        from ..operators.trim import View3D_OT_slvs_trim
        from ..operators.bevel import View3D_OT_slvs_bevel

        segment_ops = (
            View3D_OT_slvs_add_offset,  # entity
            View3D_OT_slvs_trim,        # segment
            View3D_OT_slvs_bevel,       # p1 accepts POINT2D | SEGMENT
        )
        for real_cls in segment_ops:
            with self.subTest(op=real_cls.__name__):
                line = self._a_line()
                self._select_only(line)

                h = self._harness(real_cls)
                h.prefill()

                self.assertTrue(
                    h.op.get_state_data(0).get("is_existing_entity"),
                    "selected segment was not matched for prefill",
                )
                self.assertEqual(h.state_curve_id(0), line.curve_id)

    # -- end to end: prefilled start point is reused by the committed line ----
    def test_prefilled_point_is_reused_as_line_start(self):
        from ..operators.add_line_2d import View3D_OT_slvs_add_line2d

        pt = self._a_point()
        self._select_only(pt)

        h = self._harness(View3D_OT_slvs_add_line2d)
        h.prefill()                 # start point <- selection
        h.place_point((10.0, 4.0))  # endpoint placed by a click
        h.finish()                  # commit: main() builds the line

        line = h.op.target
        self.assertEqual(line.p1.curve_id, pt.curve_id)
        # The endpoint is a freshly created point, not the selected one.
        self.assertNotEqual(line.p2.curve_id, pt.curve_id)

    # -- immediate execution: a full selection fills every state at once ------
    def test_two_selected_points_complete_line_immediately(self):
        """Docs "Immediate Execution": select both points, invoke line -> both
        pointer states prefill and the operator can run without any click."""
        from ..operators.add_line_2d import View3D_OT_slvs_add_line2d

        p_start = self.add_point((0.0, 0.0))
        p_end = self.add_point((4.0, 0.0))
        global_data.selected.clear()
        global_data.selected.append(p_start.curve_id)
        global_data.selected.append(p_end.curve_id)

        h = self._harness(View3D_OT_slvs_add_line2d)
        h.prefill()

        # Both states filled -> the operator is ready to commit with no click.
        self.assertTrue(h.op.check_props(), "full selection did not satisfy all states")
        h.finish()
        line = h.op.target
        self.assertEqual(
            {line.p1.curve_id, line.p2.curve_id},
            {p_start.curve_id, p_end.curve_id},
        )

    # -- type rejection: a wrong-typed selection must not prefill -------------
    def test_selected_line_does_not_prefill_point_state(self):
        from ..operators.add_circle import View3D_OT_slvs_add_circle2d

        line = self._a_line()          # a segment, not a point
        self._select_only(line)

        h = self._harness(View3D_OT_slvs_add_circle2d)  # center wants a point
        h.prefill()

        self.assertFalse(
            h.op.get_state_data(0).get("is_existing_entity", False),
            "a line must not be accepted as a circle center",
        )
        self.assertFalse(h.state_curve_id(0), "no curve should be bound to the center")

    def tearDown(self):
        global_data.selected.clear()
        return super().tearDown()


class TestNoHardcodedExtensionNamespace(TestCase):
    """Imports must be relative; a hardcoded ``bl_ext.<repo>.CAD_Sketcher`` path
    resolves only in the dev install and raises ModuleNotFoundError in every other
    namespace (user_default, the published extension id, ...). Selection prefill
    crashed exactly this way from ``_matches_types`` when a selected entity was
    used to invoke a tool.
    """

    def test_no_absolute_bl_ext_imports(self):
        root = Path(__file__).resolve().parent.parent
        pattern = re.compile(r"\bbl_ext\.\w+\.CAD_Sketcher\b")
        offenders = []
        for path in root.rglob("*.py"):
            if path.parent.name == "testing":
                continue
            for lineno, line in enumerate(path.read_text().splitlines(), 1):
                code = line.split("#", 1)[0]
                if pattern.search(code):
                    offenders.append(f"{path.relative_to(root)}:{lineno}: {line.strip()}")
        self.assertFalse(
            offenders,
            "Hardcoded extension namespace in import(s) — use relative imports:\n"
            + "\n".join(offenders),
        )
