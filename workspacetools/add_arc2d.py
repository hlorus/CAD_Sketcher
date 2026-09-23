from bpy.types import WorkSpaceTool

from ..declarations import GizmoGroups, Operators, WorkSpaceTools
from ..keymaps import tool_generic
from ..stateful_operator.tool import GenericStateTool
from ..stateful_operator.utilities.keymap import operator_access


class VIEW3D_T_slvs_add_arc2d(GenericStateTool, WorkSpaceTool):
    bl_space_type = "VIEW_3D"
    bl_context_mode = "OBJECT"
    bl_idname = WorkSpaceTools.AddArc2D
    bl_label = "Add 2D Arc"
    bl_operator = Operators.AddArc2D
    bl_icon = "ops.gpencil.primitive_arc"
    bl_widget = GizmoGroups.Preselection
    bl_keymap = (
        *tool_generic,
        *operator_access(Operators.AddArc2D),
    )

    def draw_settings(context, layout, tool):
        layout.prop(
            context.scene.sketcher, "auto_axis_constraints", text="Auto Constraints"
        )
        layout.prop(
            context.scene.sketcher, "use_snap_project", text="Live Project Snaps"
        )


class VIEW3D_T_slvs_add_arc3pt2d(GenericStateTool, WorkSpaceTool):
    bl_space_type = "VIEW_3D"
    bl_context_mode = "OBJECT"
    bl_idname = WorkSpaceTools.AddArc3Point2D
    bl_label = "Add Endpoint Arc"
    bl_description = (
        "Add an arc from its start and end points, curving the way you set off"
    )
    bl_operator = Operators.AddArc3Point2D
    bl_icon = "ops.gpencil.primitive_arc"
    bl_widget = GizmoGroups.Preselection
    bl_keymap = (
        *tool_generic,
        *operator_access(Operators.AddArc3Point2D),
    )

    def draw_settings(context, layout, tool):
        props = tool.operator_properties(Operators.AddArc3Point2D)
        layout.prop(props, "continuous_draw")
        VIEW3D_T_slvs_add_arc2d.draw_settings(context, layout, tool)
