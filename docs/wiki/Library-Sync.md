# Library Sync

Library sync indexes your Plex movie and TV libraries into CuratorX’s SQLite database (`curatorx.db`), enriches metadata (TMDB), builds search facets/FTS, and prepares embeddings for recommendations.

## How to start a sync

- **Config page** — maintenance dashboard → **Sync library**
- **Chat** — `/sync` (single-user mode; owner-only when multi-user is on)
- **API** — `POST /api/library/sync`
- **Scheduler** — automatic re-sync on `library_sync_interval_hours` (default 24)

## Progress UI

While a sync runs, the **status dock** (bottom-left of the chat workspace) and the Config **Library sync** card show:

- Friendly phase label (Preparing, Scanning movies, …)
- Count hints when available (`120 of ~500`)
- Weighted overall **percent** (never 100% until complete)

Persona flavor phrases are secondary and never replace live progress.

## Durable jobs (1.0)

Job state is written to `/config/jobs_state.json` (under `DATA_DIR`).

- Status and progress survive container/process restarts
- Any job left `running` or `queued` at startup is marked **failed** with:

  > Interrupted by server restart — start sync again

- API shape stays the same: `GET /api/jobs` includes `progress.phase`, `percent`, `message`, etc.

## Tips

- First sync on a large library can take a while (network + TMDB enrichment). Metadata enrichment runs with a bounded thread pool (`library_enrich_workers`, default 6; SQLite writes stay serial)
- Keep `/config` on persistent storage so the index and job history are not lost
- Use `CURATORX_LOG_LEVEL=DEBUG` to trace sync phases in container logs

See also: [Troubleshooting](Troubleshooting.md) · [../WEB_UI.md](../WEB_UI.md)
