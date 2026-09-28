# AI Agent (MCP)

CAD Sketcher can serve a [Model Context Protocol](https://modelcontextprotocol.io)
endpoint, which lets an AI agent such as Claude Code or Cursor read and edit
sketches in your running Blender session.

It is off until you start it, and it listens only on your own machine.

## Connecting

CAD Sketcher speaks MCP over its standard HTTP transport, so **any MCP client
can connect**: all it needs is the endpoint's address.

1. Open the **Sketcher** sidebar in the 3D viewport (press <kbd>N</kbd>) and
   expand **AI Agent (MCP)**.
2. Press **Start Server**.
3. Choose your client from the dropdown and press **Copy Address**. Leave it on
   **URL** if your client just asks for a server address, which most do.

The dropdown only changes the shape of what is copied:

| Choice | What you get |
| --- | --- |
| URL | The address on its own |
| Claude Code | A `claude mcp add` command to run in a terminal |
| Cursor / Claude / Windsurf | An `mcpServers` entry for the client's JSON config |
| VS Code | A `servers` entry for `mcp.json` |

You only do this once. The address stays the same between sessions, so the agent
stays connected. Blender's **Allow Online Access** preference must be on.

Tick **Start on launch** and the endpoint is served from the moment Blender
opens, with nothing to press at all.

The URL carries an access token, kept in the add-on's own user folder. **New
Access Token** replaces it, which makes any URL you handed out before stop
working; reconnect the agent afterwards.

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

The server also tells the agent how to work here: units, constraining rather
than placing by eye, aiming for a fully defined sketch, and checking its own
work with a render. You should not have to explain any of that yourself.

Everything else stays yours. The agent cannot run arbitrary code, reach your
files, or touch anything in Blender outside CAD Sketcher's sketches.

## Watching what it does

The panel lists the agent's recent calls: what it touched, what it added, and
anything it was refused. An agent works in another window, so this is what makes
its work legible without switching to it.

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
