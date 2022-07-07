from ..constants import Operators, numeric_events, unit_key_types

from bpy.types import KeyMapItem, Context
from typing import List

def _get_key_hint(kmi: KeyMapItem) -> List[str]:
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

def _get_matching_kmi(context: Context, id_name: str, filter_func=None) -> List[KeyMapItem]:
    """
    Returns a list of keymap items that act on given operator.
    Optionally filtered by filter_func.
    """
    wm = context.window_manager
    kc = wm.keyconfigs.addon

    km_items = []
    for km in kc.keymaps:
        for kmi in km.keymap_items:
            if not kmi.idname == id_name:
                continue
            if kmi.type in ("LEFTMOUSE", "MIDDLEMOUSE", "RIGHTMOUSE"):
                continue

            if kmi.type in numeric_events:
                continue

            if filter_func and not filter_func(kmi):
                continue
            km_items.append(kmi)
    return km_items

def get_key_map_desc(context: Context, id_name: str) -> str:
    """
    Returns a list of shortcut hints to operator with given idname.
    Looks through keymaps in addon keyconfig.
    """

    km_items = _get_matching_kmi(context, id_name)
    km_items.extend(
        _get_matching_kmi(
            context,
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

def _tool_numeric_invoke_km(operator):
    km = []
    for event in numeric_events:
        km.append(
            (
                operator,
                {"type": event, "value": "PRESS"},
                None,
            )
        )
    return km

def operator_access(operator):
    return (
        *_tool_numeric_invoke_km(operator),
        (
            operator,
            {"type": "LEFTMOUSE", "value": "PRESS", "any": True},
            {"properties": [("wait_for_input", False)]},
        ),
    )

def tool_invoke_kmi(button, tool, operator):
    return (
        Operators.InvokeTool,
        {"type": button, "value": "PRESS"},
        {"properties": [("tool_name", tool), ("operator", operator)]},
    )

def is_numeric_input(event):
    return event.type in (*numeric_events, "BACK_SPACE")

def is_unit_input(event):
    return event.type in unit_key_types

def get_unit_value(event):
    type = event.type
    return type.lower()

def get_value_from_event(event):
    type = event.type
    if type in ("ZERO", "NUMPAD_0"):
        return "0"
    if type in ("ONE", "NUMPAD_1"):
        return "1"
    if type in ("TWO", "NUMPAD_2"):
        return "2"
    if type in ("THREE", "NUMPAD_3"):
        return "3"
    if type in ("FOUR", "NUMPAD_4"):
        return "4"
    if type in ("FIVE", "NUMPAD_5"):
        return "5"
    if type in ("SIX", "NUMPAD_6"):
        return "6"
    if type in ("SEVEN", "NUMPAD_7"):
        return "7"
    if type in ("EIGHT", "NUMPAD_8"):
        return "8"
    if type in ("NINE", "NUMPAD_9"):
        return "9"
    if type in ("PERIOD", "NUMPAD_PERIOD"):
        return "."