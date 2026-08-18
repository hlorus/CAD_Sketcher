"""CAD Sketcher MCP submodule: TCP bridge + UI + handlers."""

from . import operators, ui
from . import server as mcp_server


def register():
    operators.register()
    ui.register()
    try:
        from ..utilities.preferences import get_prefs

        prefs = get_prefs()
        if getattr(prefs, "mcp_auto_start", False) and not bpy_app_background():
            host = getattr(prefs, "mcp_host", mcp_server.DEFAULT_HOST)
            port = int(getattr(prefs, "mcp_port", mcp_server.DEFAULT_PORT))
            mcp_server.start_server(host=host, port=port)
    except Exception:
        # Preferences/server may not be ready in all register paths
        pass


def unregister():
    mcp_server.stop_server()
    ui.unregister()
    operators.unregister()


def bpy_app_background() -> bool:
    import bpy

    return bool(bpy.app.background)
