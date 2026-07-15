# Changelog

## [1.4.0] — 2026-07-15

Documentation alignment, security hardening, and roadmap cleanup.

### Security
- Error response sanitization: all ~20 `HTTPException(detail=str(error))` patterns replaced with `_safe_error_detail()` helper — no internal paths, stack traces, or API keys leak to clients
- Security headers middleware: `Content-Security-Policy`, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy`, `Permissions-Policy` on all responses
- `GET /api/system-config` gated behind `require_role("owner")` (was readable by guests)
- Rate limiting on `POST /api/chat` and `GET /api/chat/stream` (30 req/min per IP)

### Changed
- Roadmap: purged unsupervised clustering ML pipeline, fluid persona slider automation, and visual clustering canvas from Phase 3
- Roadmap: added semantic embeddings over cached plot summaries as deferred item
- Renamed `_migrate_phase3_tables` → `_migrate_context_tables` in database layer (no schema change)
- Product positioning: CuratorX framed as a real-world MCP interface example across README, ABOUT, ARCHITECTURE, MCP.md, FAQ, and wiki
- PRD marked as historical design archive; ARCHITECTURE.md is the canonical roadmap source
- Unraid CA packaging: root `ca_profile.xml` (Community Applications repository profile); removed misnamed container template at `unraid/ca_profile.xml`
- Unraid templates baseline for first CA submission of 1.3.0 (`Changes`, `Requires`, Ollama `ExtraParams`, Fanart/Tautulli/LLM seed envs)

### Added
- 37 new security tests: error sanitization (13), security headers (9), system-config auth (4), rate limiting (11)
- Design philosophy sections in README.md, docs/ABOUT.md, docs/MCP.md with MCP thesis quote

## [1.3.0] — 2026-07-14

Privacy-safe MCP, Admin/Settings split, household management, wide/mobile chat, voice, watchlist sync, and local curated lists.

### Security / Privacy
- Dual-mode MCP: privacy key (`CURATORX_MCP_API_KEY`) vs full key (`CURATORX_MCP_FULL_API_KEY`); keys must differ
- Shared public/internal sanitizers redact Plex tokens and infra IDs for privacy MCP and non-owner library browse
- Public privacy disclosure at `/privacy` (no login) plus [docs/PRIVACY.md](docs/PRIVACY.md)

### Added
- Admin vs Settings shells, preferred conversation name, and in-app About (version from `/api/health`)
- Household user disable/remove and Seerr sync management for owners
- Browser voice mode (mic dictation + optional spoken replies) with Settings toggles
- Wider chat stage on large screens and touch-first mobile chrome (fullscreen `100dvh`, sticky composer)
- Plex Discover watchlist sync and pin-from-recs (encrypted Sign-in-with-Plex account token)
- Local named curated lists (Settings → Lists + agent tools); Plex Lists publish deferred
- Admin → Advanced: generate/rotate dual MCP keys, TMDB poster/backdrop CDN sizes

### Changed
- Docker / Unraid tags move to `:1.3` / `:1.3.0`
- Unraid templates expose both MCP env vars (or generate keys in Admin → Advanced)
- Operator docs baselined on 1.3.0 (install/config as the normal path)

## [1.2.0] — 2026-07-14

Pre-CA security hardening, multi-user API enforcement, MCP product surface, and Unraid CA packaging freeze.

### Security
- Global API auth middleware when multi-user is enabled (allowlist: health/features/auth/webhooks)
- Owner-only settings, setup tests, library sync mutate, persona/lens writes
- Session secret auto-bootstrap under DATA_DIR; refuse public default for multi-user
- Plex PIN nonce cookie binding + per-IP rate limits; Secure cookies behind HTTPS proxies
- Setup-test SSRF guards (link-local/metadata) + host-matched secret attachment
- Webhooks reject empty secrets; Seerr requests always require confirmation tokens
- Chat threads, pending actions, reviews, and preferences scoped by `user_id`
- Guest role blocked from request / *arr mutating agent tools

### Added
- Expanded MCP library tools + `docs/MCP.md` + sample `mcp.json`
- Optional HTTP MCP at `/mcp` gated by `CURATORX_MCP_API_KEY`
- Unraid `ca_profile.xml` + advanced env vars (`CURATORX_SESSION_SECRET`, webhook, MCP)
- `tests/test_api_authz.py`

### Changed
- Docker image installs `[web,mcp]`; tags move to `:1.2` / `:1.2.0`
- Architecture + Multi-User wiki document the partitioning matrix
- `docs/SECURITY.md` findings S1–S2, S4–S10, S12 marked Mitigated where code landed

## [1.1.6] — 2026-07-13

Unraid CA application icon plus friendlier Config / first-run copy. Preserves 1.1.5 **Sign in with Plex** (PIN) as the household login path; Config now clearly separates the Plex *server* token (library sync) from user PIN sign-in.

### Added
- Community Applications icon assets: `unraid/curatorx-icon.png` (256) and `unraid/curatorx-icon-512.png` (512)
- `<Icon>` on Unraid templates pointing at the GitHub raw 256 PNG
- Icon specs section in [docs/wiki/Unraid.md](docs/wiki/Unraid.md)

### Changed
- Config / onboarding labels and help text in plain language (no raw `plex_token` keys, demoted jargon)
- Distinguishes **Plex server token** (libraries) from household **Sign in with Plex** PIN login; never directs users to plex.tv/account for a token
- Wizard steps renamed: Name → Connections → Libraries; Settings replaces “maintenance dashboard” wording

## [1.1.5] — 2026-07-13

Overseerr-style **Sign in with Plex** for multi-user login (plex.tv PIN / link flow).

### Added
- `POST /api/auth/plex/pin` and `GET /api/auth/plex/pin/{id}` — create and poll a plex.tv PIN, then set the CuratorX session cookie
- Login page primary path opens plex.tv auth; advanced token paste remains as a fallback

### Fixed
- Login copy no longer tells users to copy a token from plex.tv/account (Plex removed that UI for most accounts)

### Changed
- Docs / Config labels: “Plex login” instead of “Plex token login”

## [1.1.4] — 2026-07-12

Pin turnstyle recommendation cards to the exact recommended work when year or `tmdb_id` is known.

### Fixed
- `search_tmdb` no longer expands one specific recommendation (e.g. **Mandy (2018)** / `tmdb_id` 460885) into every same-name TMDB hit in turnstyle cards
- Prefer exact `tmdb_id` lookup; with `title`+`year`, filter to that year only

### Changed
- `search_tmdb` accepts optional `tmdb_id` (title optional when set); system prompt asks for `tmdb_id` or title+year when recommending a single title

## [1.1.3] — 2026-07-12

Chat composer: **Enter** sends the message; a trailing send button mirrors that action.

### Added
- Enter-to-send in the chat composer (Shift+Enter still inserts a newline)
- Trailing send button next to the composer

## [1.1.2] — 2026-07-12

Fix `/stats` showing **Last sync: Invalid Date**.

### Fixed
- `/stats` Library stats parses `last_sync` JSON (`timestamp` Unix seconds) instead of treating the whole blob as an epoch
- Missing or malformed last sync shows **never** / **Unknown**, never Invalid Date

## [1.1.1] — 2026-07-12

Resume interrupted library syncs without redoing finished work, and skip unchanged recommendation embeddings.

### Added
- Phase checkpoints after movies / TV / enrich / index / episodes (valid ≤72h) so a restart mid-sync resumes from the next phase
- Embedding content-hash skip: unchanged titles are not re-embedded on finishing

### Fixed
- Restarting during **Building recommendations…** no longer forces a full rescan/enrich when earlier phases already completed
- Empty-library first sync no longer double-fetches Plex movie/TV lists before enrich

## [1.1.0] — 2026-07-12

Cinema-dark UI/UX refactor: Fraunces + DM Sans, amber accent (no violet gradients), brand-first top bar, wider sidebar with in-rail status dock, poster-forward title cards, and Config/Login aligned to the same visual system.

## [1.0.13] — 2026-07-12

Track confirmed adds, simplify batch rating, and accept half-star reviews.

### Fixed
- Confirmed Radarr/Sonarr/Seerr adds are remembered (`arr_queued_titles`) so gap/recommend tools and the system prompt no longer re-pitch the same titles
- Half-star ratings (e.g. 4.5) save and sync to Plex (`stars × 2`) without asking the user to round

### Added
- `/rate` with no title shows a compact strip of the last ~10 viewed & unrated titles
- `GET /api/reviews/to-rate` and agent `suggest_titles_to_rate` surface rateable cards (batch UI) instead of one-by-one chat grilling

### Changed
- Review prompts and star pickers support 0.5 increments; persona guidance prefers batch cards for “rate recently watched”

## [1.0.12] — 2026-07-12

Make “Why this?” useful and keep library sync finishing visible.

### Fixed
- Title card **Why this?** no longer shows internal pipeline labels like **TMDB title match**; prefers curator rationale from `search_tmdb(reason=…)` / `set_recommendation_reasons`
- Library sync **Finishing · Building recommendations…** reports N of M title progress (and advances the 90–99% band) instead of freezing at 90% with no logs

### Changed
- Embedding rebuild batches provider API calls and SQLite writes for faster finishing on large libraries

## [1.0.11] — 2026-07-12

Stop duplicating bulk “Confirm all” between chat and StatusDock.

### Fixed
- In-chat / turnstyle **Confirm all N to Radarr|Sonarr|Seerr** runs the bulk add immediately instead of enqueueing a second StatusDock “Add all N titles?” prompt
- Agent pending-token bulk confirms stay in chat when title cards already host the Confirm all button; dock still shows token confirm when there is no in-message host
- StatusDock remains for single-title drag/add confirms, running jobs, and add progress

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
