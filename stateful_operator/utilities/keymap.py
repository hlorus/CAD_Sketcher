from ..constants import Operators, numeric_events, unit_key_types

from bpy.types import KeyMapItem, Context, Event

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


def _get_matching_kmi(
    context: Context, id_name: str, filter_func=None
) -> List[KeyMapItem]:
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
            filter_func=lambda kmi: kmi.properties["operator"] == id_name,
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


def _tool_numeric_invoke_km(operator: str):
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


def operator_access(operator: str):
    return (
        *_tool_numeric_invoke_km(operator),
        (
            operator,
            {"type": "LEFTMOUSE", "value": "PRESS", "any": True},
            {"properties": [("wait_for_input", False)]},
        ),
    )


def tool_invoke_kmi(button: str, tool: str, operator: str):
    return (
        Operators.InvokeTool,
        {"type": button, "value": "PRESS"},
        {"properties": [("tool_name", tool), ("operator", operator)]},
    )


def is_numeric_input(event: Event):
    return event.type in (*numeric_events, "BACK_SPACE")


def is_unit_input(event: Event):
    return event.type in unit_key_types


def get_unit_value(event: Event):
    type = event.type
    return type.lower()


_EVENT_TO_DIGIT = {
    "ZERO": "0", "NUMPAD_0": "0",
    "ONE": "1", "NUMPAD_1": "1",
    "TWO": "2", "NUMPAD_2": "2",
    "THREE": "3", "NUMPAD_3": "3",
    "FOUR": "4", "NUMPAD_4": "4",
    "FIVE": "5", "NUMPAD_5": "5",
    "SIX": "6", "NUMPAD_6": "6",
    "SEVEN": "7", "NUMPAD_7": "7",
    "EIGHT": "8", "NUMPAD_8": "8",
    "NINE": "9", "NUMPAD_9": "9",
    "PERIOD": ".", "NUMPAD_PERIOD": ".",
}


def get_value_from_event(event: Event):
    return _EVENT_TO_DIGIT.get(event.type, "")
