from bpy.types import WorkSpaceTool

from ..declarations import GizmoGroups, Operators, WorkSpaceTools
from ..keymaps import disable_gizmos, tool_access, tool_select
from ..stateful_operator.tool import GenericStateTool
from ..stateful_operator.utilities.keymap import operator_access
from .icon import get_addon_icon_path


class VIEW3D_T_slvs_add_point3d(GenericStateTool, WorkSpaceTool):
    bl_space_type = "VIEW_3D"
    bl_context_mode = "OBJECT"
    bl_idname = WorkSpaceTools.AddPoint3D
    bl_label = "Add 3D Point"
    bl_operator = Operators.AddPoint3D
    bl_icon = get_addon_icon_path("ops.bgs.add_point")
    bl_widget = GizmoGroups.Preselection
    bl_keymap = (
        *disable_gizmos,
        *tool_select,
        *tool_access,
        *operator_access(Operators.AddPoint3D),
    )
