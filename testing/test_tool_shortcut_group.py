"""What a tool key starts when several tools share one toolbar button.

A key marked as a group key (the rectangle variants, the arrays) starts whichever
member the toolbar shows, the last one used, as clicking that button would. Every
other key names one tool and starts that one, even where it shares a button: the
two arcs share a button but have a key each.
"""

from collections import namedtuple

from bl_ui.space_toolsystem_common import ToolSelectPanelHelper

from ..declarations import Operators, WorkSpaceTools
from ..stateful_operator.invoke_op import View3D_OT_invoke_tool
from .utils import BgsTestCase, make_operator_double

_Item = namedtuple("_Item", "idname operator")


class TestGroupToolShortcut(BgsTestCase):
    def _invoke_op(self, group=True):
        op = make_operator_double(View3D_OT_invoke_tool)()
        op.tool_name = WorkSpaceTools.AddArc2D.value
        op.operator = Operators.AddArc2D.value
        op.group = group
        return op

    def _with_group_active(self, item, group=None):
        """Stand in for the toolbar's group-active lookup."""
        cls = ToolSelectPanelHelper._tool_class_from_space_type("VIEW_3D")
        original = cls._tool_get_by_id_active_with_group
        cls._tool_get_by_id_active_with_group = classmethod(
            lambda _cls, _context, _idname: (item, 0, group)
        )
        self.addCleanup(setattr, cls, "_tool_get_by_id_active_with_group", original)

    def test_starts_the_groups_active_tool(self):
        self._with_group_active(
            _Item(WorkSpaceTools.AddArc3Point2D, Operators.AddArc3Point2D)
        )
        tool, operator = self._invoke_op()._group_active(self.context)

        self.assertEqual(tool, WorkSpaceTools.AddArc3Point2D.value)
        self.assertEqual(operator, Operators.AddArc3Point2D.value)

    def test_a_chain_starts_the_member_that_can_carry_it_on(self):
        # The center-based arc is what the toolbar shows, but it starts from a
        # center: it would end the chain rather than continue it.
        from ..stateful_operator.utilities import continuation

        continuation.publish(["abc"], None, "Sketch")
        self.addCleanup(continuation.clear)
        center = _Item(WorkSpaceTools.AddArc2D, Operators.AddArc2D)
        endpoint = _Item(WorkSpaceTools.AddArc3Point2D, Operators.AddArc3Point2D)
        self._with_group_active(center, group=[center, endpoint])

        tool, operator = self._invoke_op()._group_active(self.context)

        self.assertEqual(tool, WorkSpaceTools.AddArc3Point2D.value)
        self.assertEqual(operator, Operators.AddArc3Point2D.value)

    def test_a_key_that_names_one_tool_starts_that_tool(self):
        # Shift+A is the center-based arc's own key: it must not be redirected to
        # whichever arc the toolbar shows.
        endpoint = _Item(WorkSpaceTools.AddArc3Point2D, Operators.AddArc3Point2D)
        center = _Item(WorkSpaceTools.AddArc2D, Operators.AddArc2D)
        self._with_group_active(endpoint, group=[endpoint, center])

        tool, operator = self._invoke_op(group=False)._group_active(self.context)

        self.assertEqual(tool, WorkSpaceTools.AddArc2D.value)
        self.assertEqual(operator, Operators.AddArc2D.value)

    def test_the_tables_say_which_keys_are_group_keys(self):
        # The arcs have a key each; the rectangle variants and the arrays share one.
        from .. import keymaps

        def keyed(table):
            return {row[0]: keymaps.GROUP in row[3:] for row in table}

        sketch = keyed(keymaps.SKETCH_TOOL_KEYS)
        self.assertFalse(sketch[WorkSpaceTools.AddArc3Point2D])
        self.assertFalse(sketch[WorkSpaceTools.AddArc2D])
        self.assertTrue(sketch[WorkSpaceTools.AddRectangle])
        self.assertTrue(keyed(keymaps.NODE_TOOL_KEYS)[WorkSpaceTools.ArrayLinear])

    def test_without_a_chain_the_shown_member_still_wins(self):
        center = _Item(WorkSpaceTools.AddArc2D, Operators.AddArc2D)
        endpoint = _Item(WorkSpaceTools.AddArc3Point2D, Operators.AddArc3Point2D)
        self._with_group_active(center, group=[center, endpoint])

        tool, operator = self._invoke_op()._group_active(self.context)

        self.assertEqual(tool, WorkSpaceTools.AddArc2D.value)
        self.assertEqual(operator, Operators.AddArc2D.value)

    def test_falls_back_to_the_tool_the_key_names(self):
        """Not in a group, or a toolbar that can't answer: use the key's tool."""
        self._with_group_active(None)
        tool, operator = self._invoke_op()._group_active(self.context)

        self.assertEqual(tool, WorkSpaceTools.AddArc2D.value)
        self.assertEqual(operator, Operators.AddArc2D.value)

    def test_a_global_key_is_a_group_key_where_its_tool_key_is(self):
        """Ctrl+Shift+D starts the array the toolbar shows, like plain D does."""
        from .. import keymaps

        globals_by_tool = {
            tool: (key, group)
            for tool, _operator, _tool_key, key, group in keymaps.node_tool_rows()
        }

        self.assertEqual(len(globals_by_tool), len(keymaps.NODE_TOOL_KEYS))
        self.assertEqual(globals_by_tool[WorkSpaceTools.ArrayLinear], ("D", True))
        self.assertEqual(globals_by_tool[WorkSpaceTools.Extrude], ("E", False))
