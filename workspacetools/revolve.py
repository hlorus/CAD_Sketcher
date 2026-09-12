from bpy.types import WorkSpaceTool

from ..declarations import GizmoGroups, Operators, WorkSpaceTools
from ..keymaps import tool_node
from ..stateful_operator.tool import GenericStateTool
from ..stateful_operator.utilities.keymap import operator_access
from ..utilities.preferences import get_prefs


class VIEW3D_T_slvs_node_revolve(GenericStateTool, WorkSpaceTool):
    bl_space_type = "VIEW_3D"
    bl_context_mode = "OBJECT"
    bl_idname = WorkSpaceTools.Revolve
    bl_label = "Revolve"
    bl_operator = Operators.NodeRevolve
    bl_icon = "ops.mesh.spin"
    bl_widget = GizmoGroups.ObjectHover
    bl_keymap = (
        *tool_node,
        *operator_access(Operators.NodeRevolve),
    )

    def draw_settings(context, layout, tool):
        # Shared across the boolean-capable tools: the single addon preference
        # gating whether a new solid auto-booleans into overlapping bodies.
        layout.prop(get_prefs(), "use_auto_boolean")
