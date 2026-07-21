import logging
from enum import Enum, auto

import bpy
from bpy.utils import register_tool, unregister_tool

logger = logging.getLogger(__name__)


class ToolGroup(Enum):
    ALWAYS = auto()
    SKETCH = auto()
    NON_SKETCH = auto()


_registry = []  # list of (tool_cls, kwargs, group)
_sketch_active = False
_registered = set()  # tool class bl_idname strings currently registered


def add(tool_cls, visibility=ToolGroup.SKETCH, **kwargs):
    _registry.append((tool_cls, kwargs, visibility))


def _register_tools(groups):
    for tool_cls, kwargs, group in _registry:
        if group not in groups:
            continue
        if tool_cls.bl_idname in _registered:
            continue
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


def enter_sketch_mode():
    global _sketch_active
    if _sketch_active:
        return
    _sketch_active = True
    _unregister_tools({ToolGroup.NON_SKETCH})
    _register_tools({ToolGroup.SKETCH})


def leave_sketch_mode():
    global _sketch_active
    if not _sketch_active:
        return
    _sketch_active = False
    _unregister_tools({ToolGroup.SKETCH})
    _register_tools({ToolGroup.NON_SKETCH})


def register():
    if bpy.app.background:
        return
    _register_tools({ToolGroup.ALWAYS, ToolGroup.NON_SKETCH})


def unregister():
    if bpy.app.background:
        return
    _unregister_tools({ToolGroup.ALWAYS, ToolGroup.SKETCH, ToolGroup.NON_SKETCH})
    _registry.clear()
    _registered.clear()
    global _sketch_active
    _sketch_active = False
