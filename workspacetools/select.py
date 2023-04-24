from bpy.types import WorkSpaceTool

from ..declarations import GizmoGroups, Operators, WorkSpaceTools
from ..keymaps import tool_select


class VIEW3D_T_slvs_select(WorkSpaceTool):
    bl_space_type = "VIEW_3D"
    bl_context_mode = "OBJECT"
    bl_idname = WorkSpaceTools.Select
    bl_label = "Solvespace Select"
    bl_description = "Select Solvespace Entities"
    bl_icon = "ops.generic.select"
    bl_widget = GizmoGroups.Preselection
    bl_keymap = tool_select

    def draw_settings(context, layout, tool):
        props = tool.operator_properties(Operators.Select)
        layout.prop(props, "mode", text="", expand=True, icon_only=True)
