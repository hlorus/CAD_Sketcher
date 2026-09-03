import logging
from enum import Enum, auto

import bpy
from bpy.utils import register_tool, unregister_tool

logger = logging.getLogger(__name__)


class ToolGroup(Enum):
    ALWAYS = auto()
    SKETCH_2D = auto()
    SKETCH_3D = auto()
    NON_SKETCH = auto()

    # Backward-compatible alias for callers that still mean the classic 2D
    # sketch tool set.
    SKETCH = SKETCH_2D


_registry = []  # list of (tool_cls, kwargs, group)
_sketch_active = False
_sketch_group = None
_registered = set()  # tool class bl_idname strings currently registered


def add(tool_cls, visibility=ToolGroup.SKETCH_2D, **kwargs):
    _registry.append((tool_cls, kwargs, visibility))


def _select_keymap_for_group(group):
    """Return the Select-tool keymap matching the active sketch family.

    The Select workspace tool is intentionally shared by 2D and 3D sketch
    groups. Its class-level ``bl_keymap`` therefore has to be rebound immediately
    before registration; otherwise the 3D group inherits the 2D P/L InvokeTool
    entries and a hotkey can invoke AddLine2D/AddPoint2D without activating the
    matching 3D workspace tool.
    """
    from ..keymaps import tool_access, tool_base_keymap, tool_select
    from .keymaps_3d import tool_access_3d

    common = tool_select[len(tool_base_keymap) + len(tool_access) :]
    access = tool_access_3d if group == ToolGroup.SKETCH_3D else tool_access
    return (*tool_base_keymap, *access, *common)


def _prepare_tool_class(tool_cls, group):
    """Apply group-specific class data before Blender registers a tool."""
    from ..declarations import WorkSpaceTools

    if tool_cls.bl_idname == WorkSpaceTools.Select:
        tool_cls.bl_keymap = _select_keymap_for_group(group)


def _register_tools(groups):
    for tool_cls, kwargs, group in _registry:
        if group not in groups:
            continue
        if tool_cls.bl_idname in _registered:
            continue
        _prepare_tool_class(tool_cls, group)
        register_tool(tool_cls, **kwargs)
        _registered.add(tool_cls.bl_idname)


def _unregister_tools(groups):
    for tool_cls, kwargs, group in reversed(_registry):
        if group not in groups:
            continue
        if tool_cls.bl_idname not in _registered:
            continue
        unregister_tool(tool_cls)
        _registered.discard(tool_cls.bl_idname)


def enter_sketch_mode(is_3d=False):
    global _sketch_active, _sketch_group

    desired = ToolGroup.SKETCH_3D if is_3d else ToolGroup.SKETCH_2D
    if _sketch_active and _sketch_group == desired:
        return

    if _sketch_active and _sketch_group is not None:
        _unregister_tools({_sketch_group})
    else:
        _unregister_tools({ToolGroup.NON_SKETCH})

    _sketch_active = True
    _sketch_group = desired
    _register_tools({desired})


def leave_sketch_mode():
    global _sketch_active, _sketch_group
    if not _sketch_active:
        return

    if _sketch_group is not None:
        _unregister_tools({_sketch_group})

    _sketch_active = False
    _sketch_group = None
    _register_tools({ToolGroup.NON_SKETCH})


def is_sketch_mode():
    """True while either sketch sub-tool set is registered."""
    return _sketch_active


def sync_sketch_mode(is_active_sketch: bool, is_3d=False):
    """Reconcile registered tools with the undo-tracked active sketch.

    2D and native-3D sketches have different draw tool sets. Undo/redo does not
    restore Python registration state, so re-enter the matching set whenever an
    active sketch survives the operation.
    """
    if is_active_sketch:
        enter_sketch_mode(is_3d=is_3d)
    else:
        leave_sketch_mode()


def register():
    if bpy.app.background:
        return
    _register_tools({ToolGroup.ALWAYS, ToolGroup.NON_SKETCH})


def unregister():
    if bpy.app.background:
        return

    _unregister_tools(
        {
            ToolGroup.ALWAYS,
            ToolGroup.SKETCH_2D,
            ToolGroup.SKETCH_3D,
            ToolGroup.NON_SKETCH,
        }
    )

    # Keep _registry: it is populated at import time (via add() calls in
    # __init__), which does not run again on a same-session disable/enable.
    _registered.clear()

    global _sketch_active, _sketch_group
    _sketch_active = False
    _sketch_group = None