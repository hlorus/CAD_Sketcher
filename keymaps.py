import bpy

from .declarations import BLENDER_SELECT_TOOL, Macros, Operators, WorkSpaceTools
from .stateful_operator.constants import Operators as StatefulOps
from .stateful_operator.utilities.keymap import tool_invoke_kmi
from .stateful_operator.utilities.switch import (
    clear_switch_operators,
    register_switch_operator,
)

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
    # Dimensions: the Dimension tool, preset to one kind.
    *(
        (
            Operators.AddDimension,
            {"type": key, "value": "PRESS", "alt": True},
            {"properties": [("wait_for_input", True), *flags]},
        )
        for key, flags in (
            ("D", [("kind", "DISTANCE")]),
            ("V", [("kind", "DISTANCE"), ("align", "VERTICAL")]),
            ("H", [("kind", "DISTANCE"), ("align", "HORIZONTAL")]),
            ("A", [("kind", "ANGLE")]),
            ("O", [("kind", "DIAMETER")]),
            ("R", [("kind", "DIAMETER"), ("radius", True)]),
        )
    ),
)

# Tool shortcuts: (tool, operator, key). The key starts the tool from any other
# CAD Sketcher tool, also while one is running.
SKETCH_TOOL_KEYS = (
    (WorkSpaceTools.AddPoint2D, Operators.AddPoint2D, "P"),
    (WorkSpaceTools.AddLine2D, Operators.AddLine2D, "L"),
    (WorkSpaceTools.AddCircle2D, Operators.AddCircle2D, "C"),
    (WorkSpaceTools.AddArc2D, Operators.AddArc2D, "A"),
    (WorkSpaceTools.AddRectangle, Operators.AddRectangle, "R"),
    (WorkSpaceTools.Trim, Operators.Trim, "Y"),
    (WorkSpaceTools.Bevel, Operators.Bevel, "B"),
    (WorkSpaceTools.Offset, Operators.Offset, "O"),
    (WorkSpaceTools.AddDimension, Operators.AddDimension, "D"),
    # Does nothing inside a sketch, but keeps S from scaling the sketch object.
    (WorkSpaceTools.AddSketch, Operators.AddSketch, "S"),
    # "P" is already the Add Point tool, so Project Geometry uses "J".
    (WorkSpaceTools.ProjectGeometry, Operators.ProjectGeometry, "J"),
)

SKETCH_3D_TOOL_KEYS = (
    (WorkSpaceTools.AddPoint3D, Operators.AddPoint3D, "P"),
    (WorkSpaceTools.AddLine3D, Operators.AddLine3D, "L"),
)

# Object tools also get a global Ctrl+Shift key: (tool, operator, key, global key).
NODE_TOOL_KEYS = (
    (WorkSpaceTools.Extrude, Operators.NodeExtrude, "E", "E"),
    (WorkSpaceTools.Revolve, Operators.NodeRevolve, "R", "R"),
    (WorkSpaceTools.ArrayLinear, Operators.NodeArrayLinear, "D", "D"),
    # Ctrl+Shift+S saves as, so Add Sketch uses Ctrl+Shift+A.
    (WorkSpaceTools.AddSketch, Operators.AddSketch, "S", "A"),
)


def tool_keys(table) -> tuple:
    """Tool keymap items starting each tool of ``table`` by its key."""
    return tuple(tool_invoke_kmi(key, tool, op) for tool, op, key, *_ in table)


tool_access = (
    *tool_keys(SKETCH_TOOL_KEYS),
    *constraint_access,
)

node_access = tool_keys(NODE_TOOL_KEYS)

use_construction = (
    "wm.context_toggle",
    {"type": "C", "value": "PRESS", "alt": True, "shift": True},
    {
        "properties": [
            ("data_path", "scene.sketcher.use_construction"),
        ]
    },
)

# ESC / RMB from a sketch drawing tool returns to the slvs Select tool. Only
# used by tool_generic, whose tools are all sketch-mode, so slvs_select is
# always registered here.
tool_use_select = (
    (
        "wm.tool_set_by_id",
        {"type": "ESC", "value": "PRESS"},
        {"properties": [("name", WorkSpaceTools.Select)]},
    ),
    (
        "wm.tool_set_by_id",
        {"type": "RIGHTMOUSE", "value": "PRESS"},
        {"properties": [("name", WorkSpaceTools.Select)]},
    ),
)

# ESC/RMB -> Blender's builtin select, for non-sketch tools (the slvs_select
# tool only exists in sketch mode; outside it, tool_set_by_id would no-op).
tool_use_select_builtin = (
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
    use_construction,
    *tool_use_select,
    *tool_access,
)

tool_node = (
    *node_access,
    *tool_use_select_builtin,
)

tool_select = (
    *tool_base_keymap,
    *tool_access,
    use_construction,
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
    # Alt+click: select the next entity in the overlapping stack (issue #50).
    (
        Operators.Select,
        {"type": "LEFTMOUSE", "value": "CLICK", "alt": True},
        {"properties": [("cycle", True)]},
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

        # Cycle the hovered element through overlapping entities under the cursor
        # (issue #50). Alt+wheel, so it does not collide with zoom; a no-op unless
        # more than one entity is stacked under the cursor.
        for event_type, direction in (("WHEELUPMOUSE", 1), ("WHEELDOWNMOUSE", -1)):
            kmi = km.keymap_items.new(
                Operators.HoverCycle, event_type, "PRESS", alt=True
            )
            kmi.properties.direction = direction
            addon_keymaps.append((km, kmi))

        # Boolean: no workspacetool, so invoke the operator directly. It prefills
        # the body/cutter from the selection or lets them be picked, same as the
        # other node tools.
        kmi = km.keymap_items.new(
            Operators.NodeBoolean.value, "B", "PRESS", ctrl=True, shift=True
        )
        addon_keymaps.append((km, kmi))

        # Switch to a tool, then invoke its operator. Inside a sketch the tool
        # isn't available and the key passes on (Ctrl+Shift+A leaves the sketch).
        for tool, operator, _key, key in NODE_TOOL_KEYS:
            kmi = km.keymap_items.new(
                StatefulOps.InvokeTool.value, key, "PRESS", ctrl=True, shift=True
            )
            kmi.properties.tool_name = tool.value
            kmi.properties.operator = operator.value
            kmi.properties.fallthrough = True
            addon_keymaps.append((km, kmi))

        # Leave Sketch (same shortcut as add sketch). Passes the key on when no
        # sketch is active.
        kmi = km.keymap_items.new(
            Operators.SetActiveSketch, "A", "PRESS", ctrl=True, shift=True
        )
        kmi.properties.sketch_name = ""
        addon_keymaps.append((km, kmi))

    # Shortcuts that interrupt a running tool, besides tool switches.
    for _op, _event, _props in constraint_access:
        register_switch_operator(_op)
    register_switch_operator(Operators.NodeBoolean)
    register_switch_operator(Operators.SetActiveSketch, _leaves_sketch)
    # Toggling construction applies to what is being drawn.
    register_switch_operator(
        use_construction[0], _toggles_construction, keep_running=True
    )


def _toggles_construction(context, kmi) -> bool:
    return kmi.properties.data_path == "scene.sketcher.use_construction"


def _leaves_sketch(context, kmi) -> bool:
    from .model.sketch_ref import get_active_sketch

    return not kmi.properties.sketch_name and bool(get_active_sketch(context))


def unregister():
    clear_switch_operators()
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if kc:
        for km, kmi in addon_keymaps:
            km.keymap_items.remove(kmi)
    addon_keymaps.clear()
