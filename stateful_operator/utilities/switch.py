"""Let a key that starts another tool interrupt a running tool.

A running modal operator sees every key before the keymaps do. When a key is
bound to starting another tool, the running operator ends and passes the event
on, so the keymap starts the new tool as if nothing had been running.
"""

from typing import Callable, Iterable, Iterator, Optional

import bpy
from bpy.types import Context, Event, KeyMap, KeyMapItem

from ..constants import Operators

# What a keymap item does with a key press in the current context.
PASS, SWITCH, BLOCK = range(3)

# Tool keymaps are looked up first, then these (as Blender does for the 3D view).
FALLBACK_KEYMAPS = ("Object Mode",)

_MODIFIERS = ("ctrl", "shift", "alt", "oskey", "hyper")

# idname -> predicate(context, kmi), or None to use the operator's poll.
_switch_operators: dict = {}


def register_switch_operator(
    idname: str, predicate: Optional[Callable[[Context, KeyMapItem], bool]] = None
) -> None:
    """Treat keymap items calling ``idname`` as starting another tool.

    ``predicate`` tells whether the item acts in the given context; otherwise the
    operator's poll decides. Items that don't act let the key through.
    """
    _switch_operators[getattr(idname, "value", idname)] = predicate


def clear_switch_operators() -> None:
    """Forget all operators registered with ``register_switch_operator``."""
    _switch_operators.clear()


def tool_available(context: Context, tool_name: str) -> bool:
    """Return True if the workspace tool can be activated in this context."""
    from bl_ui.space_toolsystem_common import item_from_id

    try:
        return bool(item_from_id(context, "VIEW_3D", tool_name))
    except Exception:
        return False


def _operator_polls(idname: str) -> bool:
    module, _, name = idname.partition(".")
    op = getattr(getattr(bpy.ops, module, None), name, None)
    if op is None:
        return False
    try:
        return op.poll()
    except RuntimeError:
        return False


def matches(kmi: KeyMapItem, event: Event) -> bool:
    """Return True if the key press ``event`` triggers ``kmi``."""
    if event.value != "PRESS" or kmi.value != "PRESS":
        return False
    if not kmi.active or kmi.type != event.type:
        return False
    if kmi.key_modifier != "NONE":
        return False
    if kmi.any:
        return True
    return all(
        bool(getattr(kmi, m, False)) == bool(getattr(event, m, False))
        for m in _MODIFIERS
    )


def classify(context: Context, kmi: KeyMapItem, exclude: str = "") -> int:
    """Return PASS, SWITCH or BLOCK for a keymap item matching a key press.

    ``exclude`` is the running operator: its own shortcut doesn't restart it.
    """
    idname = kmi.idname
    if idname == Operators.InvokeTool:
        props = kmi.properties
        if props.operator == exclude:
            return BLOCK
        if tool_available(context, props.tool_name):
            return SWITCH
        return PASS if props.fallthrough else BLOCK

    if idname not in _switch_operators:
        return BLOCK
    if idname == exclude:
        return BLOCK
    predicate = _switch_operators[idname]
    if predicate is None:
        active = _operator_polls(idname)
    else:
        active = predicate(context, kmi)
    return SWITCH if active else PASS


def _active_keymaps(context: Context) -> Iterator[KeyMap]:
    from bl_ui.space_toolsystem_common import keymap_from_id

    keymaps = context.window_manager.keyconfigs.user.keymaps
    tool = context.workspace.tools.from_space_view3d_mode(context.mode)
    if tool is not None:
        try:
            name = keymap_from_id(context, "VIEW_3D", tool.idname)
        except Exception:
            name = None
        km = keymaps.get(name) if name else None
        if km is not None:
            yield km
    for name in FALLBACK_KEYMAPS:
        km = keymaps.get(name)
        if km is not None:
            yield km


def first_verdict(
    items: Iterable[KeyMapItem], event: Event, verdict: Callable[[KeyMapItem], int]
) -> bool:
    """Walk items in Blender's order; the first one that doesn't pass decides."""
    for kmi in items:
        if not matches(kmi, event):
            continue
        result = verdict(kmi)
        if result != PASS:
            return result == SWITCH
    return False


def is_switch_event(context: Context, event: Event, exclude: str = "") -> bool:
    """Return True if the key press would start another tool.

    Only letter keys are considered: tool shortcuts use them, and it keeps mouse
    and navigation events away from the keymap walk.
    """
    if event.value != "PRESS" or len(event.type) != 1:
        return False
    items = (kmi for km in _active_keymaps(context) for kmi in km.keymap_items)
    return first_verdict(items, event, lambda kmi: classify(context, kmi, exclude))
