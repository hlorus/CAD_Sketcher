"""Opt-in tracing for the snapping and live-projection path.

Enabled by Preferences > Advanced > Trace Snapping. A snapping bug shows up only
while the mouse moves, which no test can watch and no screenshot can capture, so
the trace puts one line per move in the add-on's log: the snap target, what the
placed point linked to, and every projected point the depsgraph moves.

Lines are emitted at INFO on this module's own logger, which is set to INFO
regardless of the preference's logging level, so turning the toggle on is enough
to see them (console, and the log file named at startup).
"""

import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def tracing() -> bool:
    """Whether snap tracing is switched on in the preferences."""
    try:
        from .preferences import get_prefs

        return bool(get_prefs().trace_snapping)
    except Exception:
        # Preferences are unavailable during registration and in --background.
        return False


def trace(message: str, *args) -> None:
    """Log one trace line, formatted lazily, when tracing is on."""
    if tracing():
        logger.info("TRACE " + message, *args)


def fmt_vec(vec, digits: int = 4) -> str:
    """A short, stable rendering of a vector (or None) for a trace line."""
    if vec is None:
        return "-"
    return "(" + ", ".join(f"{float(c):.{digits}f}" for c in vec) + ")"


def short_id(curve_id) -> str:
    """The first chars of a curve id, enough to follow it across lines."""
    if not curve_id:
        return "-"
    return str(curve_id)[:8]
