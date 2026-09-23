"""A tool key starts whichever member of its toolbar group is active.

The two arc tools share one toolbar button, so "A" has to start the one the
toolbar shows (the last one used), not always the group's first tool.
"""

from collections import namedtuple

from bl_ui.space_toolsystem_common import ToolSelectPanelHelper

from ..declarations import Operators, WorkSpaceTools
from ..stateful_operator.invoke_op import View3D_OT_invoke_tool
from .utils import BgsTestCase, make_operator_double

_Item = namedtuple("_Item", "idname operator")


class TestGroupToolShortcut(BgsTestCase):
    def _invoke_op(self):
        op = make_operator_double(View3D_OT_invoke_tool)()
        op.tool_name = WorkSpaceTools.AddArc2D.value
        op.operator = Operators.AddArc2D.value
        return op

    def _with_group_active(self, item):
        """Stand in for the toolbar's group-active lookup."""
        cls = ToolSelectPanelHelper._tool_class_from_space_type("VIEW_3D")
        original = cls._tool_get_by_id_active_with_group
        cls._tool_get_by_id_active_with_group = classmethod(
            lambda _cls, _context, _idname: (item, 0, None)
        )
        self.addCleanup(setattr, cls, "_tool_get_by_id_active_with_group", original)

    def test_starts_the_groups_active_tool(self):
        self._with_group_active(
            _Item(WorkSpaceTools.AddArc3Point2D, Operators.AddArc3Point2D)
        )
        tool, operator = self._invoke_op()._group_active(self.context)

        self.assertEqual(tool, WorkSpaceTools.AddArc3Point2D.value)
        self.assertEqual(operator, Operators.AddArc3Point2D.value)

    def test_falls_back_to_the_tool_the_key_names(self):
        """Not in a group, or a toolbar that can't answer: use the key's tool."""
        self._with_group_active(None)
        tool, operator = self._invoke_op()._group_active(self.context)

        self.assertEqual(tool, WorkSpaceTools.AddArc2D.value)
        self.assertEqual(operator, Operators.AddArc2D.value)
