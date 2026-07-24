from bpy.types import WorkSpaceTool

from ..declarations import GizmoGroups, Operators, WorkSpaceTools
from ..keymaps import tool_node
from ..stateful_operator.tool import GenericStateTool
from ..stateful_operator.utilities.keymap import operator_access


class VIEW3D_T_slvs_node_array_linear(GenericStateTool, WorkSpaceTool):
    bl_space_type = "VIEW_3D"
    bl_context_mode = "OBJECT"
    bl_idname = WorkSpaceTools.ArrayLinear
    bl_label = "Linear Array"
    bl_operator = Operators.NodeArrayLinear
    bl_icon = "ops.mesh.dupli_extrude_cursor"
    bl_widget = GizmoGroups.ObjectHover
    bl_keymap = (
        *tool_node,
        *operator_access(Operators.NodeArrayLinear),
    )
