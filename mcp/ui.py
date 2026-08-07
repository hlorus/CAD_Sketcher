"""UI panel for CAD Sketcher MCP server control."""

import bpy
from bpy.types import Panel

from .. import declarations
from ..declarations import Operators
from ..ui.panels import VIEW3D_PT_sketcher_base
from ..utilities.preferences import get_prefs
from . import server as mcp_server


class VIEW3D_PT_sketcher_mcp(VIEW3D_PT_sketcher_base):
    bl_label = "MCP"
    bl_idname = declarations.Panels.SketcherMcp
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        prefs = get_prefs()
        running = mcp_server.is_running()
        srv = mcp_server.get_server()

        col = layout.column(align=True)
        col.prop(prefs, "mcp_host")
        col.prop(prefs, "mcp_port")
        col.prop(prefs, "mcp_auto_start")

        row = layout.row(align=True)
        if running:
            row.operator(Operators.McpStop, text="Stop Server", icon="PAUSE")
            port = srv.port if srv else prefs.mcp_port
            layout.label(text=f"Listening on port {port}", icon="CHECKMARK")
        else:
            row.operator(Operators.McpStart, text="Start Server", icon="PLAY")
            layout.label(text="Server stopped", icon="RADIOBUT_OFF")

        box = layout.box()
        box.label(text="Cursor / Claude MCP")
        box.label(text="Use uvx package cad-sketcher-mcp")
        box.label(text="Port must match BLENDER_PORT (9877)")


classes = (VIEW3D_PT_sketcher_mcp,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
