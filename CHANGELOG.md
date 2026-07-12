# Changelog

## [1.0.10] — 2026-07-12

Show the running CuratorX version on the Config screen.

### Added
- Config maintenance footer (and onboarding footer) displays `CuratorX {version}` from `GET /api/health`

## [1.0.9] — 2026-07-12

Hotfix: top-bar agent pulse no longer shows **Agent error** during healthy library sync.

### Fixed
- Agent pulse is driven only by chat/LLM state (`loading` / `chatError`), not by background jobs
- Historical or concurrent failed sync jobs no longer sticky-paint the pulse red while StatusDock shows a successful running sync
- Error clears when a new chat send starts; tooltips report idle / thinking / error with a brief reason

## [1.0.8] — 2026-07-12

Speed up TV episode sync for large libraries (~800 shows).

### Changed
- Fetch show episodes via Plex `allLeaves` first (one request per show), falling back to seasons only when needed
- Parallel episode fetches with a bounded thread pool (reuses `library_enrich_workers`, default 6, clamp 1–16); SQLite writes stay serial
- Batch episode replace (delete + upsert + rollups) in a single commit per show
- Skip re-fetch when stored episode/view counts already match Plex `leafCount` / `viewedLeafCount` (large win on daily resyncs)
- Progress callbacks remain show N of total during the episodes phase

### Notes
- First sync after upgrade still fetches every show; subsequent syncs should skip most unchanged titles
- On ~800 shows, expect roughly worker-count speedup on the network phase (~4–8× with default workers), plus near-instant skips on quiet resyncs

## [1.0.7] — 2026-07-12

Preferred time-of-day scheduling for automatic library sync.

### Added
- Optional `library_sync_hour` (`0–23`, null = interval-only) so daily sync prefers a clock hour in container local time
- Advanced Config → Paths and sync hour selector (“Any / interval only” or `00:00`–`23:00`)
- Unraid template `TZ` variable so preferred hour matches wall-clock time
- Unit tests for scheduler decision logic (`should_run_scheduled_library_sync`)

### Changed
- `library_sync_interval_hours` remains the minimum gap between auto-syncs; with a preferred hour the scheduler waits for that hour (and catch-up if already past it and stale) instead of firing ~N hours after the last sync / shortly after startup

## [1.0.6] — 2026-07-12

Hotfix: keep the sync/job status dock inside the conversation sidebar.

### Fixed
- Mount StatusDock in the sidebar column and constrain its width so sync notifications no longer float across the sidebar/chat divider

## [1.0.5] — 2026-07-12

Hotfix: library sync no longer hangs silently on **Building search facets…** for multi-thousand-title libraries.

### Fixed
- Rebuild search facets and FTS with a single bulk transaction (`executemany`) instead of one commit per facet/FTS row
- Emit indexing-phase progress and periodic INFO logs while facets/FTS rebuild (row/title counts)

### Notes
- On ~5k titles, facet rebuild should finish in seconds to low minutes (not tens of minutes)

## [1.0.4] — 2026-07-12

Hotfix: stop SQLite `database is locked` API failures during large parallel library enrich on Unraid.

### Fixed
- Enable WAL mode, 30s `busy_timeout`, and `synchronous=NORMAL` on every SQLite connection (better concurrent reads under Unraid volume latency; NORMAL trades a small abrupt-power-loss window vs FULL)
- Batch enrich upserts (50 rows per commit) so parallel network enrich no longer commits once per title
- Retry transient lock/busy errors on critical reads/writes (`get_user`, service integrations, upserts, bootstrap)
- `/api/features` no longer writes bootstrap owner on every request — read-first + in-memory cache after owner exists

### Notes
- The `ensure_bootstrap_owner` traceback “recursion” was one-level re-entry (open connection → call with `conn`), not unbounded recursion; still tightened with read-first/caching

## [1.0.3] — 2026-07-12

Faster library sync metadata enrichment via bounded parallel network fetches.

### Changed
- Enrich TMDB/Fanart metadata with a bounded thread pool (default 6 workers, configurable via `library_enrich_workers`); SQLite upserts remain serial on the main thread
- Progress callbacks for the enriching phase still emit periodically with title counts

### Added
- `library_enrich_workers` setting (1–16) in Configuration → Advanced and `settings.json`

## [1.0.2] — 2026-07-12

Hotfix: Unraid containers hung after the startup log and never finished FastAPI lifespan / never served HTTP.

### Fixed
- Deferred library facet index warm-up to a background thread so large libraries cannot block startup
- Hardened durable `jobs_state.json` load (corrupt / oversized / bad entries no longer stall JobManager init)
- Delayed the first scheduled library sync tick until after HTTP can bind
- Added step-by-step INFO startup logs for Unraid log diagnosis

All notable changes to CuratorX are documented in this file.

## [1.0.1] — 2026-07-12

Patch for Community Applications: chat scroll pins the latest user turn while replies grow, plus e2e onboarding isolation when a shared server already completed setup.

### Changed
- Chat scroll follows the latest user turn near the top of the viewport (instead of yanking to absolute bottom) so questions stay visible while the assistant reply / typing indicator grows
- Wizard and setup-banner e2e suites force incomplete onboarding via mocks so they stay reliable against a shared e2e server

### Fixed
- E2E onboarding isolation when `onboarding_complete` cannot be unset by the API

## [1.0.0] — 2026-07-12

Community Applications–ready release: single chat workspace, durable library sync jobs, and Unraid/Docker Hub images.

### Added
- Durable job state under `DATA_DIR/jobs_state.json` — sync jobs survive process/container restarts; interrupted `running`/`queued` jobs are marked failed with a clear recovery message
- In-repo wiki under [`docs/wiki/`](docs/wiki/) (Home, Installation, Unraid, Configuration, Library Sync, Multi-User, Seerr, Troubleshooting, FAQ)
- Canonical [`docs/FAQ.md`](docs/FAQ.md)
- Multi-arch Docker Hub tags: `romwil/curatorx:1.0.0`, `:1.0`, `:latest` (amd64 + arm64)

### Changed
- Status dock prefers live sync phase / counts / `%` over persona flavor text
- `/sync` slash command uses a friendly “Library sync queued…” message (no raw job ids)
- FastAPI startup migrated to lifespan context manager
- Documentation rewritten for the **single workspace** product (removed dual Turnstyle/Immersive and Phase shipping language)

### Fixed
- Restart no longer leaves the UI believing a sync is still running with no recovery path

## [0.1.0] — prior

Initial public redesign: chat workspace, Seerr connector hooks, optional multi-user auth, reviews, and Unraid template.
