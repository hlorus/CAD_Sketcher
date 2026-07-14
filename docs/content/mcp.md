## MCP Agent Interface

CAD Sketcher can expose a dedicated [Model Context Protocol](https://modelcontextprotocol.io/)
server so tools like Cursor or Claude can author sketches, constraints, and solve
systems in a **live Blender session**.

This is separate from [blender-mcp](https://github.com/ahujasid/blender-mcp)
(port **9876**). CAD Sketcher uses port **9877** by default so both can run together.

### Architecture

1. **In-addon TCP bridge** — Sketcher sidebar → **MCP** → Start Server (`localhost:9877`)
2. **External FastMCP process** — `cad-sketcher-mcp` (via `uvx`) talks MCP stdio to the IDE and proxies JSON commands to the bridge

Agents should prefer the typed sketch tools (points, lines, constraints, solve).
`execute_sketcher_code` is an escape hatch that injects `bpy`, `sketcher`,
`entities`, and `constraints`.

### Blender setup

1. Enable CAD Sketcher (solver module required).
2. In the 3D View press **N** → **Sketcher** → **MCP**.
3. Confirm host/port (default `localhost` / `9877`).
4. Click **Start Server**.

Optional: Edit → Preferences → Add-ons → CAD Sketcher → **Auto-start MCP Server**.

### Cursor setup

Install [`uv`](https://docs.astral.sh/uv/) if needed (`brew install uv` on macOS).

Add a server to `~/.cursor/mcp.json` (global) or the project's `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "cad-sketcher": {
      "command": "/opt/homebrew/bin/uvx",
      "args": [
        "--from",
        "/ABSOLUTE/PATH/TO/CAD_Sketcher/mcp_package",
        "cad-sketcher-mcp"
      ],
      "env": {
        "BLENDER_HOST": "localhost",
        "BLENDER_PORT": "9877"
      }
    }
  }
}
```

Use the absolute path to `uvx` (GUI apps often do not inherit shell `PATH`).

Fully quit and reopen Cursor, then verify **Cursor Settings → Tools & MCP** shows
`cad-sketcher`.

### Core tools

| Tool | Purpose |
|------|---------|
| `get_sketcher_status` | Solver / active sketch / counts |
| `list_sketches` / `get_sketch` | Inspect sketches and DOF |
| `list_entities` / `list_constraints` | Inspect geometry (entity index / constraint UID) |
| `add_sketch` / `set_active_sketch` | Lifecycle |
| `add_point_2d` / `add_line_2d` / `add_circle_2d` / `add_arc_2d` | Geometry |
| `add_distance` / `add_coincident` / `add_horizontal` / `add_vertical` / … | Constraints |
| `delete_entity` / `delete_constraint` | Cleanup |
| `solve` | Run the solver |
| `execute_sketcher_code` | Restricted Python escape hatch |

Entity IDs are CAD Sketcher **global indices** (`slvs_index`). Constraint IDs are
**`constraint_uid`** strings.

### Limitations

- Requires a GUI Blender session (commands are scheduled on the main thread).
- Modal View3D tools (trim, bevel, move, pick) are not exposed.
- Convert / fill / extrude / screenshots are not in the first MVP.
