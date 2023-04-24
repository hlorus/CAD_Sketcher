from bpy.types import WorkSpaceTool

from ..declarations import GizmoGroups, Operators, WorkSpaceTools
from ..keymaps import tool_generic
from ..stateful_operator.tool import GenericStateTool
from ..stateful_operator.utilities.keymap import operator_access


class VIEW3D_T_slvs_add_line2d(GenericStateTool, WorkSpaceTool):
    bl_space_type = "VIEW_3D"
    bl_context_mode = "OBJECT"
    bl_idname = WorkSpaceTools.AddLine2D
    bl_label = "Add 2D Line"
    bl_operator = Operators.AddLine2D
    bl_icon = "ops.gpencil.primitive_line"
    bl_widget = GizmoGroups.Preselection
    bl_keymap = (
        *tool_generic,
        *operator_access(Operators.AddLine2D),
    )

    def draw_settings(context, layout, tool):
        props = tool.operator_properties(Operators.AddLine2D)
        layout.prop(props, "continuous_draw")
