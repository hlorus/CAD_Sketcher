from bpy.types import WorkSpaceTool

from ..declarations import GizmoGroups, Operators, WorkSpaceTools
from ..stateful_operator.tool import GenericStateTool
from ..stateful_operator.utilities.keymap import operator_access
from .keymaps_3d import tool_generic_3d


class VIEW3D_T_slvs_add_line3d(GenericStateTool, WorkSpaceTool):
    bl_space_type = "VIEW_3D"
    bl_context_mode = "OBJECT"
    bl_idname = WorkSpaceTools.AddLine3D
    bl_label = "Add 3D Line"
    bl_operator = Operators.AddLine3D
    bl_icon = "ops.gpencil.primitive_line"
    bl_widget = GizmoGroups.Preselection
    bl_keymap = (
        *tool_generic_3d,
        *operator_access(Operators.AddLine3D),
    )
