"""Sidebar panel for the MCP endpoint."""

import bpy
from bpy.types import Context
from bpy.utils import register_classes_factory

from ..declarations import Operators, Panels
from ..ui.panels import VIEW3D_PT_sketcher_base
from ..utilities.preferences import get_prefs
from . import server


class VIEW3D_PT_sketcher_mcp(VIEW3D_PT_sketcher_base):
    """Serve an MCP endpoint for an AI agent"""

    bl_label = "AI Agent (MCP)"
    bl_idname = Panels.SketcherMcp
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context: Context) -> None:
        layout = self.layout
        prefs = get_prefs()
        running = server.get_server()

        if not bpy.app.online_access:
            column = layout.column()
            column.label(text="Online access is off", icon="ERROR")
            column.label(text="Enable it in Preferences > System")
            return

        if running is not None and running.running:
            layout.operator(Operators.McpStop, text="Stop Server", icon="PAUSE")
            layout.label(text=f"Listening on port {running.port}", icon="CHECKMARK")

            box = layout.box()
            box.label(text="Connect an agent")
            box.operator(Operators.McpCopyUrl, text="Copy URL", icon="COPYDOWN")
            column = box.column(align=True)
            column.scale_y = 0.8
            column.label(text="Then, in a terminal:")
            column.label(text="claude mcp add --transport http")
            column.label(text="  cad-sketcher <paste URL>")
            layout.label(text="Anyone with the URL can edit", icon="INFO")
            return

        layout.prop(prefs, "mcp_port")
        layout.operator(Operators.McpStart, text="Start Server", icon="PLAY")
        layout.label(text="Not running", icon="RADIOBUT_OFF")


register, unregister = register_classes_factory((VIEW3D_PT_sketcher_mcp,))
