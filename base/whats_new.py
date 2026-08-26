"""In-app "What's new" dialog, shown once after the add-on is updated.

Everything is derived automatically so a release needs no extra bookkeeping:

- the version comes from the manifest (``get_addon_version``);
- the notes come from the bundled ``CHANGELOG.md`` — the same file that feeds the
  GitHub release — parsed by the shared :mod:`changelog` module;
- the last-shown version is stored in the extension's per-user directory (which
  survives updates), so nothing is written to the user's preferences.

Only the ``show_whats_new`` preference toggle is user-facing: when off, the dialog
is skipped but the marker still advances, so it never shows retroactively.
"""

import logging
import textwrap
from pathlib import Path

import bpy
from bpy.types import Operator

logger = logging.getLogger(__name__)

RELEASES_URL = "https://github.com/hlorus/CAD_Sketcher/releases"
_DIALOG_WIDTH = 600
# Blender labels don't wrap; this many characters fit per ~width unit. Tuned to
# fill most of the dialog with a small margin against proportional-font variance.
_CHARS_PER_WIDTH = 0.16
_FIRST_INTERVAL = 1.0


def _max_chars(width: int) -> int:
    return max(24, int(width * _CHARS_PER_WIDTH))


def _wrap_lines(notes: str, max_chars: int):
    """Reflow changelog text into display lines that fit ``max_chars``.

    Consecutive prose lines join into a paragraph and reflow together; bullets
    wrap individually with a hanging indent; blank lines are kept as breaks.
    Pure (no bpy) so it can be unit-tested.
    """
    out = []
    paragraph = []

    def flush():
        if paragraph:
            out.extend(textwrap.wrap(" ".join(paragraph), max_chars))
            paragraph.clear()

    for raw in notes.splitlines():
        line = raw.strip()
        if not line:
            flush()
            out.append("")  # paragraph break
        elif line.startswith(("- ", "* ")):
            flush()
            out.extend(textwrap.wrap(line, max_chars, subsequent_indent="  "))
        else:
            paragraph.append(line)
    flush()
    return out


def _addon_package() -> str:
    from ..utilities.register import get_name

    return get_name()


def _current_version() -> str:
    from .. import get_addon_version

    return get_addon_version()


def _notes_for(version: str) -> str:
    from .. import changelog

    changelog_path = Path(__file__).parent.parent / "CHANGELOG.md"
    try:
        text = changelog_path.read_text(encoding="utf-8")
    except OSError:
        return ""
    return changelog.extract_section(version, text)


def _seen_file() -> Path:
    # create=True makes the *directory*; the marker is a file inside it.
    directory = Path(
        bpy.utils.extension_path_user(_addon_package(), path="", create=True)
    )
    return directory / "whats_new_seen.txt"


def _read_seen() -> str:
    try:
        return _seen_file().read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _write_seen(version: str) -> None:
    try:
        _seen_file().write_text(version, encoding="utf-8")
    except OSError as e:
        logger.warning("Could not persist what's-new marker: %s", e)


def _prefs():
    addon = bpy.context.preferences.addons.get(_addon_package())
    return addon.preferences if addon else None


class VIEW3D_OT_slvs_whats_new(Operator):
    """Show what changed in the latest CAD Sketcher update"""

    bl_idname = "view3d.slvs_whats_new"
    bl_label = "CAD Sketcher — What's New"
    bl_options = {"INTERNAL"}

    def invoke(self, context, event):
        self._version = _current_version()
        self._notes = _notes_for(self._version)
        # invoke_popup (not invoke_props_dialog) renders the content without an
        # OK/Cancel footer; it dismisses on click-away.
        return context.window_manager.invoke_popup(self, width=_DIALOG_WIDTH)

    def draw(self, context):
        layout = self.layout
        layout.label(text=f"Updated to version {self._version}", icon="INFO")

        col = layout.column(align=True)
        if self._notes:
            for line in _wrap_lines(self._notes, _max_chars(_DIALOG_WIDTH)):
                if line:
                    col.label(text=line)
                else:
                    col.separator()
        else:
            col.label(text="See the full changelog for details.")

        layout.separator()
        row = layout.row()
        row.operator("wm.url_open", text="Full changelog", icon="URL").url = RELEASES_URL
        prefs = _prefs()
        if prefs is not None:
            row.prop(prefs, "show_whats_new", text="Show on update")

    def execute(self, context):
        return {"FINISHED"}


def _process_update(show_enabled: bool = True):
    """Advance the seen-marker and decide whether to announce.

    Pure of the background check and the popup call so it is unit-testable.
    Returns the version to announce, or ``None`` when nothing should be shown.
    The marker advances on every version change regardless of *show_enabled*, so
    a disabled toggle never causes a stale popup later.
    """
    current = _current_version()
    seen = _read_seen()

    if not seen:
        _write_seen(current)  # first run on this machine: record silently
        return None
    if seen == current:
        return None  # up to date

    # Only announce a version once it actually has changelog notes. On the rolling
    # 'latest' channel the base version is the in-development next release, whose
    # entry is usually not written yet — leave the marker untouched so the
    # announcement still fires once the notes land in a later build.
    if not _notes_for(current):
        return None

    _write_seen(current)
    return current if show_enabled else None


def _maybe_show():
    """App-timer callback: show the dialog once when the version has changed."""
    if bpy.app.background:
        return None

    prefs = _prefs()
    show_enabled = prefs is None or prefs.show_whats_new
    if _process_update(show_enabled) is not None:
        try:
            bpy.ops.view3d.slvs_whats_new("INVOKE_DEFAULT")
        except Exception as e:
            logger.warning("Could not show what's-new dialog: %s", e)
    return None


def register():
    bpy.utils.register_class(VIEW3D_OT_slvs_whats_new)
    if not bpy.app.background:
        bpy.app.timers.register(_maybe_show, first_interval=_FIRST_INTERVAL)


def unregister():
    if bpy.app.timers.is_registered(_maybe_show):
        bpy.app.timers.unregister(_maybe_show)
    bpy.utils.unregister_class(VIEW3D_OT_slvs_whats_new)
