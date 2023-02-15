from bpy.types import WorkSpaceTool

from ..declarations import GizmoGroups, Operators, WorkSpaceTools
from ..keymaps import disable_gizmos, tool_access, tool_select
from ..stateful_operator.tool import GenericStateTool
from ..stateful_operator.utilities.keymap import operator_access


class VIEW3D_T_slvs_trim(GenericStateTool, WorkSpaceTool):
    bl_space_type = "VIEW_3D"
    bl_context_mode = "OBJECT"
    bl_idname = WorkSpaceTools.Trim
    bl_label = "Trim"
    bl_operator = Operators.Trim
    bl_icon = "ops.gpencil.stroke_cutter"
    bl_widget = GizmoGroups.Preselection
    bl_keymap = (
        *disable_gizmos,
        *tool_select,
        *tool_access,
        *operator_access(Operators.Trim),
    )
