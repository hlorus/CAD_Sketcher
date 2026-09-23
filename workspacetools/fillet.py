from bpy.types import WorkSpaceTool

from ..declarations import GizmoGroups, Operators, WorkSpaceTools
from ..keymaps import tool_node
from ..stateful_operator.tool import GenericStateTool
from ..stateful_operator.utilities.keymap import operator_access


class VIEW3D_T_slvs_fillet(GenericStateTool, WorkSpaceTool):
    """Pick the edges a Fillet modifier rounds."""

    bl_space_type = "VIEW_3D"
    bl_context_mode = "OBJECT"
    bl_idname = WorkSpaceTools.Fillet
    bl_label = "Fillet"
    bl_description = "Round picked edges of the active object"
    bl_icon = "ops.mesh.bevel"
    bl_operator = Operators.FilletSelect
    bl_widget = GizmoGroups.ObjectHover
    bl_keymap = (
        *tool_node,
        *operator_access(Operators.FilletSelect),
    )

    def draw_settings(context, layout, tool):
        props = tool.operator_properties(Operators.FilletSelect)
        layout.prop(props, "amount")
