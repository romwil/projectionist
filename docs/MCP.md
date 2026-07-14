# CuratorX MCP

CuratorX exposes a Model Context Protocol server over your indexed Plex library, with **two trust planes** selected by which API key you present.

## Install

```bash
pip install "curatorx[mcp]"
# or in Docker image (1.2+): already included
```

## Modes

| Mode | How selected | Response schema | Tool surface |
|------|--------------|-----------------|--------------|
| **privacy** (default for sharing) | HTTP: `CURATORX_MCP_API_KEY`. Stdio: `CURATORX_MCP_MODE=privacy` (or unset). | Public content — titles/metadata; **no** `rating_key`, file sizes, raw watch timestamps, `in_radarr`/`in_sonarr`, or tokenized Plex thumbs. Optional `watch_state` enum. | Read-only library tools |
| **full** (trusted in-stack) | HTTP: `CURATORX_MCP_FULL_API_KEY`. Stdio: `CURATORX_MCP_MODE=full` **and** distinct full key in env. | Internal fields allowed (`rating_key`, view counts, *arr flags, file size) but **never** live `X-Plex-Token` in URLs. | Read tools **plus** confirm-gated `propose_add_radarr` / `propose_add_sonarr` / `propose_remove_arr` / `confirm_pending_action` |

**Rules**

- Mode comes from the **key** (HTTP) or stdio mode + full-key presence — never from a client “mode” query param.
- Privacy and full keys must **differ**. If they are equal or the full key is empty, full mode is refused.
- If only one key is configured, that key’s mode applies.

## Images (TMDB CDN)

Emitted `poster_url` / `backdrop_url` are allowlisted to `https://image.tmdb.org/t/p/{size}/…` only. Configurable sizes (settings / Advanced later):

- `mcp_tmdb_poster_size` (default `w500`; allow `w185` / `w342` / `w500` / `w780`)
- `mcp_tmdb_backdrop_size` (default `w1280`)

Plex/Fanart thumbs (including any URL containing `X-Plex-Token`) are cleared rather than rewritten.

## Stdio (Cursor / Claude Desktop)

```bash
DATA_DIR=/path/to/config curatorx-mcp
# equivalent: python -m curatorx.mcp
```

Privacy (default):

```json
{
  "mcpServers": {
    "curatorx": {
      "command": "curatorx-mcp",
      "env": {
        "DATA_DIR": "/mnt/user/appdata/curatorx/config",
        "CURATORX_MCP_MODE": "privacy"
      }
    }
  }
}
```

Full (trusted LAN automation only):

```json
{
  "mcpServers": {
    "curatorx-full": {
      "command": "curatorx-mcp",
      "env": {
        "DATA_DIR": "/mnt/user/appdata/curatorx/config",
        "CURATORX_MCP_MODE": "full",
        "CURATORX_MCP_FULL_API_KEY": "generate-a-long-random-secret"
      }
    }
  }
}
```

Repo sample: [`mcp.json`](../mcp.json).

## HTTP transport

Mounts at `/mcp` when at least one of `CURATORX_MCP_API_KEY` / `CURATORX_MCP_FULL_API_KEY` is set.

```bash
# Privacy mode
curl -H "X-CuratorX-MCP-Key: $CURATORX_MCP_API_KEY" \
  http://127.0.0.1:8788/mcp

# Full mode
curl -H "X-CuratorX-MCP-Key: $CURATORX_MCP_FULL_API_KEY" \
  http://127.0.0.1:8788/mcp
```

Without either key, `/mcp` returns **503**. Wrong key → **401**. Logs record `mode=` only — never the key material.

## Tools

### Read (both modes)

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
| `search_tmdb_proxy` | TMDB search when key configured (CDN posters; trimmed fields) |

### Full mode only (*arr — propose → confirm)

| Tool | Purpose |
|------|---------|
| `propose_add_radarr` / `propose_add_sonarr` | Queue add; returns `pending_token` |
| `propose_remove_arr` | Queue remove; returns `pending_token` |
| `confirm_pending_action` | Confirm or cancel a pending token |

Privacy mode callers receive an error if they invoke propose/confirm tools. There is no silent `require_confirmation=false` path.

## See also

- [SECURITY.md](SECURITY.md) — findings **P1–P6** (tokenized posters, rating_key, telemetry, key confusion, member dump, full-mode handling)
- [PRIVACY.md](PRIVACY.md) — household-facing disclosure
