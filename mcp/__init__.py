"""Model Context Protocol endpoint, so an agent can drive sketches.

Blender serves MCP itself, over Streamable HTTP on loopback, rather than talking
an ad-hoc protocol to a helper process that speaks MCP on its behalf: the client
then needs nothing installed and connects by URL.

Nothing listens until the user starts it from the Sketcher sidebar.
"""

import logging

from ..utilities.register import module_register_factory

logger = logging.getLogger(__name__)

modules = [
    "operators",
    "ui",
]

_register_modules, _unregister_modules = module_register_factory(__name__, modules)


def register() -> None:
    """Register the MCP operators and panel, serving only if asked to."""
    _register_modules()
    _auto_start()


def _auto_start() -> None:
    """Serve on launch when the user has asked for that.

    Deferred to a timer: preferences and the add-on's own modules are not both
    ready during register, and a failure here must not take registration with it.
    """
    import bpy

    def once():
        try:
            from ..utilities.preferences import get_prefs

            if not get_prefs().mcp_auto_start or bpy.app.background:
                return None
            from . import server

            server.start_server(port=get_prefs().mcp_port)
        except Exception:
            logger.exception("Could not auto-start the MCP endpoint")
        return None

    bpy.app.timers.register(once, first_interval=0.0)


def unregister() -> None:
    """Unregister, stopping the server so a disabled add-on frees its port."""
    from . import server

    server.stop_server()
    _unregister_modules()
