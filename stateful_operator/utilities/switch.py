"""Let shortcuts reach the keymap while a tool is running.

A running modal operator sees every key before the keymaps do. A key bound to
starting another tool ends the running operator and passes the event on, so the
keymap starts the new tool as if nothing had been running. A key bound to a
setting toggle passes on while the running operator keeps going, and undo
cancels the running operator like Esc.
"""

from typing import Callable, Iterable, Iterator, Optional

import bpy
from bpy.types import Context, Event, KeyMap, KeyMapItem

from ..constants import Operators

# What a key press does to a running tool:
#   SKIP    the keymap item doesn't act here, the next one is tried
#   SWITCH  end the running tool and pass the key on
#   FORWARD pass the key on and keep running
#   BLOCK   the running tool keeps the key
#   CANCEL  undo: cancel the running tool, like Esc
SKIP, SWITCH, FORWARD, BLOCK, CANCEL = range(5)

# Where Blender binds undo, looked up so a remapped undo key works too.
UNDO_KEYMAP = "Screen"
UNDO_OPERATOR = "ed.undo"

# Tool keymaps are looked up first, then these (as Blender does for the 3D view).
FALLBACK_KEYMAPS = ("Object Mode",)

_MODIFIERS = ("ctrl", "shift", "alt", "oskey", "hyper")

Predicate = Callable[[Context, KeyMapItem], bool]

# idname -> (predicate or None to use the operator's poll, action when it acts)
_operators: dict = {}


def register_switch_operator(
    idname: str, predicate: Optional[Predicate] = None, keep_running: bool = False
) -> None:
    """Let keymap items calling ``idname`` act while a tool is running.

    By default the running tool ends first, as for starting another tool; with
    ``keep_running`` it continues (for toggles). ``predicate`` tells whether the
    item acts in the given context, otherwise the operator's poll decides.
    Items that don't act leave the key to the next item.
    """
    key = getattr(idname, "value", idname)
    _operators[key] = (predicate, FORWARD if keep_running else SWITCH)


def clear_switch_operators() -> None:
    """Forget all operators registered with ``register_switch_operator``."""
    _operators.clear()


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
    """Return what a keymap item matching a key press does to a running tool.

    ``exclude`` is the running operator: its own shortcut doesn't restart it.
    """
    idname = kmi.idname
    if idname == Operators.InvokeTool:
        props = kmi.properties
        if props.operator == exclude:
            return BLOCK
        if tool_available(context, props.tool_name):
            return SWITCH
        return SKIP if props.fallthrough else BLOCK

    if idname not in _operators or idname == exclude:
        return BLOCK
    predicate, action = _operators[idname]
    if predicate is None:
        active = _operator_polls(idname)
    else:
        active = predicate(context, kmi)
    return action if active else SKIP


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


def first_action(
    items: Iterable[KeyMapItem], event: Event, verdict: Callable[[KeyMapItem], int]
) -> int:
    """Walk items in Blender's order; the first one that acts decides."""
    for kmi in items:
        if not matches(kmi, event):
            continue
        result = verdict(kmi)
        if result != SKIP:
            return result
    return BLOCK


def is_undo_event(context: Context, event: Event) -> bool:
    """Return True if the key press is bound to undo."""
    km = context.window_manager.keyconfigs.user.keymaps.get(UNDO_KEYMAP)
    if km is None:
        return False
    return any(
        kmi.idname == UNDO_OPERATOR and matches(kmi, event) for kmi in km.keymap_items
    )


def key_action(context: Context, event: Event, exclude: str = "") -> int:
    """Return SWITCH, FORWARD, CANCEL or BLOCK for a key press during a running tool.

    Only letter keys are considered: the shortcuts use them, and it keeps mouse
    and navigation events away from the keymap walk.
    """
    if event.value != "PRESS" or len(event.type) != 1:
        return BLOCK
    if is_undo_event(context, event):
        return CANCEL
    items = (kmi for km in _active_keymaps(context) for kmi in km.keymap_items)
    return first_action(items, event, lambda kmi: classify(context, kmi, exclude))
