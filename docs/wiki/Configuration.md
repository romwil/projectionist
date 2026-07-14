# Configuration

Settings persist to `{DATA_DIR}/settings.json` (Docker/Unraid: `/config/settings.json`). Environment variables override file values when set.

## Required for a useful install

| Setting | Env | Notes |
|---------|-----|-------|
| Plex URL | `PLEX_URL` | e.g. `http://192.168.1.10:32400` |
| Plex server token | `PLEX_TOKEN` | Library access for sync — not household login |
| Movie / TV sections | `PLEX_MOVIE_SECTION`, `PLEX_TV_SECTION` | Set via wizard dropdowns |
| TMDB API key | `TMDB_API_KEY` | Discovery + enrichment |

## Recommended

| Setting | Env |
|---------|-----|
| Radarr | `RADARR_URL`, `RADARR_API_KEY` |
| Sonarr | `SONARR_URL`, `SONARR_API_KEY` |
| LLM | `LLM_PROVIDER`, `LLM_API_KEY`, `LLM_MODEL`, optional `LLM_BASE_URL` |

Supported LLM presets include OpenAI, Anthropic, Gemini, Groq, Mistral, Together, DeepSeek, OpenRouter, Ollama, and custom OpenAI-compatible endpoints.

## Optional

- Fanart.tv, TVDB, Tautulli
- `library_sync_interval_hours` (minimum hours between auto-syncs, default 24)
- `library_sync_hour` (optional `0–23` preferred local hour; omit/`null` for interval-only). Uses container local time — set `TZ` on Unraid if needed.
- `CURATORX_LOG_LEVEL` (`INFO` default; `DEBUG` for sync tracing)

## Feature flags (off by default)

```json
{
  "features": {
    "multi_user_enabled": false,
    "seerr_enabled": false,
    "plex_collections_enabled": false
  }
}
```

- **multi_user** — **Sign in with Plex** (PIN) gate; owner vs member. See [Multi-User](Multi-User.md).
- **seerr** — household request path. See [Seerr](Seerr.md).
- **plex_collections** — allow curator-managed Plex collections (owner).

Full reference: [../CONFIGURATION.md](../CONFIGURATION.md)
