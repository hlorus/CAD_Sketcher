"""A short log of what the agent has been doing, for the sidebar to show.

An agent works in another window, so without this the only evidence of it is
geometry appearing. Seeing the last few calls is what makes it legible: what it
touched, whether anything was refused, and whether it is still going.

Written and read on the main thread only (every tool call is marshalled there
anyway), so nothing here needs a lock. The in-flight count is the exception and
is only ever a display hint.
"""

import time
from collections import deque
from typing import Any, Deque, List, NamedTuple, Optional

# Enough to see what just happened without turning the sidebar into a log file.
LIMIT = 8


class Entry(NamedTuple):
    """One finished tool call."""

    clock: str
    tool: str
    detail: str
    ok: bool


_entries: Deque[Entry] = deque(maxlen=LIMIT)
_in_flight = 0


def record(tool: str, ok: bool, detail: str = "") -> None:
    """Note a finished call. Main thread only."""
    _entries.append(
        Entry(clock=time.strftime("%H:%M:%S"), tool=tool, detail=detail, ok=ok)
    )


def entries() -> List[Entry]:
    """The recent calls, newest last."""
    return list(_entries)


def clear() -> None:
    """Forget the log."""
    _entries.clear()


def begin() -> None:
    """A call has started."""
    global _in_flight
    _in_flight += 1


def end() -> None:
    """A call has finished."""
    global _in_flight
    _in_flight = max(0, _in_flight - 1)


def busy() -> bool:
    """Whether a call is being served right now."""
    return _in_flight > 0


def summarise(tool: str, value: Any) -> str:
    """One short line saying what a call did, for the sidebar.

    Reads the few keys that carry the news rather than switching on every tool,
    so a new tool still gets a sensible line without touching this.
    """
    if isinstance(value, tuple):
        return "rendered"
    if not isinstance(value, dict):
        return ""

    applied = value.get("applied")
    if isinstance(applied, dict):
        parts = []
        if applied.get("entities_added"):
            parts.append(f"+{applied['entities_added']} entities")
        if applied.get("constraints_added"):
            parts.append(f"+{applied['constraints_added']} constraints")
        changed = ", ".join(parts) if parts else "no additions"
        return f"{value.get('sketch', '')} {changed}".strip()

    if "deleted" in value:
        return f"deleted {value['deleted']}"

    if "sketches" in value:
        return f"{len(value['sketches'])} sketch(es) in the scene"

    if "sketch" in value:
        dof = value.get("dof")
        if dof == 0 and value.get("fully_defined"):
            return f"{value['sketch']}, fully defined"
        if dof is not None:
            return f"{value['sketch']}, dof {dof}"
        return str(value["sketch"])

    return ""


def note_result(tool: str, value: Any, error: Optional[Exception]) -> None:
    """Record the outcome of one call. Main thread only."""
    if error is not None:
        record(tool, ok=False, detail=str(error).split("\n")[0][:80])
        return
    record(tool, ok=True, detail=summarise(tool, value))
