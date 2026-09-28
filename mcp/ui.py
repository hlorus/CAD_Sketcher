"""Sidebar panel for the MCP endpoint.

Deliberately thin. Settings belong in the add-on preferences, so what is left
here is what changes while you work: whether it is serving, and what the agent
has been doing. The one exception is the first run, where a short setup box in
reach beats sending the user off to find preferences.
"""

import bpy
from bpy.types import Context
from bpy.utils import register_classes_factory

from ..declarations import Operators, Panels
from ..ui.panels import VIEW3D_PT_sketcher_base
from ..utilities.preferences import get_prefs
from . import activity, server


def _draw_setup(layout, prefs) -> None:
    """First-run box: start serving and hand the address to a client."""
    box = layout.box()
    box.label(text="Connect an agent", icon="PLAY")

    running = server.get_server()
    if running is None or not running.running:
        box.operator(Operators.McpStart, text="Start Server", icon="PLAY")
        column = box.column(align=True)
        column.scale_y = 0.8
        column.label(text="Lets an AI agent read and")
        column.label(text="edit your sketches.")
        return

    box.prop(prefs, "mcp_client", text="")
    box.operator(
        Operators.McpCopyUrl, text="Copy Address", icon="COPYDOWN"
    ).client_format = prefs.mcp_client
    column = box.column(align=True)
    column.scale_y = 0.8
    column.label(text=_hint(prefs.mcp_client))
    column.label(text="Disappears once connected.")


def _hint(client_format: str) -> str:
    """Where the copied text is meant to go."""
    return {
        "URL": "Paste where the client asks",
        "CLAUDE_CODE": "Paste in a terminal",
        "JSON": "Paste into the client's config",
        "VSCODE": "Paste into mcp.json",
    }.get(client_format, "Paste where the client asks")


def _draw_activity(layout) -> None:
    """The agent's recent calls, so its work is visible without leaving Blender."""
    entries = activity.entries()
    if not entries and not activity.busy():
        return

    box = layout.box()
    header = box.row(align=True)
    header.label(text="Activity")
    if activity.busy():
        header.label(text="working", icon="SORTTIME")
    else:
        header.operator(Operators.McpClearActivity, text="", icon="TRASH", emboss=False)

    column = box.column(align=True)
    column.scale_y = 0.8
    # Newest first: what just happened is what the user is looking for.
    for entry in reversed(entries):
        row = column.row(align=True)
        row.label(text="", icon="CHECKMARK" if entry.ok else "ERROR")
        row.label(text=f"{entry.clock}  {entry.tool}")
        if entry.detail:
            detail = column.row(align=True)
            detail.active = False
            detail.label(text=f"        {entry.detail}")


class VIEW3D_PT_sketcher_mcp(VIEW3D_PT_sketcher_base):
    """Serve an MCP endpoint for an AI agent"""

    bl_label = "AI Agent (MCP)"
    bl_idname = Panels.SketcherMcp
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context: Context) -> None:
        layout = self.layout
        prefs = get_prefs()

        if not bpy.app.online_access:
            column = layout.column()
            column.label(text="Online access is off", icon="ERROR")
            column.label(text="Enable it in Preferences > System")
            return

        running = server.get_server()
        serving = running is not None and running.running
        # Settings live in the add-on preferences; only the first run, when
        # nothing has ever connected, is worth the space here.
        setting_up = not server.client_ever_connected()

        row = layout.row(align=True)
        if serving:
            row.label(text=f"Serving on port {running.port}", icon="CHECKMARK")
            row.operator(Operators.McpStop, text="", icon="PAUSE")
        elif not setting_up:
            # While setting up, the box below owns the start button.
            row.operator(Operators.McpStart, text="Start Server", icon="PLAY")
        else:
            row.label(text="Not running")
        # The settings themselves live in preferences; this is the way there.
        row.operator(Operators.McpPreferences, text="", icon="PREFERENCES")

        if setting_up:
            _draw_setup(layout, prefs)

        _draw_activity(layout)


register, unregister = register_classes_factory((VIEW3D_PT_sketcher_mcp,))
