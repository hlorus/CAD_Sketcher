"""A stateful operator's status line names the tool before its prompt."""

from types import SimpleNamespace

from ..stateful_operator.logic import StatefulOperatorLogic
from .utils import OpHarness, Sketch2dTestCase


class StatusRecorder:
    """A stand-in context that keeps whatever is written to the status bar."""

    def __init__(self):
        self.lines = []
        self.workspace = SimpleNamespace(status_text_set=self.lines.append)
        self.area = None


class TestStatusLine(Sketch2dTestCase):
    def _op(self, cls):
        op = OpHarness(cls, self.sketch, self.context).op
        # The twin stubs the numeric input out; the status line reads it.
        op._numeric = SimpleNamespace(is_active=False)
        return op

    def _status(self, cls, method=StatefulOperatorLogic.set_status_text):
        # The twin shadows set_status_text with a no-op sink, so call the real
        # one against it.
        recorder = StatusRecorder()
        method(self._op(cls), recorder)
        return recorder.lines[-1]

    def test_prompt_starts_with_the_operator_name(self):
        from ..operators.add_geometric_constraints import (
            VIEW3D_OT_slvs_add_tangent,
        )

        line = self._status(VIEW3D_OT_slvs_add_tangent)
        self.assertTrue(line.startswith("Tangent    "), line)
        # The state's own prompt is still there, after the name.
        self.assertIn("Entity 1:", line)

    def test_each_tool_names_itself(self):
        from ..operators.add_circle import View3D_OT_slvs_add_circle2d
        from ..operators.trim import View3D_OT_slvs_trim

        for cls, label in (
            (View3D_OT_slvs_add_circle2d, "Add Circle"),
            (View3D_OT_slvs_trim, "Trim"),
        ):
            self.assertTrue(self._status(cls).startswith(label + "    "), label)

    def test_re_pick_line_is_named_too(self):
        from ..operators.add_geometric_constraints import (
            VIEW3D_OT_slvs_add_tangent,
        )

        line = self._status(
            VIEW3D_OT_slvs_add_tangent, StatefulOperatorLogic._set_edit_status
        )
        self.assertTrue(line.startswith("Tangent    Re-pick "), line)

    def test_an_unnamed_operator_keeps_its_bare_prompt(self):
        op = SimpleNamespace(bl_label="")
        self.assertEqual(
            StatefulOperatorLogic._status_line(op, "Entity 1: pick"),
            "Entity 1: pick",
        )
