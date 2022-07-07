import bpy
from bpy.types import KeyMapItem
from typing import List

from .declarations import Operators, WorkSpaceTools

def tool_invoke_kmi(button, tool, operator):
    return (
        Operators.InvokeTool,
        {"type": button, "value": "PRESS"},
        {"properties": [("tool_name", tool), ("operator", operator)]},
    )

constraint_access = (
    (
        Operators.AddCoincident,
        {"type": "C", "value": "PRESS", "shift": True},
        {"properties": [("wait_for_input", True), ]}
    ),
    (
        Operators.AddVertical,
        {"type": "V", "value": "PRESS", "shift": True},
        {"properties": [("wait_for_input", True), ]}
    ),
    (
        Operators.AddHorizontal,
        {"type": "H", "value": "PRESS", "shift": True},
        {"properties": [("wait_for_input", True), ]}
    ),
    (
        Operators.AddEqual,
        {"type": "E", "value": "PRESS", "shift": True},
        {"properties": [("wait_for_input", True), ]}
    ),
    (
        Operators.AddParallel,
        {"type": "A", "value": "PRESS", "shift": True},
        {"properties": [("wait_for_input", True), ]}
    ),
    (
        Operators.AddPerpendicular,
        {"type": "P", "value": "PRESS", "shift": True},
        {"properties": [("wait_for_input", True), ]}
    ),
    (
        Operators.AddTangent,
        {"type": "T", "value": "PRESS", "shift": True},
        {"properties": [("wait_for_input", True), ]}
    ),
    (
        Operators.AddMidPoint,
        {"type": "M", "value": "PRESS", "shift": True},
        {"properties": [("wait_for_input", True), ]}
    ),
    (
        Operators.AddRatio,
        {"type": "R", "value": "PRESS", "shift": True},
        {"properties": [("wait_for_input", True), ]}
    ),

    # Dimensional Constraints
    (
        Operators.AddDistance,
        {"type": "D", "value": "PRESS", "alt": True},
        {"properties": [("wait_for_input", True), ]}
    ),
    (
        Operators.AddDistance,
        {"type": "V", "value": "PRESS", "alt": True},
        {"properties": [("wait_for_input", True), ("align", "VERTICAL")]}
    ),
    (
        Operators.AddDistance,
        {"type": "H", "value": "PRESS", "alt": True},
        {"properties": [("wait_for_input", True), ("align", "HORIZONTAL")]}
    ),
    (
        Operators.AddAngle,
        {"type": "A", "value": "PRESS", "alt": True},
        {"properties": [("wait_for_input", True), ]}
    ),
    (
        Operators.AddDiameter,
        {"type": "O", "value": "PRESS", "alt": True},
        {"properties": [("wait_for_input", True), ]}
    ),
    (
        Operators.AddDiameter,
        {"type": "R", "value": "PRESS", "alt": True},
        {"properties": [("wait_for_input", True), ("setting", True)]}
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
    (
        Operators.AddSketch,
        {"type": "S", "value": "PRESS"},
        {"properties": [("wait_for_input", True), ]}
    ),
    *constraint_access,
)

addon_keymaps = []

def _get_key_hint(kmi):
    """
    Returns a string representing the keymap item in the form:
    "ctrl + alt + shift + key"
    """

    modifiers = {"ctrl": "Ctrl", "alt": "Alt", "shift": "Shift"}

    elements = []
    for m in modifiers.keys():
        if not getattr(kmi, m):
            continue
        elements.append(modifiers[m])

    elements.append(kmi.type)
    return " + ".join(elements)

def _get_matching_kmi(id_name, filter_func=None) -> List[KeyMapItem]:
    """
    Returns a list of keymap items that act on given operator.
    Optionally filtered by filter_func.
    """
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon

    km_items = []
    for km in kc.keymaps:
        for kmi in km.keymap_items:
            if not kmi.idname == id_name:
                continue
            if kmi.type in ("LEFTMOUSE", "MIDDLEMOUSE", "RIGHTMOUSE"):
                continue

            from .operators import numeric_events
            if kmi.type in numeric_events:
                continue

            if filter_func and not filter_func(kmi):
                continue
            km_items.append(kmi)
    return km_items

def get_key_map_desc(id_name) -> str:
    """
    Returns a list of shortcut hints to operator with given idname.
    Looks through keymaps in addon keyconfig.
    """

    km_items = _get_matching_kmi(id_name)
    km_items.extend(
        _get_matching_kmi(
            Operators.InvokeTool,
            filter_func=lambda kmi: kmi.properties["operator"] == id_name
            )
        )

    if not len(km_items):
        return ""

    hints = []
    for kmi in km_items:
        hint = _get_key_hint(kmi)
        if hint in hints:
            continue
        hints.append(hint)

    return "({})".format(", ".join(hints))


def register():
    wm = bpy.context.window_manager
    if wm.keyconfigs.addon:
        km = wm.keyconfigs.addon.keymaps.new(name='Object Mode', space_type='EMPTY')

        # Select
        kmi = km.keymap_items.new('wm.tool_set_by_id', 'ESC', 'PRESS', shift=True)
        kmi.properties.name = WorkSpaceTools.Select
        addon_keymaps.append((km, kmi))

        # Add Sketch
        kmi = km.keymap_items.new(Operators.AddSketch, 'A', 'PRESS', ctrl=True, shift=True)
        kmi.properties.wait_for_input = True
        addon_keymaps.append((km, kmi))

def unregister():
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if kc:
        for km, kmi in addon_keymaps:
            km.keymap_items.remove(kmi)
            addon_keymaps.clear()
