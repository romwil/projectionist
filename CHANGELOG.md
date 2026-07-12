# Changelog

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
