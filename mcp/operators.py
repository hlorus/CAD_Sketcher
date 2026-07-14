"""Operators to start/stop the CAD Sketcher MCP TCP server."""

import bpy
from bpy.types import Operator

from ..declarations import Operators
from ..utilities.preferences import get_prefs
from . import server as mcp_server


class View3D_OT_slvs_mcp_start(Operator):
    bl_idname = Operators.McpStart
    bl_label = "Start CAD Sketcher MCP"
    bl_description = "Start the CAD Sketcher MCP TCP server (default port 9877)"

    def execute(self, context):
        prefs = get_prefs()
        host = getattr(prefs, "mcp_host", mcp_server.DEFAULT_HOST) or mcp_server.DEFAULT_HOST
        port = int(getattr(prefs, "mcp_port", mcp_server.DEFAULT_PORT))
        try:
            mcp_server.start_server(host=host, port=port)
        except Exception as e:
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}
        self.report({"INFO"}, f"CAD Sketcher MCP listening on {host}:{port}")
        return {"FINISHED"}


class View3D_OT_slvs_mcp_stop(Operator):
    bl_idname = Operators.McpStop
    bl_label = "Stop CAD Sketcher MCP"
    bl_description = "Stop the CAD Sketcher MCP TCP server"

    def execute(self, context):
        mcp_server.stop_server()
        self.report({"INFO"}, "CAD Sketcher MCP stopped")
        return {"FINISHED"}


classes = (
    View3D_OT_slvs_mcp_start,
    View3D_OT_slvs_mcp_stop,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
