from bpy.types import WorkSpaceTool

from ..declarations import GizmoGroups, Operators, WorkSpaceTools, Macros
from ..keymaps import disable_gizmos, tool_access


class VIEW3D_T_slvs_select(WorkSpaceTool):
    bl_space_type = "VIEW_3D"
    bl_context_mode = "OBJECT"
    bl_idname = WorkSpaceTools.Select
    bl_label = "Solvespace Select"
    bl_description = "Select Solvespace Entities"
    bl_icon = "ops.generic.select"
    bl_widget = GizmoGroups.Preselection
    bl_keymap = (
        *disable_gizmos,
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
            {"type": "LEFTMOUSE", "value": "CLICK", "any": True},
            None,
        ),
        (
            Operators.Select,
            {"type": "LEFTMOUSE", "value": "CLICK", "shift": True},
            {"properties": [("mode", "EXTEND")]},
        ),
        (
            Operators.Select,
            {"type": "LEFTMOUSE", "value": "CLICK", "ctrl": True},
            {"properties": [("mode", "SUBTRACT")]},
        ),
        (
            Operators.SelectInvert,
            {"type": "I", "value": "PRESS", "ctrl": True},
            None,
        ),
        (
            Operators.SelectExtend,
            {"type": "E", "value": "PRESS", "ctrl": True},
            None,
        ),
        (
            Operators.SelectExtendAll,
            {"type": "E", "value": "PRESS", "ctrl": True, "shift": True},
            None,
        ),
        (
            Operators.SelectBox,
            {"type": "LEFTMOUSE", "value": "CLICK_DRAG"},
            None,
        ),
        (
            Operators.SelectBox,
            {"type": "LEFTMOUSE", "value": "CLICK_DRAG", "ctrl": True},
            {"properties": [("mode", "SUBTRACT")]},
        ),
        (
            Operators.SelectBox,
            {"type": "LEFTMOUSE", "value": "CLICK_DRAG", "shift": True},
            {"properties": [("mode", "EXTEND")]},
        ),
        # (
        #     Operators.SelectBox,
        #     {"type": "LEFTMOUSE", "value": "CLICK_DRAG", "alt": True},
        #     {"properties": [("mode", "TOGGLE")]},
        # ),
        (
            Operators.Tweak,
            {"type": "LEFTMOUSE", "value": "CLICK_DRAG"},
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
        (
            Operators.Copy,
            {"type": "C", "value": "PRESS", "ctrl": True},
            None,
        ),
        (
            Operators.Paste,
            {"type": "V", "value": "PRESS", "ctrl": True},
            None,
        ),
        (
            Macros.DuplicateMove,
            {"type": "D", "value": "PRESS", "shift": True},
            None,
        ),
        (
            Operators.Move,
            {"type": "G", "value": "PRESS"},
            None,
        ),
        *tool_access,
    )

    def draw_settings(context, layout, tool):
        props = tool.operator_properties(Operators.Select)
        layout.prop(props, "mode", text="", expand=True, icon_only=True)
