from bpy.types import WorkSpaceTool

from ..declarations import GizmoGroups, Operators, WorkSpaceTools
from ..keymaps import tool_generic
from ..stateful_operator.tool import GenericStateTool
from ..stateful_operator.utilities.keymap import operator_access


class VIEW3D_T_slvs_add_rectangle(GenericStateTool, WorkSpaceTool):
    bl_space_type = "VIEW_3D"
    bl_context_mode = "OBJECT"
    bl_idname = WorkSpaceTools.AddRectangle
    bl_label = "Corner Rectangle"
    bl_description = "Add a rectangle from two opposite corners"
    bl_operator = Operators.AddRectangle
    bl_icon = "ops.gpencil.primitive_box"
    bl_widget = GizmoGroups.Preselection
    bl_keymap = (
        *tool_generic,
        *operator_access(Operators.AddRectangle),
    )

    def draw_settings(context, layout, tool):
        layout.prop(
            context.scene.sketcher, "auto_axis_constraints", text="Auto Constraints"
        )
        layout.prop(
            context.scene.sketcher, "use_snap_project", text="Live Project Snaps"
        )


class VIEW3D_T_slvs_add_rectangle_center(GenericStateTool, WorkSpaceTool):
    bl_space_type = "VIEW_3D"
    bl_context_mode = "OBJECT"
    bl_idname = WorkSpaceTools.AddRectangleCenter
    bl_label = "Center Rectangle"
    bl_description = "Add a rectangle from its center and one corner"
    bl_operator = Operators.AddRectangleCenter
    bl_icon = "ops.gpencil.primitive_box"
    bl_widget = GizmoGroups.Preselection
    bl_keymap = (
        *tool_generic,
        *operator_access(Operators.AddRectangleCenter),
    )

    draw_settings = VIEW3D_T_slvs_add_rectangle.draw_settings


class VIEW3D_T_slvs_add_rectangle_3point(GenericStateTool, WorkSpaceTool):
    bl_space_type = "VIEW_3D"
    bl_context_mode = "OBJECT"
    bl_idname = WorkSpaceTools.AddRectangle3Point
    bl_label = "3-Point Rectangle"
    bl_description = "Add a rectangle from one edge and its width, at any angle"
    bl_operator = Operators.AddRectangle3Point
    bl_icon = "ops.gpencil.primitive_box"
    bl_widget = GizmoGroups.Preselection
    bl_keymap = (
        *tool_generic,
        *operator_access(Operators.AddRectangle3Point),
    )

    draw_settings = VIEW3D_T_slvs_add_rectangle.draw_settings
