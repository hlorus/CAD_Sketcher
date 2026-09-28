"""Sidebar panel for the MCP endpoint."""

import bpy
from bpy.types import Context
from bpy.utils import register_classes_factory

from ..declarations import Operators, Panels
from ..ui.panels import VIEW3D_PT_sketcher_base
from ..utilities.preferences import get_prefs
from . import activity, server


def _hint(client_format: str) -> str:
    """Where the copied text is meant to go."""
    return {
        "URL": "Paste where the client asks",
        "CLAUDE_CODE": "Paste in a terminal",
        "JSON": "Paste into the client's config",
        "VSCODE": "Paste into mcp.json",
    }.get(client_format, "Paste where the client asks")


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
        if running is None or not running.running:
            layout.operator(Operators.McpStart, text="Start Server", icon="PLAY")
            layout.label(text="Not running", icon="RADIOBUT_OFF")
            column = layout.column(align=True)
            column.prop(prefs, "mcp_port")
            column.prop(prefs, "mcp_auto_start", text="Start on launch")
            return

        layout.operator(Operators.McpStop, text="Stop Server", icon="PAUSE")
        layout.label(text=f"Listening on port {running.port}", icon="CHECKMARK")

        box = layout.box()
        box.label(text="Connect an agent")
        box.prop(prefs, "mcp_client", text="")
        box.operator(
            Operators.McpCopyUrl, text="Copy Address", icon="COPYDOWN"
        ).client_format = prefs.mcp_client
        column = box.column(align=True)
        column.scale_y = 0.8
        column.label(text=_hint(prefs.mcp_client))
        column.label(text="Once only; the address keeps.")

        _draw_activity(layout)

        column = layout.column(align=True)
        column.scale_y = 0.8
        column.label(text="Anyone with the URL can edit", icon="INFO")
        layout.operator(
            Operators.McpNewToken, text="New Access Token", icon="FILE_REFRESH"
        )


def _draw_activity(layout) -> None:
    """The agent's recent calls, so its work is visible without leaving Blender."""
    entries = activity.entries()
    box = layout.box()

    header = box.row(align=True)
    header.label(text="Activity")
    if activity.busy():
        header.label(text="working", icon="SORTTIME")
    elif entries:
        header.operator(Operators.McpClearActivity, text="", icon="TRASH", emboss=False)

    if not entries:
        column = box.column()
        column.scale_y = 0.8
        column.label(text="Nothing yet")
        return

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


register, unregister = register_classes_factory((VIEW3D_PT_sketcher_mcp,))
