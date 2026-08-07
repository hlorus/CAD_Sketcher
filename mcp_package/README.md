# CAD Sketcher MCP

FastMCP stdio server that proxies tools to the CAD Sketcher add-on TCP bridge
(default `localhost:9877`).

## Cursor config

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

In Blender: Sketcher sidebar → **MCP** → **Start Server**. Coexists with
blender-mcp on port 9876.
