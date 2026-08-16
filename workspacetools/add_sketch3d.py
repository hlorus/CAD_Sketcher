from bpy.types import WorkSpaceTool

from ..declarations import Operators, WorkSpaceTools
from ..keymaps import tool_node
from ..stateful_operator.tool import GenericStateTool
from ..stateful_operator.utilities.keymap import operator_access


class VIEW3D_T_slvs_add_sketch3d(GenericStateTool, WorkSpaceTool):
    bl_space_type = "VIEW_3D"
    bl_context_mode = "OBJECT"
    bl_idname = WorkSpaceTools.AddSketch3D
    bl_label = "Add 3D Sketch"
    bl_operator = Operators.AddSketch3D
    bl_icon = "ops.mesh.primitive_grid_add_gizmo"
    bl_keymap = (
        *tool_node,
        *operator_access(Operators.AddSketch3D),
    )
