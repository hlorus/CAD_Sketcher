"""Start and stop the MCP endpoint, and hand its URL to a client."""

import bpy
from bpy.types import Context, Operator
from bpy.utils import register_classes_factory

from ..declarations import Operators
from ..utilities.preferences import get_prefs
from . import clients, server


def start(operator: Operator, context: Context) -> bool:
    """Start the endpoint, reporting why through ``operator`` if it cannot."""
    if bpy.app.background:
        # Tool calls are run from a timer, and a background Blender has no loop
        # to fire one, so the endpoint would accept and never answer.
        operator.report(
            {"ERROR"}, "The MCP endpoint needs a Blender window, not --background."
        )
        return False

    if not bpy.app.online_access:
        operator.report(
            {"ERROR"},
            "Blender's online access is off. Enable it in "
            "Preferences > System > Network to serve the MCP endpoint.",
        )
        return False

    port = get_prefs().mcp_port
    taken, reason = server.address_in_use(port)
    if taken:
        operator.report({"ERROR"}, f"Port {port} is not available: {reason}")
        return False

    try:
        running = server.start_server(port=port)
    except (OSError, RuntimeError) as e:
        operator.report({"ERROR"}, f"Could not start the MCP endpoint: {e}")
        return False

    operator.report({"INFO"}, f"MCP endpoint listening on port {running.port}")
    return True


class View3D_OT_slvs_mcp_start(Operator):
    """Serve the MCP endpoint so an AI agent can drive this Blender session"""

    bl_idname = Operators.McpStart
    bl_label = "Start MCP Server"

    @classmethod
    def poll(cls, context: Context) -> bool:
        return not server.is_running()

    def execute(self, context: Context):
        return {"FINISHED"} if start(self, context) else {"CANCELLED"}


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
    """Copy this endpoint's address, in the form your MCP client wants"""

    bl_idname = Operators.McpCopyUrl
    bl_label = "Copy Address"

    client_format: bpy.props.EnumProperty(
        name="For",
        description="Which client to shape the address for",
        items=clients.FORMAT_ITEMS,
        default="URL",
        options={"SKIP_SAVE"},
    )

    @classmethod
    def poll(cls, context: Context) -> bool:
        return server.is_running()

    def execute(self, context: Context):
        running = server.get_server()
        context.window_manager.clipboard = running.connect_snippet(self.client_format)
        self.report({"INFO"}, "Copied to the clipboard")
        return {"FINISHED"}


class View3D_OT_slvs_mcp_new_token(Operator):
    """Replace the access token, so any URL handed out before stops working"""

    bl_idname = Operators.McpNewToken
    bl_label = "New Access Token"
    bl_options = {"REGISTER"}

    def execute(self, context: Context):
        token = server.new_token()
        # A running endpoint keeps serving the old token until it is rebound.
        if server.is_running():
            port = server.get_server().port
            server.stop_server()
            server.start_server(port=port, token=token)
        self.report({"INFO"}, "New token; reconnect your agent with the new URL")
        return {"FINISHED"}


class View3D_OT_slvs_mcp_clear_activity(Operator):
    """Clear the list of recent agent activity"""

    bl_idname = Operators.McpClearActivity
    bl_label = "Clear Activity"

    def execute(self, context: Context):
        from . import activity

        activity.clear()
        if context.area:
            context.area.tag_redraw()
        return {"FINISHED"}


register, unregister = register_classes_factory(
    (
        View3D_OT_slvs_mcp_start,
        View3D_OT_slvs_mcp_stop,
        View3D_OT_slvs_mcp_copy_url,
        View3D_OT_slvs_mcp_new_token,
        View3D_OT_slvs_mcp_clear_activity,
    )
)
