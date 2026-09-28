"""Start and stop the MCP endpoint, and copy its URL."""

import bpy
from bpy.types import Context, Operator
from bpy.utils import register_classes_factory

from ..declarations import Operators
from ..utilities.preferences import get_prefs
from . import server


class View3D_OT_slvs_mcp_start(Operator):
    """Serve the MCP endpoint so an AI agent can drive this Blender session"""

    bl_idname = Operators.McpStart
    bl_label = "Start MCP Server"

    @classmethod
    def poll(cls, context: Context) -> bool:
        return not server.is_running()

    def execute(self, context: Context):
        if bpy.app.background:
            # Tool calls are run from a timer, and a background Blender has no
            # loop to fire one, so the endpoint would accept and never answer.
            self.report(
                {"ERROR"}, "The MCP endpoint needs a Blender window, not --background."
            )
            return {"CANCELLED"}

        if not bpy.app.online_access:
            self.report(
                {"ERROR"},
                "Blender's online access is off. Enable it in "
                "Preferences > System > Network to serve the MCP endpoint.",
            )
            return {"CANCELLED"}

        port = get_prefs().mcp_port
        taken, reason = server.address_in_use(port)
        if taken:
            self.report({"ERROR"}, f"Port {port} is not available: {reason}")
            return {"CANCELLED"}

        try:
            running = server.start_server(port=port)
        except (OSError, RuntimeError) as e:
            self.report({"ERROR"}, f"Could not start the MCP endpoint: {e}")
            return {"CANCELLED"}

        self.report({"INFO"}, f"MCP endpoint listening on port {running.port}")
        return {"FINISHED"}


class View3D_OT_slvs_mcp_stop(Operator):
    """Stop serving the MCP endpoint"""

    bl_idname = Operators.McpStop
    bl_label = "Stop MCP Server"

    @classmethod
    def poll(cls, context: Context) -> bool:
        return server.is_running()

    def execute(self, context: Context):
        server.stop_server()
        self.report({"INFO"}, "MCP endpoint stopped")
        return {"FINISHED"}


class View3D_OT_slvs_mcp_copy_url(Operator):
    """Copy the endpoint URL, including its access token, to the clipboard"""

    bl_idname = Operators.McpCopyUrl
    bl_label = "Copy MCP URL"

    @classmethod
    def poll(cls, context: Context) -> bool:
        return server.is_running()

    def execute(self, context: Context):
        running = server.get_server()
        context.window_manager.clipboard = running.url
        self.report({"INFO"}, "Endpoint URL copied")
        return {"FINISHED"}


register, unregister = register_classes_factory(
    (
        View3D_OT_slvs_mcp_start,
        View3D_OT_slvs_mcp_stop,
        View3D_OT_slvs_mcp_copy_url,
    )
)
