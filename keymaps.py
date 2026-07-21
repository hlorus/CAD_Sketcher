import bpy

from .declarations import BLENDER_SELECT_TOOL, Macros, Operators, WorkSpaceTools
from .stateful_operator.constants import Operators as StatefulOps
from .stateful_operator.utilities.keymap import tool_invoke_kmi

constraint_access = (
    (
        Operators.AddCoincident,
        {"type": "C", "value": "PRESS", "shift": True},
        {
            "properties": [
                ("wait_for_input", True),
            ]
        },
    ),
    (
        Operators.MergePoints,
        {"type": "M", "value": "PRESS", "alt": True},
        None,
    ),
    (
        Operators.AddVertical,
        {"type": "V", "value": "PRESS", "shift": True},
        {
            "properties": [
                ("wait_for_input", True),
            ]
        },
    ),
    (
        Operators.AddHorizontal,
        {"type": "H", "value": "PRESS", "shift": True},
        {
            "properties": [
                ("wait_for_input", True),
            ]
        },
    ),
    (
        Operators.AddEqual,
        {"type": "E", "value": "PRESS", "shift": True},
        {
            "properties": [
                ("wait_for_input", True),
            ]
        },
    ),
    (
        Operators.AddParallel,
        {"type": "A", "value": "PRESS", "shift": True},
        {
            "properties": [
                ("wait_for_input", True),
            ]
        },
    ),
    (
        Operators.AddPerpendicular,
        {"type": "P", "value": "PRESS", "shift": True},
        {
            "properties": [
                ("wait_for_input", True),
            ]
        },
    ),
    (
        Operators.AddTangent,
        {"type": "T", "value": "PRESS", "shift": True},
        {
            "properties": [
                ("wait_for_input", True),
            ]
        },
    ),
    (
        Operators.AddMidPoint,
        {"type": "M", "value": "PRESS", "shift": True},
        {
            "properties": [
                ("wait_for_input", True),
            ]
        },
    ),
    (
        Operators.AddRatio,
        {"type": "R", "value": "PRESS", "shift": True},
        {
            "properties": [
                ("wait_for_input", True),
            ]
        },
    ),
    # Dimensional Constraints
    (
        Operators.AddDistance,
        {"type": "D", "value": "PRESS", "alt": True},
        {
            "properties": [
                ("wait_for_input", True),
            ]
        },
    ),
    (
        Operators.AddDistance,
        {"type": "V", "value": "PRESS", "alt": True},
        {"properties": [("wait_for_input", True), ("align", "VERTICAL")]},
    ),
    (
        Operators.AddDistance,
        {"type": "H", "value": "PRESS", "alt": True},
        {"properties": [("wait_for_input", True), ("align", "HORIZONTAL")]},
    ),
    (
        Operators.AddAngle,
        {"type": "A", "value": "PRESS", "alt": True},
        {
            "properties": [
                ("wait_for_input", True),
            ]
        },
    ),
    (
        Operators.AddDiameter,
        {"type": "O", "value": "PRESS", "alt": True},
        {
            "properties": [
                ("wait_for_input", True),
            ]
        },
    ),
    (
        Operators.AddDiameter,
        {"type": "R", "value": "PRESS", "alt": True},
        {"properties": [("wait_for_input", True), ("setting", True)]},
    ),
)

tool_access = (
    tool_invoke_kmi(
        "P",
        WorkSpaceTools.AddPoint2D,
        Operators.AddPoint2D,
    ),
    tool_invoke_kmi(
        "L",
        WorkSpaceTools.AddLine2D,
        Operators.AddLine2D,
    ),
    tool_invoke_kmi(
        "C",
        WorkSpaceTools.AddCircle2D,
        Operators.AddCircle2D,
    ),
    tool_invoke_kmi(
        "A",
        WorkSpaceTools.AddArc2D,
        Operators.AddArc2D,
    ),
    tool_invoke_kmi(
        "R",
        WorkSpaceTools.AddRectangle,
        Operators.AddRectangle,
    ),
    tool_invoke_kmi(
        "Y",
        WorkSpaceTools.Trim,
        Operators.Trim,
    ),
    tool_invoke_kmi(
        "B",
        WorkSpaceTools.Bevel,
        Operators.Bevel,
    ),
    tool_invoke_kmi(
        "O",
        WorkSpaceTools.Offset,
        Operators.Offset
    ),
    tool_invoke_kmi(
        "S",
        WorkSpaceTools.AddSketch,
        Operators.AddSketch,
    ),
    *constraint_access,
)

node_access = (
    tool_invoke_kmi(
        "E",
        WorkSpaceTools.Extrude,
        Operators.NodeExtrude,
    ),
    tool_invoke_kmi(
        "D",
        WorkSpaceTools.ArrayLinear,
        Operators.NodeArrayLinear,
    ),
    tool_invoke_kmi(
        "S",
        WorkSpaceTools.AddSketch,
        Operators.AddSketch,
    ),
)

disable_gizmos = (
    # Disabling gizmos when pressing ctrl + shift
    # Add two entries so it doesn't matter which key is pressed first
    # NOTE: This cannot be done as a normal modifier key to selection since it has to toggle a global property
    (
        "wm.context_set_boolean",
        {"type": "LEFT_SHIFT", "value": "PRESS", "ctrl": True},
        {
            "properties": [
                ("data_path", "scene.sketcher.selectable_constraints"),
                ("value", False),
            ]
        },
    ),
    (
        "wm.context_set_boolean",
        {"type": "LEFT_CTRL", "value": "PRESS", "shift": True},
        {
            "properties": [
                ("data_path", "scene.sketcher.selectable_constraints"),
                ("value", False),
            ]
        },
    ),
    (
        "wm.context_set_boolean",
        {"type": "LEFT_SHIFT", "value": "RELEASE", "any": True},
        {
            "properties": [
                ("data_path", "scene.sketcher.selectable_constraints"),
                ("value", True),
            ]
        },
    ),
)

use_construction = (
    "wm.context_toggle",
    {"type": "C", "value": "PRESS", "alt": True, "shift": True},
    {
        "properties": [
            ("data_path", "scene.sketcher.use_construction"),
        ]
    },
)

tool_use_select = (
    (
        "wm.tool_set_by_id",
        {"type": "ESC", "value": "PRESS"},
        {"properties": [("name", BLENDER_SELECT_TOOL)]},
    ),
    (
        "wm.tool_set_by_id",
        {"type": "RIGHTMOUSE", "value": "PRESS"},
        {"properties": [("name", BLENDER_SELECT_TOOL)]},
    ),
)
tool_base_keymap = (
    (
        Operators.DeleteEntity,
        {"type": "DEL", "value": "PRESS"},
        None,
    ),
    (
        Operators.DeleteEntity,
        {"type": "X", "value": "PRESS"},
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
    (
        Operators.AlignView,
        {"type": "V", "value": "PRESS"},
        {"properties": [("use_active", True)]},
    ),
)

tool_generic = (
    *tool_base_keymap,
    *disable_gizmos,
    use_construction,
    *tool_use_select,
    *tool_access,
)

tool_node = (
    *node_access,
)

tool_select = (
    *tool_base_keymap,
    *disable_gizmos,
    *tool_access,
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
)

addon_keymaps = []


def register():
    wm = bpy.context.window_manager
    if wm.keyconfigs.addon:
        km = wm.keyconfigs.addon.keymaps.new(name="Object Mode", space_type="EMPTY")

        # Select
        kmi = km.keymap_items.new("wm.tool_set_by_id", "ESC", "PRESS", shift=True)
        kmi.properties.name = BLENDER_SELECT_TOOL
        addon_keymaps.append((km, kmi))

        # Add Sketch: switch to the Add Sketch tool (workplane gizmo), then
        # invoke the operator (a pre-selected workplane creates immediately).
        kmi = km.keymap_items.new(
            StatefulOps.InvokeTool.value, "A", "PRESS", ctrl=True, shift=True
        )
        kmi.properties.tool_name = WorkSpaceTools.AddSketch.value
        kmi.properties.operator = Operators.AddSketch.value
        addon_keymaps.append((km, kmi))

        # Leave Sketch (same shortcut as add sketch)
        kmi = km.keymap_items.new(
            Operators.SetActiveSketch, "A", "PRESS", ctrl=True, shift=True
        )
        kmi.properties.sketch_name = ""
        addon_keymaps.append((km, kmi))

        # Extrude: switch to the Extrude tool, then invoke the operator.
        kmi = km.keymap_items.new(
            StatefulOps.InvokeTool.value, "E", "PRESS", ctrl=True, shift=True
        )
        kmi.properties.tool_name = WorkSpaceTools.Extrude.value
        kmi.properties.operator = Operators.NodeExtrude.value
        addon_keymaps.append((km, kmi))

        # Linear Array: switch to the tool, then invoke the operator.
        kmi = km.keymap_items.new(
            StatefulOps.InvokeTool.value, "D", "PRESS", ctrl=True, shift=True
        )
        kmi.properties.tool_name = WorkSpaceTools.ArrayLinear.value
        kmi.properties.operator = Operators.NodeArrayLinear.value
        addon_keymaps.append((km, kmi))



def unregister():
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if kc:
        for km, kmi in addon_keymaps:
            km.keymap_items.remove(kmi)
            addon_keymaps.clear()
