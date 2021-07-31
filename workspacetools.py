from bpy.types import WorkSpaceTool
from . import operators, gizmos

tool_prefix = "sketcher."


def tool_invoke_kmi(button, tool, operator):
    return (
        (
            operators.View3D_OT_invoke_tool.bl_idname,
            {"type": button, "value": "PRESS"},
            {"properties": [("tool", tool), ("operator", operator)]},
        ),
    )


tool_access = (
    *tool_invoke_kmi(
        "L", "sketcher.slvs_add_line2d", operators.View3D_OT_slvs_add_line2d.bl_idname
    ),
    *tool_invoke_kmi(
        "C",
        "sketcher.slvs_add_circle2d",
        operators.View3D_OT_slvs_add_circle2d.bl_idname,
    ),
    *tool_invoke_kmi(
        "A", "sketcher.slvs_add_arc2d", operators.View3D_OT_slvs_add_arc2d.bl_idname
    ),
    *tool_invoke_kmi(
        "S", "sketcher.slvs_add_arc2d", operators.View3D_OT_slvs_add_sketch.bl_idname
    ),
)


class VIEW3D_T_slvs_select(WorkSpaceTool):
    bl_space_type = "VIEW_3D"
    bl_context_mode = "OBJECT"
    bl_idname = tool_prefix + "slvs_select"
    bl_label = "Solvespace Select"
    bl_description = "Select Solvespace Entities"
    bl_icon = "ops.generic.select"
    bl_widget = gizmos.VIEW3D_GGT_slvs_preselection.bl_idname
    bl_keymap = (
        (
            operators.View3D_OT_slvs_select_all.bl_idname,
            {"type": "ESC", "value": "PRESS"},
            {"properties": [("deselect", True)]},
        ),
        (
            operators.View3D_OT_slvs_select_all.bl_idname,
            {"type": "A", "value": "PRESS", "ctrl": True},
            {"properties": [("deselect", False)]},
        ),
        (
            operators.View3D_OT_slvs_select.bl_idname,
            {"type": "LEFTMOUSE", "value": "CLICK"},
            None,
        ),
        (
            operators.View3D_OT_slvs_tweak.bl_idname,
            {"type": "LEFTMOUSE", "value": "CLICK_DRAG"},
            None,
        ),
        (
            operators.View3D_OT_slvs_tweak.bl_idname,
            {"type": "LEFTMOUSE", "value": "PRESS", "ctrl": True},
            None,
        ),
        (
            operators.View3D_OT_slvs_context_menu.bl_idname,
            {"type": "RIGHTMOUSE", "value": "PRESS"},
            None,
        ),
        (
            operators.View3D_OT_slvs_delete_entity.bl_idname,
            {"type": "DEL", "value": "PRESS"},
            None,
        ),
        *tool_access,
    )

    def draw_settings(context, layout, tool):
        props = tool.operator_properties(operators.View3D_OT_slvs_select.bl_idname)


tool_keymap = (
    (
        "wm.tool_set_by_id",
        {"type": "ESC", "value": "PRESS"},
        {"properties": [("name", VIEW3D_T_slvs_select.bl_idname)]},
    ),
    (
        operators.View3D_OT_slvs_context_menu.bl_idname,
        {"type": "RIGHTMOUSE", "value": "PRESS"},
        None,
    ),
)


class View3D_T_slvs_add_point3d(WorkSpaceTool):
    bl_space_type = "VIEW_3D"
    bl_context_mode = "OBJECT"
    bl_idname = tool_prefix + "slvs_add_point3d"
    bl_label = "Add 3D Point"
    bl_description = "Add a Point"
    bl_icon = ""
    bl_widget = gizmos.VIEW3D_GGT_slvs_preselection.bl_idname
    bl_keymap = (
        *tool_keymap,
        *tool_access,
        (
            operators.View3D_OT_slvs_add_point3d.bl_idname,
            {"type": "LEFTMOUSE", "value": "PRESS"},
            None,
        ),
    )


class View3D_T_slvs_add_point2d(WorkSpaceTool):
    bl_space_type = "VIEW_3D"
    bl_context_mode = "OBJECT"
    bl_idname = tool_prefix + "slvs_add_point2d"
    bl_label = "Add 2D Point"
    bl_description = "Add a Point to the active workplane"
    bl_icon = ""
    bl_widget = gizmos.VIEW3D_GGT_slvs_preselection.bl_idname
    bl_keymap = (
        *tool_keymap,
        *tool_access,
        (
            operators.View3D_OT_slvs_add_point2d.bl_idname,
            {"type": "LEFTMOUSE", "value": "PRESS"},
            None,
        ),
    )


class View3D_T_slvs_add_line3d(WorkSpaceTool):
    bl_space_type = "VIEW_3D"
    bl_context_mode = "OBJECT"
    bl_idname = tool_prefix + "slvs_add_line3d"
    bl_label = "Add 3D Line"
    bl_description = "Add a Line"
    bl_icon = "ops.gpencil.primitive_line"
    bl_widget = gizmos.VIEW3D_GGT_slvs_preselection.bl_idname
    bl_keymap = (
        *tool_keymap,
        *tool_access,
        (
            operators.View3D_OT_slvs_add_line3d.bl_idname,
            {"type": "LEFTMOUSE", "value": "PRESS"},
            {"properties": [("wait_for_input", False)]},
        ),
    )


class View3D_T_slvs_add_line2d(WorkSpaceTool):
    bl_space_type = "VIEW_3D"
    bl_context_mode = "OBJECT"
    bl_idname = tool_prefix + "slvs_add_line2d"
    bl_label = "Add 2D Line"
    bl_description = "Add a Line to the active sketch"
    bl_icon = "ops.gpencil.primitive_line"
    bl_widget = gizmos.VIEW3D_GGT_slvs_preselection.bl_idname
    bl_keymap = (
        *tool_keymap,
        *tool_access,
        (
            operators.View3D_OT_slvs_add_line2d.bl_idname,
            {"type": "LEFTMOUSE", "value": "PRESS"},
            {"properties": [("wait_for_input", False)]},
        ),
    )


class View3D_T_slvs_add_circle2d(WorkSpaceTool):
    bl_space_type = "VIEW_3D"
    bl_context_mode = "OBJECT"
    bl_idname = tool_prefix + "slvs_add_circle2d"
    bl_label = "Add 2D Circle"
    bl_description = "Add a Circle to the active sketch"
    bl_icon = "ops.gpencil.primitive_circle"
    bl_widget = gizmos.VIEW3D_GGT_slvs_preselection.bl_idname
    bl_keymap = (
        *tool_keymap,
        *tool_access,
        (
            operators.View3D_OT_slvs_add_circle2d.bl_idname,
            {"type": "LEFTMOUSE", "value": "PRESS"},
            {"properties": [("wait_for_input", False)]},
        ),
    )


class View3D_T_slvs_add_arc2d(WorkSpaceTool):
    bl_space_type = "VIEW_3D"
    bl_context_mode = "OBJECT"
    bl_idname = tool_prefix + "slvs_add_arc2d"
    bl_label = "Add 2D Arc"
    bl_description = "Add a Arc to the active sketch"
    bl_icon = "ops.gpencil.primitive_arc"
    bl_widget = gizmos.VIEW3D_GGT_slvs_preselection.bl_idname
    bl_keymap = (
        *tool_keymap,
        *tool_access,
        (
            operators.View3D_OT_slvs_add_arc2d.bl_idname,
            {"type": "LEFTMOUSE", "value": "PRESS"},
            {"properties": [("wait_for_input", False)]},
        ),
    )


# TODO:
# class View3D_T_slvs_add_sketch(WorkSpaceTool):
#     bl_space_type = 'VIEW_3D'
#     bl_context_mode = 'OBJECT'
#     bl_idname = tool_prefix + "slvs_add_sketch"
#     bl_label = "Add 2D Sketch"
#     bl_description = "Add a sketch"
#     bl_icon = ""
#     bl_widget = gizmos.VIEW3D_GGT_slvs_preselection.bl_idname
#     bl_keymap = (
#         *tool_keymap,
#         *tool_access,
#         (operators.View3D_OT_slvs_add_sketch.bl_idname, {"type": 'LEFTMOUSE', "value": 'PRESS'}, {"properties": [('wait_for_input', False)]}),
#     )


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
)


def register():
    from bpy.utils import register_tool

    for tool in tools:
        register_tool(tool[0], **tool[1])


def unregister():
    from bpy.utils import unregister_tool

    for tool in reversed(tools):
        unregister_tool(tool[0])
