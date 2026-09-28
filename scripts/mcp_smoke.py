#!/usr/bin/env python3
"""Exercise a running CAD Sketcher MCP endpoint, without needing an AI client.

Start the server from the Sketcher sidebar, press Copy Address (with the format
left on "URL"), then:

    python3 scripts/mcp_smoke.py "http://127.0.0.1:9877/mcp/<token>"

Builds a fully constrained plate with a located hole in the open Blender
session, checks that a bad edit is refused, and checks that the endpoint turns
away a browser and a guessed token. Watch the viewport while it runs; one
Ctrl+Z afterwards takes the whole thing back.
"""

import argparse
import json
import sys
import urllib.error
import urllib.request

PROTOCOL_VERSION = "2026-07-28"

PLATE_OPS = [
    {"op": "point", "name": "a", "co": [0, 0], "fixed": True},
    {"op": "point", "name": "b", "co": [0.08, 0.003]},
    {"op": "point", "name": "c", "co": [0.08, 0.05]},
    {"op": "point", "name": "d", "co": [0, 0.05]},
    {"op": "line", "name": "bottom", "p1": "a", "p2": "b"},
    {"op": "line", "name": "right", "p1": "b", "p2": "c"},
    {"op": "line", "name": "top", "p1": "c", "p2": "d"},
    {"op": "line", "name": "left", "p1": "d", "p2": "a"},
    {"op": "constrain", "type": "horizontal", "refs": ["bottom"]},
    {"op": "constrain", "type": "horizontal", "refs": ["top"]},
    {"op": "constrain", "type": "vertical", "refs": ["left"]},
    {"op": "constrain", "type": "vertical", "refs": ["right"]},
    {"op": "constrain", "type": "distance", "refs": ["a", "b"], "value": 0.08},
    {"op": "constrain", "type": "distance", "refs": ["a", "d"], "value": 0.05},
    {"op": "point", "name": "hc", "co": [0.02, 0.025]},
    {"op": "circle", "name": "hole", "center": "hc", "radius": 0.005},
    {"op": "constrain", "type": "diameter", "refs": ["hole"], "value": 0.012},
    {"op": "constrain", "type": "distance", "refs": ["hc", "left"], "value": 0.02},
    {"op": "constrain", "type": "distance", "refs": ["hc", "bottom"], "value": 0.025},
]


def rpc(url, method, params=None, headers=None):
    """One JSON-RPC call. Returns (http status, parsed body)."""
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={
            "Content-Type": "application/json",
            "MCP-Protocol-Version": PROTOCOL_VERSION,
            **(headers or {}),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def call(url, tool, arguments=None):
    """Run one tool. Returns (text or None, is_error)."""
    status, body = rpc(url, "tools/call", {"name": tool, "arguments": arguments or {}})
    if "error" in body:
        raise SystemExit(f"{tool}: JSON-RPC error {body['error']}")
    result = body["result"]
    texts = [c["text"] for c in result.get("content", []) if c.get("type") == "text"]
    images = [c for c in result.get("content", []) if c.get("type") == "image"]
    if images:
        print(f"   got an image, {len(images[0]['data'])} base64 chars")
    return (texts[0] if texts else None), bool(result.get("isError"))


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' : ' + detail) if detail else ''}")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="the endpoint address from the Sketcher sidebar")
    url = parser.parse_args().url
    passed = []

    print("\n-- the endpoint answers --")
    _, body = rpc(url, "server/discover")
    info = body["result"]["_meta"]["io.modelcontextprotocol/serverInfo"]
    passed.append(
        check("discover", info["name"] == "cad-sketcher", f"v{info['version']}")
    )

    _, body = rpc(url, "tools/list")
    names = sorted(t["name"] for t in body["result"]["tools"])
    passed.append(check("tools/list", len(names) == 7, ", ".join(names)))

    print("\n-- it can read the scene --")
    text, _ = call(url, "describe_scene")
    scene = json.loads(text)
    passed.append(
        check(
            "describe_scene", "units" in scene, f"{len(scene['sketches'])} sketch(es)"
        )
    )

    print("\n-- it can build a fully defined plate --")
    text, _ = call(url, "create_sketch", {"name": "Smoke", "plane": "XY"})
    sketch_name = json.loads(text)["sketch"]
    print(f"   created {sketch_name!r}")

    text, err = call(url, "edit_sketch", {"sketch": sketch_name, "ops": PLATE_OPS})
    if err:
        return not check("edit_sketch", False, text)
    plate = json.loads(text)
    passed.append(
        check(
            "edit_sketch",
            not err,
            f"{plate['applied']['entities_added']} entities, "
            f"{plate['applied']['constraints_added']} constraints",
        )
    )
    passed.append(
        check(
            "solves to fully defined",
            plate["fully_defined"],
            f"dof {plate['dof']}, {plate['solver_state']}",
        )
    )

    print("\n-- it refuses a wrong-typed constraint --")
    text, err = call(
        url,
        "edit_sketch",
        {
            "sketch": sketch_name,
            "ops": [{"op": "constrain", "type": "parallel", "refs": ["a", "a"]}],
        },
    )
    passed.append(check("bad edit refused", err, (text or "").strip()))

    print("\n-- it can show you the result --")
    text, err = call(url, "render_sketch", {"sketch": sketch_name, "size": 600})
    passed.append(check("render_sketch", not err, text or ""))

    print("\n-- it turns away what it should --")
    status, _ = rpc(url, "tools/list", headers={"Origin": "https://evil.example"})
    passed.append(check("browser origin refused", status == 403, f"HTTP {status}"))

    status, _ = rpc(url.rsplit("/", 1)[0] + "/guessed", "tools/list")
    passed.append(check("guessed token refused", status == 404, f"HTTP {status}"))

    print(f"\n{sum(passed)}/{len(passed)} passed.")
    print("The plate is in your viewport; Ctrl+Z takes back each edit.")
    return 0 if all(passed) else 1


if __name__ == "__main__":
    sys.exit(main())
