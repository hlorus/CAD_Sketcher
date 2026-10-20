"""Run a tool call and shape the MCP result.

The endpoint is pumped from a timer on Blender's main thread, so a call arrives
already on the only thread allowed to touch ``bpy`` and runs there and then. The
pump serves one request per tick, which is also what keeps two agents from
interleaving writes into the same curve data.

Groundwork for this is from Nikita Coder's draft in PR #562.
"""

import base64
import json
import logging
from typing import Any, Dict, Optional

import bpy

from . import activity

logger = logging.getLogger(__name__)


def call_tool(name: Optional[str], arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Run a tool by name and return an MCP ``tools/call`` result."""
    from . import tools

    tool = tools.BY_NAME.get(name)
    if tool is None:
        known = ", ".join(sorted(tools.BY_NAME))
        return _text_error(f"Unknown tool {name!r}. Available: {known}.")

    activity.begin()
    try:
        return _run(name, tool["handler"], arguments)
    finally:
        activity.end()


def _run(name: str, handler, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Run one handler, noting for the sidebar what it did."""
    result = None
    error = None
    try:
        result = handler(bpy.context, arguments)
    except Exception as e:  # noqa: BLE001 - reported to the agent, not raised
        error = e

    activity.note_result(name, result, error)
    _tag_redraw()

    if error is not None:
        return _tool_error(error)
    return _result(result)


def _tag_redraw() -> None:
    """Redraw the sidebar, so a read-only call still shows up in the log.

    An edit redraws anyway through the scene change; a call that only reads
    would otherwise leave the panel stale until the user moved the mouse.
    """
    for window in getattr(bpy.context.window_manager, "windows", ()):
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()


def _result(value: Any) -> Dict[str, Any]:
    """Wrap a handler's return value as MCP content."""
    if isinstance(value, tuple) and len(value) == 2 and isinstance(value[0], bytes):
        payload, mime = value
        return {
            "content": [
                {
                    "type": "image",
                    "data": base64.b64encode(payload).decode("ascii"),
                    "mimeType": mime,
                }
            ]
        }

    text = json.dumps(value, indent=1, sort_keys=False)
    return {
        "content": [{"type": "text", "text": text}],
        "structuredContent": value if isinstance(value, dict) else {"result": value},
    }


def _tool_error(error: Exception) -> Dict[str, Any]:
    """Report a failed tool call, with the detail the agent needs to retry."""
    from .handlers import ToolError

    if isinstance(error, ToolError):
        return _text_error(str(error))

    # Not something the agent did: log it where a bug report can find it, and
    # tell the agent only that it broke.
    logger.exception("MCP tool raised", exc_info=error)
    return _text_error(f"CAD Sketcher failed: {type(error).__name__}: {error}")


def _text_error(message: str) -> Dict[str, Any]:
    return {"content": [{"type": "text", "text": message}], "isError": True}
