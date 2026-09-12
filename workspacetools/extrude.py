from bpy.types import WorkSpaceTool

from ..declarations import GizmoGroups, Operators, WorkSpaceTools
from ..keymaps import tool_node
from ..stateful_operator.tool import GenericStateTool
from ..stateful_operator.utilities.keymap import operator_access
from ..utilities.preferences import get_prefs


class VIEW3D_T_slvs_node_extrude(GenericStateTool, WorkSpaceTool):
    bl_space_type = "VIEW_3D"
    bl_context_mode = "OBJECT"
    bl_idname = WorkSpaceTools.Extrude
    bl_label = "Extrude"
    bl_operator = Operators.NodeExtrude
    bl_icon = "ops.mesh.extrude_region_move"
    bl_widget = GizmoGroups.ObjectHover
    bl_keymap = (
        *tool_node,
        *operator_access(Operators.NodeExtrude),
    )

    def draw_settings(context, layout, tool):
        # Shared across the boolean-capable tools: the single addon preference
        # gating whether a new solid auto-booleans into overlapping bodies.
        layout.prop(get_prefs(), "use_auto_boolean")
