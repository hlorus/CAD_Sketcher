"""The MCP endpoint: Streamable HTTP on loopback, served by Blender itself.

Revision 2026-07-28 took sessions, the GET stream and stream resumption out of
Streamable HTTP, which leaves a server that is one POST path answering JSON. That
is small enough to serve from inside Blender with the standard library, so no
helper process and nothing for the user to install: the client is handed a URL.

Safety, in the order it is checked:

* The URL carries a token minted when the server starts, so a process that has
  not been told the token cannot reach the tools.
* A request carrying an ``Origin`` header is refused. Real MCP clients send none
  and browsers always do, so this one rule is the DNS-rebinding defence the spec
  requires: without it any page the user visits could drive their CAD session.
* Bound to 127.0.0.1 only, never a routable interface.

Requests are handed to Blender's main thread through a timer and run one at a
time: ``bpy`` is not reentrant, and two agents editing one sketch at once would
interleave writes.
"""

import json
import logging
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional, Tuple

from . import dispatch

logger = logging.getLogger(__name__)

HOST = "127.0.0.1"
DEFAULT_PORT = 9877

# The revision this server implements, plus the older ones it answers rather than
# reject: a client on one of those opens with `initialize` and omits the
# per-request metadata, which the spec allows a server to accept.
PROTOCOL_VERSION = "2026-07-28"
SUPPORTED_VERSIONS = (PROTOCOL_VERSION, "2025-11-25", "2025-06-18", "2025-03-26")

_META_VERSION = "io.modelcontextprotocol/protocolVersion"

# JSON-RPC and MCP error codes.
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INTERNAL_ERROR = -32603
HEADER_MISMATCH = -32020

_server: Optional["MCPServer"] = None


class ProtocolError(Exception):
    """A malformed request, answered with an HTTP status and a JSON-RPC error."""

    def __init__(self, status: int, code: int, message: str, data: Any = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.data = data


class MCPServer:
    """A running endpoint, and the token its URL carries."""

    def __init__(self, port: int = DEFAULT_PORT):
        self.port = int(port)
        self.token = secrets.token_urlsafe(16)
        self._httpd: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    @property
    def url(self) -> str:
        """The URL to give an MCP client."""
        return f"http://{HOST}:{self.port}/mcp/{self.token}"

    @property
    def running(self) -> bool:
        return self._httpd is not None

    def start(self) -> None:
        """Bind the port and serve in a background thread."""
        if self.running:
            return

        server = self

        class Handler(_RequestHandler):
            mcp_server = server

        self._httpd = ThreadingHTTPServer((HOST, self.port), Handler)
        self._httpd.daemon_threads = True
        # Port 0 means "any free port", so read back what was actually bound.
        self.port = self._httpd.server_address[1]
        self._thread = threading.Thread(
            target=self._httpd.serve_forever,
            kwargs={"poll_interval": 0.25},
            daemon=True,
            name="cad-sketcher-mcp",
        )
        self._thread.start()
        logger.info("CAD Sketcher MCP listening on %s", self.url)

    def stop(self) -> None:
        """Stop serving and free the port."""
        httpd, self._httpd = self._httpd, None
        thread, self._thread = self._thread, None
        if httpd is not None:
            httpd.shutdown()
            httpd.server_close()
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)
        logger.info("CAD Sketcher MCP stopped")


class _RequestHandler(BaseHTTPRequestHandler):
    """One MCP endpoint: POST only, everything else refused."""

    mcp_server: MCPServer = None
    protocol_version = "HTTP/1.1"
    server_version = "CADSketcherMCP"
    sys_version = ""

    def log_message(self, fmt: str, *args) -> None:
        """Send request logs to the add-on's logger instead of stderr."""
        logger.debug("mcp %s", fmt % args)

    # -- HTTP verbs --

    def do_POST(self) -> None:
        try:
            self._check_request()
            body = self._read_body()
        except ProtocolError as e:
            self._send_error(e)
            return

        method = body.get("method")
        is_request = "id" in body and body.get("id") is not None

        if not is_request:
            # A notification: acknowledged, never answered.
            self._send_empty(202)
            return

        try:
            result = self._handle(method, body)
        except ProtocolError as e:
            self._send_error(e, request_id=body.get("id"))
            return
        except Exception:
            logger.exception("MCP request failed")
            self._send_json(
                500,
                _error_body(body.get("id"), INTERNAL_ERROR, "Internal error"),
            )
            return

        self._send_json(200, {"jsonrpc": "2.0", "id": body.get("id"), "result": result})

    def do_GET(self) -> None:
        """No GET stream in this revision."""
        self._send_empty(405)

    def do_DELETE(self) -> None:
        """No sessions in this revision, so nothing to terminate."""
        self._send_empty(405)

    # -- Checks --

    def _check_request(self) -> None:
        """Origin, path token and protocol version, before anything is parsed."""
        # A browser always sends Origin and an MCP client never does, so this is
        # what stops a visited web page from reaching a local CAD session.
        if self.headers.get("Origin"):
            raise ProtocolError(
                403,
                INVALID_REQUEST,
                "Requests carrying an Origin header are refused.",
            )

        expected = f"/mcp/{self.mcp_server.token}"
        if self.path.rstrip("/") != expected:
            raise ProtocolError(404, INVALID_REQUEST, "Not found.")

    def _read_body(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            raise ProtocolError(400, INVALID_REQUEST, "Empty request body.")
        raw = self.rfile.read(length)
        try:
            body = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise ProtocolError(400, PARSE_ERROR, f"Invalid JSON: {e}") from e
        if not isinstance(body, dict):
            raise ProtocolError(
                400, INVALID_REQUEST, "Body must be a single JSON-RPC message."
            )
        self._check_metadata(body)
        return body

    def _check_metadata(self, body: Dict[str, Any]) -> None:
        """Validate the mirrored headers against the body they mirror.

        The point of the check is that nothing downstream can route on a header
        that disagrees with what will actually be executed. Headers absent
        altogether mean an older client, which the spec lets a server accept.
        """
        header_version = self.headers.get("MCP-Protocol-Version")
        params = body.get("params") if isinstance(body.get("params"), dict) else {}
        meta = params.get("_meta") if isinstance(params.get("_meta"), dict) else {}
        body_version = meta.get(_META_VERSION)

        if header_version and body_version and header_version != body_version:
            raise ProtocolError(
                400,
                HEADER_MISMATCH,
                f"MCP-Protocol-Version {header_version!r} does not match the "
                f"body's {body_version!r}.",
            )

        version = header_version or body_version
        if version and version not in SUPPORTED_VERSIONS:
            raise ProtocolError(
                400,
                INVALID_REQUEST,
                f"Unsupported protocol version {version!r}.",
                {"supported": list(SUPPORTED_VERSIONS)},
            )

        header_method = self.headers.get("Mcp-Method")
        if header_method and header_method != body.get("method"):
            raise ProtocolError(
                400,
                HEADER_MISMATCH,
                f"Mcp-Method {header_method!r} does not match the body's "
                f"{body.get('method')!r}.",
            )

        header_name = self.headers.get("Mcp-Name")
        if header_name and body.get("method") == "tools/call":
            if header_name != params.get("name"):
                raise ProtocolError(
                    400,
                    HEADER_MISMATCH,
                    f"Mcp-Name {header_name!r} does not match the body's "
                    f"{params.get('name')!r}.",
                )

    # -- Methods --

    def _handle(self, method: str, body: Dict[str, Any]) -> Dict[str, Any]:
        params = body.get("params") if isinstance(body.get("params"), dict) else {}

        if method == "initialize":
            return self._initialize(params)
        if method == "ping":
            return {}
        if method == "tools/list":
            from . import tools

            return {"tools": tools.listing()}
        if method == "tools/call":
            return dispatch.call_tool(params.get("name"), params.get("arguments") or {})

        raise ProtocolError(404, METHOD_NOT_FOUND, f"Unknown method {method!r}.")

    def _initialize(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Answer the handshake older clients still open with."""
        asked = params.get("protocolVersion")
        version = asked if asked in SUPPORTED_VERSIONS else PROTOCOL_VERSION
        from .. import get_addon_version

        return {
            "protocolVersion": version,
            "capabilities": {"tools": {}},
            "serverInfo": {
                "name": "cad-sketcher",
                "title": "CAD Sketcher",
                "version": get_addon_version(),
            },
        }

    # -- Responses --

    def _send_json(self, status: int, payload: Dict[str, Any]) -> None:
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _send_empty(self, status: int) -> None:
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _send_error(self, error: ProtocolError, request_id: Any = None) -> None:
        self._send_json(
            error.status,
            _error_body(request_id, error.code, error.message, error.data),
        )


def _error_body(
    request_id: Any, code: int, message: str, data: Any = None
) -> Dict[str, Any]:
    error: Dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": error}


# -- Lifecycle ---------------------------------------------------------------


def get_server() -> Optional[MCPServer]:
    """The running server, or None."""
    return _server


def is_running() -> bool:
    return _server is not None and _server.running


def start_server(port: int = DEFAULT_PORT) -> MCPServer:
    """Start the endpoint on ``port``, replacing one already running."""
    global _server
    if _server is not None and _server.running:
        if _server.port == int(port):
            return _server
        _server.stop()
    server = MCPServer(port=port)
    server.start()
    _server = server
    return server


def stop_server() -> None:
    """Stop the endpoint, if one is running."""
    global _server
    if _server is not None:
        _server.stop()
        _server = None


def address_in_use(port: int) -> Tuple[bool, str]:
    """Whether ``port`` is already taken, for a message before binding."""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind((HOST, int(port)))
        except OSError as e:
            return True, str(e)
    return False, ""
