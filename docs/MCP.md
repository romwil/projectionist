# CuratorX MCP

CuratorX exposes a read-oriented Model Context Protocol server over your indexed Plex library.

## Install

```bash
pip install "curatorx[mcp]"
# or in Docker image (1.2+): already included
```

## Stdio (Cursor / Claude Desktop)

```bash
DATA_DIR=/path/to/config curatorx-mcp
# equivalent: python -m curatorx.mcp
```

Sample Cursor config (`.cursor/mcp.json` or user MCP settings):

```json
{
  "mcpServers": {
    "curatorx": {
      "command": "curatorx-mcp",
      "env": {
        "DATA_DIR": "/mnt/user/appdata/curatorx/config"
      }
    }
  }
}
```

Repo sample: [`mcp.json`](../mcp.json).

## HTTP transport

When `CURATORX_MCP_API_KEY` is set, the web process mounts Streamable HTTP MCP at `/mcp`.

```bash
curl -H "X-CuratorX-MCP-Key: $CURATORX_MCP_API_KEY" \
  http://127.0.0.1:8788/mcp
```

Without the env var, `/mcp` returns **503**.

## Tools (library-focused)

| Tool | Purpose |
|------|---------|
| `library_query` / `library_aggregate` / facets / TV helpers | Browse owned inventory |
| `library_overview_tool` / `library_title_detail` | Compact stats + title detail |
| `what_to_watch_tonight` | Owned watch suggestions |
| `find_collection_gaps` / `recommend_hidden_gems` | Gap / gem style browses |
| `suggest_purge_candidates_tool` | Purge candidates |
| `analyze_watch_patterns` | Overview + in-progress TV |
| `list_watchlist_pins` | Watchlist snapshot |
| `upcoming_premieres` | Recently added titles |
| `search_tmdb_proxy` | TMDB search when key configured |

MCP does **not** execute *arr writes. Mutating actions stay in the signed-in web UI with confirmation tokens.
