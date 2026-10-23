# Projectionist MCP

Projectionist exposes a Model Context Protocol server over your indexed Plex library, with **two trust planes** selected by which API key you present.

Repository memory is shared, sanitized media knowledge and may be added to the
read-only MCP surface. Private user memory, account exports, and user-memory
events are never exposed through either MCP trust plane.

## Why MCP for media curation?

A personal Plex library is a uniquely well-structured local dataset: thousands of titles with rich metadata (genres, ratings, cast, watch state, file sizes) already indexed in SQLite. MCP lets an LLM reach into that index with surgical precision — one tool call per conversational turn — without ever bulk-exporting your collection or exposing your Plex token to a remote service.

> "The LLM gets to act like a natural language surgeon on a highly optimized, predictable local dataset. It's incredibly fast, it's cheap, and it keeps your Plex token and personal collection server info locked down."

Projectionist demonstrates this pattern as a **production-quality, privacy-first MCP interface** over local structured + unstructured data:

- **Fast** — tool calls hit a pre-built SQLite index and NumPy vectors; sub-second responses even on modest homelab hardware.
- **Cheap** — the LLM receives only the minimal context slice for each turn, keeping token costs low.
- **Private** — credentials, watch history, and internal fields stay on your hardware. Dual keys let you share a read-only library view externally while keeping *arr mutations and internal fields behind a separate trust boundary.

---

## Install

```bash
pip install "projectionist[mcp]"
# or in the Docker image: already included
```

## Modes

| Mode | How selected | Response schema | Tool surface |
|------|--------------|-----------------|--------------|
| **privacy** (default for sharing) | HTTP: `PROJECTIONIST_MCP_API_KEY`. Stdio: `PROJECTIONIST_MCP_MODE=privacy` (or unset). | Public content — titles/metadata; **no** `rating_key`, file sizes, raw watch timestamps, `in_radarr`/`in_sonarr`, or tokenized Plex thumbs. Optional `watch_state` enum. | Read-only library tools |
| **full** (trusted in-stack) | HTTP: `PROJECTIONIST_MCP_FULL_API_KEY`. Stdio: `PROJECTIONIST_MCP_MODE=full` **and** distinct full key in env. | Internal fields allowed (`rating_key`, view counts, *arr flags, file size) but **never** live `X-Plex-Token` in URLs. | Read tools **plus** confirm-gated `propose_add_radarr` / `propose_add_sonarr` / `propose_remove_arr` / `confirm_pending_action` |

**Rules**

- Mode comes from the **key** (HTTP) or stdio mode + full-key presence — never from a client “mode” query param.
- Privacy and full keys must **differ**. If they are equal or the full key is empty, full mode is refused.
- If only one key is configured, that key’s mode applies.

## Images (TMDB CDN)

Emitted `poster_url` / `backdrop_url` are allowlisted to `https://image.tmdb.org/t/p/{size}/…` only. Defaults are usually fine; power users can set sizes via `settings.json` or `PUT /api/settings` (not shown on Admin → Advanced):

- `mcp_tmdb_poster_size` (default `w500`; allow `w185` / `w342` / `w500` / `w780`)
- `mcp_tmdb_backdrop_size` (default `w1280`; allow `w300` / `w780` / `w1280` / `original`)

Plex/Fanart thumbs (including any URL containing `X-Plex-Token`) are cleared rather than rewritten.

## Admin → Advanced (operators)

Owners can **generate / regenerate** privacy and full MCP keys, see a last-4 hint (never the full secret on list GETs), and copy a newly generated key once. Keys persist to `settings.json` (file overrides empty-or-absent env after rotate). Unraid templates also expose both env vars.

Use `PROJECTIONIST_*` only. In-app `CURATORX_*` reads closed in **1.34.0**. Compose/Unraid templates may still map a leftover `CURATORX_*` name into `PROJECTIONIST_*` at the shell layer; do not rely on that for new installs. See the keep-vs-sunset list in [Phase 6 spec](superpowers/specs/2026-09-24-delight-phase-6.md#curatorx-keep-vs-sunset-do-not-yank-aliases-in-1363).

| Env / setting | Mode |
|---------------|------|
| `PROJECTIONIST_MCP_API_KEY` / `mcp_api_key` | Privacy |
| `PROJECTIONIST_MCP_FULL_API_KEY` / `mcp_full_api_key` | Full (must differ) |

## Stdio (Cursor / Claude Desktop)

```bash
DATA_DIR=/path/to/config projectionist-mcp
# equivalent: python -m projectionist.mcp
```

Privacy (default):

```json
{
  "mcpServers": {
    "projectionist": {
      "command": "projectionist-mcp",
      "env": {
        "DATA_DIR": "/mnt/user/appdata/curatorx/config",
        "PROJECTIONIST_MCP_MODE": "privacy"
      }
    }
  }
}
```

Full (trusted LAN automation only):

```json
{
  "mcpServers": {
    "projectionist-full": {
      "command": "projectionist-mcp",
      "env": {
        "DATA_DIR": "/mnt/user/appdata/curatorx/config",
        "PROJECTIONIST_MCP_MODE": "full",
        "PROJECTIONIST_MCP_FULL_API_KEY": "generate-a-long-random-secret"
      }
    }
  }
}
```

Repo sample: [`mcp.json`](../mcp.json).

## HTTP transport

Mounts at `/mcp` when at least one of `PROJECTIONIST_MCP_API_KEY` / `PROJECTIONIST_MCP_FULL_API_KEY` is set.

```bash
# Privacy mode
curl -H "X-Projectionist-MCP-Key: $PROJECTIONIST_MCP_API_KEY" \
  http://127.0.0.1:8788/mcp

# Full mode
curl -H "X-Projectionist-MCP-Key: $PROJECTIONIST_MCP_FULL_API_KEY" \
  http://127.0.0.1:8788/mcp
```

Without either key, `/mcp` returns **503**. Wrong key → **401**. Logs record `mode=` only — never the key material.

## Tools

### Read (both modes)

| Tool | Purpose |
|------|---------|
| `library_query` / `library_aggregate` / facets / TV helpers | Browse owned inventory |
| `library_overview_tool` / `library_title_detail` | Compact stats + title detail |
| `sample_owned_library` | Owned inventory sample (overview + owned titles). `find_collection_gaps` is a one-release alias of this — not TMDB missing-title discover |
| `discover_missing_titles` | Real TMDB collection gaps (title, year, media_type, poster CDN, `in_library=false`); shares agent gap filters (`genres`, `without_genres`, `tv_type`, years, query) |
| `recommend_hidden_gems` | Lower-view owned “hidden gem” browses (full mode) |
| `suggest_purge_candidates_tool` | Purge candidates |
| `analyze_watch_patterns` | Overview + in-progress TV |
| `list_watchlist_pins` | Watchlist snapshot |
| `upcoming_premieres` | Recently added titles (last 30 days — not theatrical premieres) |
| `search_tmdb_proxy` | TMDB search when key configured (CDN posters; trimmed fields) |
| `list_relations` | Named one-hop `title_relations` (collection / crew / plot_link). Empty = cache not ready |
| `walk_relations` | Shallow BFS (depth ≤ 2) over the same graph |
| `titles_by_person` | In-library filmography with a named credit explanation |
| `find_similar_titles` | Explainable plot neighbors only (`explainable_only=True`) |

The in-app agent’s `research_title` service combines configured TMDB details
with the keyless Wikipedia MediaWiki API and optional OMDb/TVDB sources. It
returns provenance and does not expose Plex paths or credentials. A future
read-only MCP `research_title` tool should wrap this same sanitized service;
the in-process agent surface ships first so external-provider behavior and
privacy boundaries remain centrally tested.

Chat agent tools share the same graph functions. Prefer them (or the MCP wraps above) when the user asks “more like X”, “same director”, or “franchise siblings”. Each peer carries an XC-01 `explanation` or is omitted. Empty `{items: [], note}` means the Named kinship cache is not ready — not that nothing is related. Cosine-only rows stay out. Privacy mode never emits `rating_key`. See [ARCHITECTURE.md](ARCHITECTURE.md#agent-tools-vs-background-scheduler).

| Agent / MCP tool | Purpose | Cache / source |
|------------------|---------|----------------|
| `find_similar_titles` | Similar or surprising **explainable** neighbors | `item_neighbors` (`explainable_only=True`) |
| `list_relations` | One-hop `title_relations` edges | collection / neighbor / shared_crew |
| `walk_relations` | Shallow BFS (depth ≤ 2) over relations | same graph |
| `titles_by_person` | In-library filmography for a person | `people` + `credits` |
| `get_facet_catalog` | Top facet values including **`motif`** and **`theme`** | `library_facets` (in-app) |
| `get_for_you` | Explore For you + honest empty note (in-app) | `list_linked_unwatched` |

### Full mode only (tonight + *arr)

| Tool | Purpose |
|------|---------|
| `what_to_watch_tonight` | Same For you path as Explore (`list_linked_unwatched`): `{mode, empty, note, items[].explanation, continue[]}`. Privacy callers get the existing full-mode error — never a TMDB tonight. |
| `propose_add_radarr` / `propose_add_sonarr` | Queue add; returns `pending_token` |
| `propose_remove_arr` | Queue remove; returns `pending_token` |
| `confirm_pending_action` | Cancel a pending token, or confirm/execute it **when the key is scoped for active curation** |

Privacy mode callers receive an error if they invoke tonight or propose/confirm tools. There is no silent `require_confirmation=false` path.

**Active-curation scope (H3).** A full key can always *propose* and *cancel*. Whether it may *confirm/execute* its own proposals is a scope bound to key issuance: set `mcp_full_confirm_enabled` (Admin → rotate the full key with the active-curation scope) or `PROJECTIONIST_MCP_FULL_CONFIRM=1` for stdio / Unraid CA. Without the scope, `confirm_pending_action` returns `requires_human_confirmation` and the pending token survives so a human can confirm it in the web UI status dock (or `POST /api/actions/confirm`). This lets you issue read+propose keys for untrusted models and reserve self-confirming keys for trusted in-stack automation.

## See also

- [SECURITY.md](SECURITY.md) — findings **P1–P6** (tokenized posters, rating_key, telemetry, key confusion, member dump, full-mode handling)
- [PRIVACY.md](PRIVACY.md) — household-facing disclosure
