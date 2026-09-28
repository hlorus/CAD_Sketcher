"""Model Context Protocol endpoint, so an agent can drive sketches.

Blender serves MCP itself, over Streamable HTTP on loopback, rather than talking
an ad-hoc protocol to a helper process that speaks MCP on its behalf: the client
then needs nothing installed and connects by URL.

Nothing listens until the user starts it from the Sketcher sidebar.
"""

from ..utilities.register import module_register_factory

modules = [
    "operators",
    "ui",
]

_register_modules, _unregister_modules = module_register_factory(__name__, modules)


def register() -> None:
    """Register the MCP operators and panel. Starts no server."""
    _register_modules()


def unregister() -> None:
    """Unregister, stopping the server so a disabled add-on frees its port."""
    from . import server

    server.stop_server()
    _unregister_modules()
