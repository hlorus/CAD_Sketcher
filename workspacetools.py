from bpy.types import WorkSpaceTool
import os

from .declarations import GizmoGroups, Operators, WorkSpaceTools
from .keymaps import tool_access
from .stateful_operator.utilities.keymap import operator_access
from .stateful_operator.tool import GenericStateTool


def get_addon_icon_path(icon_name):
    return os.path.join(os.path.dirname(__file__), "ressources/icons", icon_name)


generic_keymap = (
    (
        "wm.context_set_boolean",
        {"type": "LEFT_SHIFT", "value": "PRESS"},
        {
            "properties": [
                ("data_path", "scene.sketcher.selectable_constraints"),
                ("value", False),
            ]
        },
    ),
    (
        "wm.context_set_boolean",
        {"type": "LEFT_SHIFT", "value": "RELEASE"},
        {
            "properties": [
                ("data_path", "scene.sketcher.selectable_constraints"),
                ("value", True),
            ]
        },
    ),
)


class VIEW3D_T_slvs_select(WorkSpaceTool):
    bl_space_type = "VIEW_3D"
    bl_context_mode = "OBJECT"
    bl_idname = WorkSpaceTools.Select
    bl_label = "Solvespace Select"
    bl_description = "Select Solvespace Entities"
    bl_icon = "ops.generic.select"
    bl_widget = GizmoGroups.Preselection
    bl_keymap = (
        *generic_keymap,
        (
            Operators.SelectAll,
            {"type": "ESC", "value": "PRESS"},
            {"properties": [("deselect", True)]},
        ),
        (
            Operators.SelectAll,
            {"type": "A", "value": "PRESS", "ctrl": True},
            {"properties": [("deselect", False)]},
        ),
        (
            Operators.Select,
            {"type": "LEFTMOUSE", "value": "CLICK"},
            None,
        ),
        (Operators.SelectInvert, {"type": "I", "value": "PRESS", "ctrl": True}, None),
        (Operators.SelectExtend, {"type": "E", "value": "PRESS", "ctrl": True}, None),
        (
            Operators.SelectExtendAll,
            {"type": "E", "value": "PRESS", "ctrl": True, "shift": True},
            None,
        ),
        (
            Operators.Tweak,
            {"type": "LEFTMOUSE", "value": "CLICK_DRAG"},
            None,
        ),
        (
            Operators.Tweak,
            {"type": "LEFTMOUSE", "value": "PRESS", "ctrl": True},
            None,
        ),
        (
            Operators.ContextMenu,
            {"type": "RIGHTMOUSE", "value": "PRESS"},
            {"properties": [("delayed", True)]},
        ),
        (
            Operators.DeleteEntity,
            {"type": "DEL", "value": "PRESS"},
            None,
        ),
        *tool_access,
    )

    def draw_settings(context, layout, tool):
        props = tool.operator_properties(Operators.Select)


tool_keymap = (
    *generic_keymap,
    (
        "wm.tool_set_by_id",
        {"type": "ESC", "value": "PRESS"},
        {"properties": [("name", VIEW3D_T_slvs_select.bl_idname)]},
    ),
    (
        "wm.tool_set_by_id",
        {"type": "RIGHTMOUSE", "value": "PRESS"},
        {"properties": [("name", VIEW3D_T_slvs_select.bl_idname)]},
    ),
)


class View3D_T_slvs_add_point3d(GenericStateTool, WorkSpaceTool):
    bl_space_type = "VIEW_3D"
    bl_context_mode = "OBJECT"
    bl_idname = WorkSpaceTools.AddPoint3D
    bl_label = "Add 3D Point"
    bl_operator = Operators.AddPoint3D
    bl_icon = get_addon_icon_path("ops.bgs.add_point")
    bl_widget = GizmoGroups.Preselection
    bl_keymap = (
        *tool_keymap,
        *tool_access,
        *operator_access(Operators.AddPoint3D),
    )


class View3D_T_slvs_add_point2d(GenericStateTool, WorkSpaceTool):
    bl_space_type = "VIEW_3D"
    bl_context_mode = "OBJECT"
    bl_idname = WorkSpaceTools.AddPoint2D
    bl_label = "Add 2D Point"
    bl_operator = Operators.AddPoint2D
    bl_icon = get_addon_icon_path("ops.bgs.add_point")
    bl_widget = GizmoGroups.Preselection
    bl_keymap = (
        *tool_keymap,
        *tool_access,
        *operator_access(Operators.AddPoint2D),
    )


class View3D_T_slvs_add_line3d(GenericStateTool, WorkSpaceTool):
    bl_space_type = "VIEW_3D"
    bl_context_mode = "OBJECT"
    bl_idname = WorkSpaceTools.AddLine3D
    bl_label = "Add 3D Line"
    bl_operator = Operators.AddLine3D
    bl_icon = "ops.gpencil.primitive_line"
    bl_widget = GizmoGroups.Preselection
    bl_keymap = (
        *tool_keymap,
        *tool_access,
        *operator_access(Operators.AddLine3D),
    )

    def draw_settings(context, layout, tool):
        props = tool.operator_properties(Operators.AddLine3D)
        layout.prop(props, "continuous_draw")


class View3D_T_slvs_add_line2d(GenericStateTool, WorkSpaceTool):
    bl_space_type = "VIEW_3D"
    bl_context_mode = "OBJECT"
    bl_idname = WorkSpaceTools.AddLine2D
    bl_label = "Add 2D Line"
    bl_operator = Operators.AddLine2D
    bl_icon = "ops.gpencil.primitive_line"
    bl_widget = GizmoGroups.Preselection
    bl_keymap = (
        *tool_keymap,
        *tool_access,
        *operator_access(Operators.AddLine2D),
    )

    def draw_settings(context, layout, tool):
        props = tool.operator_properties(Operators.AddLine2D)
        layout.prop(props, "continuous_draw")


class View3D_T_slvs_add_circle2d(GenericStateTool, WorkSpaceTool):
    bl_space_type = "VIEW_3D"
    bl_context_mode = "OBJECT"
    bl_idname = WorkSpaceTools.AddCircle2D
    bl_label = "Add 2D Circle"
    bl_operator = Operators.AddCircle2D
    bl_icon = "ops.gpencil.primitive_circle"
    bl_widget = GizmoGroups.Preselection
    bl_keymap = (
        *tool_keymap,
        *tool_access,
        *operator_access(Operators.AddCircle2D),
    )


class View3D_T_slvs_add_arc2d(GenericStateTool, WorkSpaceTool):
    bl_space_type = "VIEW_3D"
    bl_context_mode = "OBJECT"
    bl_idname = WorkSpaceTools.AddArc2D
    bl_label = "Add 2D Arc"
    bl_operator = Operators.AddArc2D
    bl_icon = "ops.gpencil.primitive_arc"
    bl_widget = GizmoGroups.Preselection
    bl_keymap = (
        *tool_keymap,
        *tool_access,
        *operator_access(Operators.AddArc2D),
    )


class View3D_T_slvs_add_rectangle(GenericStateTool, WorkSpaceTool):
    bl_space_type = "VIEW_3D"
    bl_context_mode = "OBJECT"
    bl_idname = WorkSpaceTools.AddRectangle
    bl_label = "Add Rectangle"
    bl_operator = Operators.AddRectangle
    bl_icon = "ops.gpencil.primitive_box"
    bl_widget = GizmoGroups.Preselection
    bl_keymap = (
        *tool_keymap,
        *tool_access,
        *operator_access(Operators.AddRectangle),
    )


class View3D_T_slvs_trim(GenericStateTool, WorkSpaceTool):
    bl_space_type = "VIEW_3D"
    bl_context_mode = "OBJECT"
    bl_idname = WorkSpaceTools.Trim
    bl_label = "Trim"
    bl_operator = Operators.Trim
    bl_icon = "ops.gpencil.stroke_cutter"
    bl_widget = GizmoGroups.Preselection
    bl_keymap = (
        *tool_keymap,
        *tool_access,
        *operator_access(Operators.Trim),
    )


class View3D_T_slvs_bevel(GenericStateTool, WorkSpaceTool):
    bl_space_type = "VIEW_3D"
    bl_context_mode = "OBJECT"
    bl_idname = WorkSpaceTools.Bevel
    bl_label = "Bevel"
    bl_operator = Operators.Bevel
    bl_icon = get_addon_icon_path("ops.bgs.bevel")
    bl_widget = GizmoGroups.Preselection
    bl_keymap = (
        *tool_keymap,
        *tool_access,
        *operator_access(Operators.Bevel),
    )


class View3D_T_slvs_add_workplane_face(GenericStateTool, WorkSpaceTool):
    bl_space_type = "VIEW_3D"
    bl_context_mode = "OBJECT"
    bl_idname = WorkSpaceTools.AddWorkplaneFace
    bl_label = "Add Workplane on mesh face"
    bl_operator = Operators.AddWorkPlaneFace
    bl_icon = "ops.mesh.primitive_grid_add_gizmo"
    bl_widget = GizmoGroups.Preselection
    bl_keymap = (
        *tool_keymap,
        *tool_access,
        *operator_access(Operators.AddWorkPlaneFace),
    )


class View3D_T_slvs_add_workplane(GenericStateTool, WorkSpaceTool):
    bl_space_type = "VIEW_3D"
    bl_context_mode = "OBJECT"
    bl_idname = WorkSpaceTools.AddWorkplane
    bl_label = "Add Workplane"
    bl_operator = Operators.AddWorkPlane
    bl_icon = "ops.mesh.primitive_grid_add_gizmo"
    bl_widget = GizmoGroups.Preselection
    bl_keymap = (
        *tool_keymap,
        *tool_access,
        *operator_access(Operators.AddWorkPlane),
    )


tools = (
    (VIEW3D_T_slvs_select, {"separator": True, "group": False}),
    (View3D_T_slvs_add_point2d, {"separator": True, "group": True}),
    (
        View3D_T_slvs_add_point3d,
        {
            "after": {View3D_T_slvs_add_point2d.bl_idname},
        },
    ),
    (View3D_T_slvs_add_line2d, {"separator": False, "group": True}),
    (
        View3D_T_slvs_add_line3d,
        {
            "after": {View3D_T_slvs_add_line2d.bl_idname},
        },
    ),
    (View3D_T_slvs_add_circle2d, {"separator": False, "group": False}),
    (View3D_T_slvs_add_arc2d, {"separator": False, "group": False}),
    (View3D_T_slvs_add_rectangle, {"separator": False, "group": False}),
    (View3D_T_slvs_trim, {"separator": False, "group": False}),
    (View3D_T_slvs_bevel, {"separator": False, "group": False}),
    (View3D_T_slvs_add_workplane_face, {"separator": True, "group": True}),
    (
        View3D_T_slvs_add_workplane,
        {"after": {View3D_T_slvs_add_workplane_face.bl_idname}},
    ),
)

import bpy


def register():
    if bpy.app.background:
        return

    from bpy.utils import register_tool

    for tool in tools:
        register_tool(tool[0], **tool[1])


def unregister():
    if bpy.app.background:
        return

    from bpy.utils import unregister_tool

    for tool in reversed(tools):
        unregister_tool(tool[0])
