"""Run a tool call on Blender's main thread and shape the MCP result.

Requests arrive on HTTP worker threads, and ``bpy`` may only be touched from the
main thread, so a call is posted as a timer and the worker waits for it. One call
runs at a time: two agents editing a sketch at once would interleave writes into
the same curve data.

Groundwork for the hop is from Nikita Coder's draft in PR #562.
"""

import base64
import json
import logging
import threading
from typing import Any, Dict, Optional

import bpy

logger = logging.getLogger(__name__)

# How long a worker waits for the main thread. Every tool here is a bounded piece
# of work, so a wait this long means Blender is blocked on something else (a modal
# operator, a long solve) and saying so beats hanging the client.
MAIN_THREAD_TIMEOUT = 60.0

# How long a worker waits for its turn when another call holds the lock.
QUEUE_TIMEOUT = 30.0

_lock = threading.Lock()


def call_tool(name: Optional[str], arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Run a tool by name and return an MCP ``tools/call`` result."""
    from . import tools

    tool = tools.BY_NAME.get(name)
    if tool is None:
        known = ", ".join(sorted(tools.BY_NAME))
        return _text_error(f"Unknown tool {name!r}. Available: {known}.")

    if not _lock.acquire(timeout=QUEUE_TIMEOUT):
        return _text_error(
            "Another MCP call is still running in Blender. Retry in a moment."
        )
    try:
        return _run_on_main_thread(tool["handler"], arguments)
    finally:
        _lock.release()


def _run_on_main_thread(handler, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Post ``handler`` to the main thread and wait for what it returns."""
    done = threading.Event()
    outcome: Dict[str, Any] = {}

    def run():
        try:
            outcome["result"] = handler(bpy.context, arguments)
        except Exception as e:  # noqa: BLE001 - reported to the agent, not raised
            outcome["error"] = e
        finally:
            done.set()
        return None  # unregister the timer

    bpy.app.timers.register(run, first_interval=0.0)

    if not done.wait(timeout=MAIN_THREAD_TIMEOUT):
        return _text_error(
            "Blender did not run the call within "
            f"{MAIN_THREAD_TIMEOUT:.0f}s. It is probably busy with something "
            "the user started; ask them to finish it."
        )

    if "error" in outcome:
        return _tool_error(outcome["error"])
    return _result(outcome.get("result"))


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
