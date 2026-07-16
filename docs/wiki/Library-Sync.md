# Library Sync

Library sync indexes your Plex movie and TV libraries into CuratorX’s SQLite database (`curatorx.db`), enriches metadata (TMDB), builds search facets/FTS, upserts structured credits, and prepares embeddings for recommendations.

## Sync vs idle trickle

| Path | When | Responsibility |
|------|------|----------------|
| **Library sync** | Manual `/sync`, API, or `library_sync_*` schedule | Plex scan, durable phases, bounded TMDB enrich, facets/FTS, honest `added_at` / ISO dates when TMDB provides them |
| **Idle scheduler** | After idle (no chat) | Fill gaps: `metadata_enrichment`, `semantic_embeddings`, `plot_neighbors`, motifs/themes, `title_relations_refresh`, optional LLM logline |

Sync stays interactive; heavy similarity graphs and embedding backfills trickle in the background so Unraid/NAS CPUs stay usable. Empty Explore neighbor rails mean the idle cache has not finished — run sync, then leave the container idle (or wait for the next scheduler cycle).

**Provenance:** CuratorX never invents `release_date` / `first_air_date` from `year` alone. Recent Releases and calendar On This Day stay empty (with an explanatory note) until real ISO dates are enriched.

## How to start a sync

- **Config page** — Settings → **Sync library**
- **Chat** — `/sync` (single-user mode; owner-only when multi-user is on)
- **API** — `POST /api/library/sync`
- **Scheduler** — automatic re-sync using `library_sync_interval_hours` (minimum gap, default 24) and optional `library_sync_hour` (`0–23` preferred local hour; unset = interval-only)

## Schedule behavior

| Setting | Role |
|---------|------|
| `library_sync_interval_hours` | Minimum hours between automatic syncs (1–168) |
| `library_sync_hour` | When set, wait for that clock hour each day (container local TZ) instead of firing ~N hours after the last sync / shortly after startup |

Notes:

- With a preferred hour, startup does **not** sync after the initial delay unless the library is already stale beyond the interval **and** local time is at/past that hour (catch-up).
- A recent sync still blocks a duplicate run (interval gate), including after container restarts.
- Set the container `TZ` environment variable (e.g. `America/New_York`) so “3am” matches your wall clock on Unraid.

## Progress UI

While a sync runs, the **status dock** (bottom of the conversation sidebar) and the Config **Library sync** card show:

- Friendly phase label (Preparing, Scanning movies, Finishing · Building recommendations…, …)
- Count hints when available (`120 of ~500`)
- Weighted overall **percent** (never 100% until complete)

Persona flavor phrases are secondary and never replace live progress.

## Durable jobs & phase checkpoints

Job state is written to `/config/jobs_state.json` (under `DATA_DIR`).

- Status and progress survive container/process restarts
- Any job left `running` or `queued` at startup is marked **failed** with:

  > Interrupted by server restart — start sync again

- Starting sync again resumes from the last completed **phase checkpoint** when still valid (≤72h): movies → TV → enrich → index → episodes → finishing. Finished phases are skipped.
- Embedding rebuilds skip unchanged titles (content-hash) when finishing.
- API shape stays the same: `GET /api/jobs` includes `progress.phase`, `percent`, `message`, etc.

## Tips

- First sync on a large library can take a while (network + TMDB enrichment). Metadata enrichment and TV episode fetches run with a bounded thread pool (`library_enrich_workers`, default 6; SQLite writes stay serial). Unchanged shows (matching Plex `leafCount` / `viewedLeafCount`) skip episode re-fetch on later syncs.
- After the first full sync, leave the app idle so embeddings → neighbors → relations trickle; Explore “More Like This” and Plot Lab fill in as those tasks complete
- Keep `/config` on persistent storage so the index, checkpoints, and job history are not lost
- Use `CURATORX_LOG_LEVEL=DEBUG` to trace sync phases in container logs
- Inspect idle tasks under Admin → scheduled tasks (quarantine reset if a task fails repeatedly)

See also: [Troubleshooting](Troubleshooting.md) · [../WEB_UI.md](../WEB_UI.md) · [../ARCHITECTURE.md](../ARCHITECTURE.md#metadata-trickle-sync-vs-idle)
