"""CAD Sketcher FastMCP server — proxies tools to the Blender add-on on TCP 9877."""

from __future__ import annotations

import json
import logging
import os
import socket
from typing import Any, Dict, Optional

from mcp.server.fastmcp import FastMCP

logger = logging.getLogger("CadSketcherMCP")
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

DEFAULT_HOST = os.environ.get("BLENDER_HOST", "localhost")
DEFAULT_PORT = int(os.environ.get("BLENDER_PORT", "9877"))

mcp = FastMCP("CADSketcherMCP")


class BlenderConnection:
    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
        self.host = host
        self.port = port
        self.sock: Optional[socket.socket] = None

    def connect(self) -> bool:
        if self.sock:
            return True
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.host, self.port))
            self.sock.settimeout(180.0)
            return True
        except Exception as e:
            logger.error("Failed to connect to CAD Sketcher MCP bridge: %s", e)
            self.sock = None
            return False

    def disconnect(self):
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None

    def _receive(self) -> bytes:
        assert self.sock is not None
        chunks = []
        self.sock.settimeout(180.0)
        while True:
            chunk = self.sock.recv(8192)
            if not chunk:
                break
            chunks.append(chunk)
            data = b"".join(chunks)
            try:
                json.loads(data.decode("utf-8"))
                return data
            except json.JSONDecodeError:
                continue
        if chunks:
            data = b"".join(chunks)
            json.loads(data.decode("utf-8"))
            return data
        raise ConnectionError("No data received from Blender")

    def send_command(
        self, command_type: str, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        if not self.sock and not self.connect():
            raise ConnectionError(
                f"Not connected to CAD Sketcher at {self.host}:{self.port}. "
                "In Blender open Sketcher → MCP → Start Server."
            )
        assert self.sock is not None
        payload = {"type": command_type, "params": params or {}}
        try:
            self.sock.sendall(json.dumps(payload).encode("utf-8"))
            raw = self._receive()
            response = json.loads(raw.decode("utf-8"))
            if response.get("status") == "error":
                raise RuntimeError(response.get("message", "Unknown Blender error"))
            return response.get("result", {})
        except Exception:
            self.disconnect()
            raise


_connection: Optional[BlenderConnection] = None


def get_connection() -> BlenderConnection:
    global _connection
    if _connection is None:
        _connection = BlenderConnection()
    if not _connection.sock and not _connection.connect():
        raise ConnectionError(
            f"Cannot reach CAD Sketcher MCP at {_connection.host}:{_connection.port}"
        )
    return _connection


def _call(command_type: str, **params) -> str:
    result = get_connection().send_command(command_type, params)
    return json.dumps(result, indent=2)


@mcp.tool()
def get_sketcher_status() -> str:
    """Check CAD Sketcher status: solver availability, active sketch, counts."""
    return _call("get_sketcher_status")


@mcp.tool()
def ensure_origin() -> str:
    """Ensure origin workplanes/axes exist for sketching."""
    return _call("ensure_origin")


@mcp.tool()
def list_sketches() -> str:
    """List all sketches in the scene."""
    return _call("list_sketches")


@mcp.tool()
def get_sketch(sketch_i: int = -1) -> str:
    """Get one sketch by index (-1 = active sketch), including DOF and solver state."""
    params: Dict[str, Any] = {}
    if sketch_i != -1:
        params["sketch_i"] = sketch_i
    return _call("get_sketch", **params)


@mcp.tool()
def list_entities(sketch_i: int = -1, include_origin: bool = False) -> str:
    """List sketch entities. Pass sketch_i or -1 for all non-origin entities."""
    params: Dict[str, Any] = {"include_origin": include_origin}
    if sketch_i != -1:
        params["sketch_i"] = sketch_i
    return _call("list_entities", **params)


@mcp.tool()
def list_constraints(sketch_i: int = -1) -> str:
    """List constraints, optionally filtered by sketch_i."""
    params: Dict[str, Any] = {}
    if sketch_i != -1:
        params["sketch_i"] = sketch_i
    return _call("list_constraints", **params)


@mcp.tool()
def add_sketch(name: str = "", activate: bool = True, workplane_i: int = -1) -> str:
    """Create a new sketch on the XY origin workplane (or a given workplane index)."""
    params: Dict[str, Any] = {"activate": activate}
    if name:
        params["name"] = name
    if workplane_i != -1:
        params["workplane_i"] = workplane_i
    return _call("add_sketch", **params)


@mcp.tool()
def set_active_sketch(sketch_i: int = -1) -> str:
    """Set the active sketch by index, or -1 to clear."""
    return _call("set_active_sketch", sketch_i=sketch_i)


@mcp.tool()
def add_point_2d(
    x: float,
    y: float,
    sketch_i: int = -1,
    fixed: bool = False,
    construction: bool = False,
) -> str:
    """Add a 2D point to a sketch (default: active sketch)."""
    params: Dict[str, Any] = {
        "co": [x, y],
        "fixed": fixed,
        "construction": construction,
    }
    if sketch_i != -1:
        params["sketch_i"] = sketch_i
    return _call("add_point_2d", **params)


@mcp.tool()
def add_line_2d(
    p1_i: int, p2_i: int, sketch_i: int = -1, construction: bool = False
) -> str:
    """Add a 2D line between two point entity indices."""
    params: Dict[str, Any] = {
        "p1_i": p1_i,
        "p2_i": p2_i,
        "construction": construction,
    }
    if sketch_i != -1:
        params["sketch_i"] = sketch_i
    return _call("add_line_2d", **params)


@mcp.tool()
def add_circle_2d(
    center_i: int, radius: float, sketch_i: int = -1, construction: bool = False
) -> str:
    """Add a 2D circle given center point index and radius."""
    params: Dict[str, Any] = {
        "center_i": center_i,
        "radius": radius,
        "construction": construction,
    }
    if sketch_i != -1:
        params["sketch_i"] = sketch_i
    return _call("add_circle_2d", **params)


@mcp.tool()
def add_arc_2d(
    center_i: int,
    p1_i: int,
    p2_i: int,
    sketch_i: int = -1,
    construction: bool = False,
    invert: bool = False,
) -> str:
    """Add a 2D arc given center and endpoint point indices."""
    params: Dict[str, Any] = {
        "center_i": center_i,
        "p1_i": p1_i,
        "p2_i": p2_i,
        "construction": construction,
        "invert": invert,
    }
    if sketch_i != -1:
        params["sketch_i"] = sketch_i
    return _call("add_arc_2d", **params)


@mcp.tool()
def add_distance(
    entity1_i: int,
    entity2_i: int,
    value: float,
    sketch_i: int = -1,
) -> str:
    """Add a distance constraint between two entities and set its value."""
    params: Dict[str, Any] = {
        "entity1_i": entity1_i,
        "entity2_i": entity2_i,
        "value": value,
    }
    if sketch_i != -1:
        params["sketch_i"] = sketch_i
    return _call("add_distance", **params)


@mcp.tool()
def add_coincident(entity1_i: int, entity2_i: int, sketch_i: int = -1) -> str:
    """Add a coincident constraint between two entities."""
    params: Dict[str, Any] = {"entity1_i": entity1_i, "entity2_i": entity2_i}
    if sketch_i != -1:
        params["sketch_i"] = sketch_i
    return _call("add_coincident", **params)


@mcp.tool()
def add_horizontal(entity1_i: int, sketch_i: int = -1, entity2_i: int = -1) -> str:
    """Add a horizontal constraint to a line (or between two points)."""
    params: Dict[str, Any] = {"entity1_i": entity1_i}
    if entity2_i != -1:
        params["entity2_i"] = entity2_i
    if sketch_i != -1:
        params["sketch_i"] = sketch_i
    return _call("add_horizontal", **params)


@mcp.tool()
def add_vertical(entity1_i: int, sketch_i: int = -1, entity2_i: int = -1) -> str:
    """Add a vertical constraint to a line (or between two points)."""
    params: Dict[str, Any] = {"entity1_i": entity1_i}
    if entity2_i != -1:
        params["entity2_i"] = entity2_i
    if sketch_i != -1:
        params["sketch_i"] = sketch_i
    return _call("add_vertical", **params)


@mcp.tool()
def add_equal(entity1_i: int, entity2_i: int, sketch_i: int = -1) -> str:
    """Add an equal-length / equal-radius constraint."""
    params: Dict[str, Any] = {"entity1_i": entity1_i, "entity2_i": entity2_i}
    if sketch_i != -1:
        params["sketch_i"] = sketch_i
    return _call("add_equal", **params)


@mcp.tool()
def add_parallel(entity1_i: int, entity2_i: int, sketch_i: int = -1) -> str:
    """Add a parallel constraint between two lines."""
    params: Dict[str, Any] = {"entity1_i": entity1_i, "entity2_i": entity2_i}
    if sketch_i != -1:
        params["sketch_i"] = sketch_i
    return _call("add_parallel", **params)


@mcp.tool()
def add_perpendicular(entity1_i: int, entity2_i: int, sketch_i: int = -1) -> str:
    """Add a perpendicular constraint between two lines."""
    params: Dict[str, Any] = {"entity1_i": entity1_i, "entity2_i": entity2_i}
    if sketch_i != -1:
        params["sketch_i"] = sketch_i
    return _call("add_perpendicular", **params)


@mcp.tool()
def add_tangent(entity1_i: int, entity2_i: int, sketch_i: int = -1) -> str:
    """Add a tangent constraint between curve/line entities."""
    params: Dict[str, Any] = {"entity1_i": entity1_i, "entity2_i": entity2_i}
    if sketch_i != -1:
        params["sketch_i"] = sketch_i
    return _call("add_tangent", **params)


@mcp.tool()
def delete_entity(index: int) -> str:
    """Delete an entity by its global index (cannot delete origin entities)."""
    return _call("delete_entity", index=index)


@mcp.tool()
def delete_constraint(uid: str) -> str:
    """Delete a constraint by its UID string."""
    return _call("delete_constraint", uid=uid)


@mcp.tool()
def solve(sketch_i: int = -1, all_sketches: bool = False) -> str:
    """Solve the active sketch (or sketch_i). Set all_sketches=True to solve everything."""
    params: Dict[str, Any] = {"all_sketches": all_sketches}
    if sketch_i != -1:
        params["sketch_i"] = sketch_i
    return _call("solve", **params)


@mcp.tool()
def execute_sketcher_code(code: str) -> str:
    """Execute Python in Blender with bpy, sketcher, entities, constraints in scope."""
    return _call("execute_sketcher_code", code=code)


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
