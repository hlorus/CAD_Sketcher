from bpy.types import WorkSpaceTool

from ..declarations import GizmoGroups, Operators, WorkSpaceTools
from ..keymaps import tool_generic
from ..stateful_operator.tool import GenericStateTool
from ..stateful_operator.utilities.keymap import operator_access


class VIEW3D_T_slvs_project_element(GenericStateTool, WorkSpaceTool):
    bl_space_type = "VIEW_3D"
    bl_context_mode = "OBJECT"
    bl_idname = WorkSpaceTools.ProjectElement
    bl_label = "Project Element"
    bl_operator = Operators.ProjectElement
    bl_icon = "ops.mesh.knife_project"
    # Hover feedback for the picked mesh vertex/edge/face is driven by the
    # operator's current state types (mesh_element_types) via this gizmo.
    bl_widget = GizmoGroups.ObjectHover
    bl_keymap = (
        *tool_generic,
        *operator_access(Operators.ProjectElement),
    )
