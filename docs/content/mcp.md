# AI Agent (MCP)

CAD Sketcher can serve a [Model Context Protocol](https://modelcontextprotocol.io)
endpoint, which lets an AI agent such as Claude Code or Cursor read and edit
sketches in your running Blender session.

It is off until you start it, and it listens only on your own machine.

## Connecting

1. Open the **Sketcher** sidebar in the 3D viewport (press <kbd>N</kbd>) and
   expand **AI Agent (MCP)**.
2. Press **Start Server**, then **Copy URL**.
3. Give the URL to your agent. For Claude Code:

    ```sh
    claude mcp add --transport http cad-sketcher <paste the URL>
    ```

    For an editor that takes a JSON config, add a server with that `url`.

The URL contains an access token that is new every time you start the server, so
starting it again means reconnecting the agent. Blender's **Allow Online Access**
preference must be on.

## What the agent can do

| Tool | What it does |
| --- | --- |
| `describe_scene` | Lists the sketches in the scene and the unit settings |
| `describe_sketch` | Reads one sketch: entities, constraints, degrees of freedom |
| `render_sketch` | Renders the sketch square-on so the agent can see its work |
| `create_sketch` | Starts a sketch on the XY, XZ or YZ plane |
| `edit_sketch` | Adds, constrains, renames and deletes, then solves |
| `delete_sketch` | Deletes a sketch and the geometry built from it |
| `solve_sketch` | Re-runs the solver and reports the state |

`edit_sketch` takes a whole list of edits at once. The agent builds a shape in
one step rather than one call per line, and the result is a single entry in your
undo history, so <kbd>Ctrl</kbd>+<kbd>Z</kbd> takes back the whole thing.

Everything else stays yours. The agent cannot run arbitrary code, reach your
files, or touch anything in Blender outside CAD Sketcher's sketches.

## While it is running

- Keep working in Blender as usual. A request that arrives while you are drawing
  or dragging is refused with a note to try again, rather than interrupting you.
- Any program on your machine that has the URL can edit your sketches, so treat
  the URL like a password and stop the server when you are done.
- Ask the agent to render the sketch as it goes. Coordinates and degrees of
  freedom rarely show that a shape came out wrong, and a picture does.

## Troubleshooting

**"Online access is off"** — turn on Allow Online Access in
Preferences ‣ System ‣ Network.

**"Port is not available"** — something else already holds port 9877. Change
**MCP Port** in the add-on preferences and start the server again.

**The agent says the call timed out** — Blender was busy with a tool you had
open. Finish or cancel it and ask the agent to retry.
