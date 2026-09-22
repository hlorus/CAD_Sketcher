from bpy.types import WorkSpaceTool

from ..declarations import Operators, WorkSpaceTools
from ..keymaps import tool_node


class VIEW3D_T_slvs_fillet(WorkSpaceTool):
    """Pick the edges a Fillet modifier rounds."""

    bl_space_type = "VIEW_3D"
    bl_context_mode = "OBJECT"
    bl_idname = WorkSpaceTools.Fillet
    bl_label = "Fillet"
    bl_description = "Round picked edges of the active object"
    bl_icon = "ops.mesh.bevel"
    bl_operator = Operators.FilletSelect
    bl_keymap = (
        (
            Operators.FilletSelect,
            {"type": "LEFTMOUSE", "value": "PRESS"},
            None,
        ),
        *tool_node,
    )
