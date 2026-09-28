"""Ways to hand the endpoint's address to an MCP client.

The transport is standard, so any conforming client can reach the endpoint from
its URL alone. How a client is *told* about it is not standard: the config files
disagree on the top-level key and on whether the transport has to be named, and
CLI helpers are per-client. So the URL is what this offers first, and the rest
are conveniences for the clients people actually use.
"""

import json
from typing import List, Tuple

SERVER_NAME = "cad-sketcher"


def url_only(url: str) -> str:
    """The address itself. Every MCP client can be pointed at this."""
    return url


def claude_code(url: str) -> str:
    """The Claude Code CLI one-liner."""
    return f'claude mcp add --transport http {SERVER_NAME} "{url}"'


def mcp_servers_json(url: str) -> str:
    """The ``mcpServers`` block, as Cursor, Claude and Windsurf read it."""
    return json.dumps({"mcpServers": {SERVER_NAME: {"url": url}}}, indent=2)


def vscode_json(url: str) -> str:
    """The VS Code block, which keys on ``servers`` and names the transport."""
    return json.dumps(
        {"servers": {SERVER_NAME: {"type": "http", "url": url}}}, indent=2
    )


FORMATS = {
    "URL": url_only,
    "CLAUDE_CODE": claude_code,
    "JSON": mcp_servers_json,
    "VSCODE": vscode_json,
}

# (identifier, label, description) for the preference and the operator.
FORMAT_ITEMS: List[Tuple[str, str, str]] = [
    (
        "URL",
        "URL",
        "Just the address. Paste it wherever your client asks for an MCP server URL",
    ),
    (
        "CLAUDE_CODE",
        "Claude Code",
        "A command to run in a terminal, which registers the endpoint",
    ),
    (
        "JSON",
        "Cursor / Claude / Windsurf",
        "An mcpServers entry for a client's JSON config file",
    ),
    (
        "VSCODE",
        "VS Code",
        "A servers entry for mcp.json, which names the transport explicitly",
    ),
]


def snippet(url: str, client_format: str) -> str:
    """What to put on the clipboard for ``client_format``."""
    return FORMATS.get(client_format, url_only)(url)
