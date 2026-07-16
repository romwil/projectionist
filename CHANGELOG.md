# Changelog

## [1.7.12] — 2026-07-15

### Fixed
- Owner dashboard: Rating Coverage now correctly counts watched titles with reviews (was always 0%)
- Owner dashboard: Taste Profile ratings display as stars out of 5 instead of /10 scale
- Context label (⧉) now updates per-thread instead of staying stuck on one thread's topic
- ConfigPage Promise.all error handling prevents blank persona page

### Added
- Owner dashboard: Purge Candidates now support multi-select with checkboxes, Delete Selected and Dismiss Selected actions with confirmation dialog
- Owner dashboard: TV Completion card expanded — shows 10 shows with larger progress bars and episode counts
- Watchlist pins badge in top bar now functional — click toggles watchlist panel, hover shows tooltip
- Privacy and About links moved to a subtle page footer on all layouts
- User chat messages now have a warm-tinted background for better readability

### Changed
- Chat conversation area expanded to ~80% width for better use of screen space
- Removed About link from top navigation bar (accessible via footer and Settings)

## [1.7.11] — 2026-07-15

### Fixed
- Owner dashboard: Decade Distribution, Top Genres, Countries, Languages, and Runtime Distribution charts now populate correctly (frontend was reading `groups`/`data` instead of backend's `buckets`)
- Owner dashboard: Purge Candidates table now shows structured data with file size, purge score, and reasons
- Owner dashboard: Engagement Streak, TV Completion, and Reviews timeline panels now map correct field names from backend responses
- Runtime Distribution chart shows human-readable labels instead of raw bucket names

## [1.7.10] — 2026-07-15

### Fixed
- Docker images now include build timestamp in file content (not just labels), forcing Docker daemons to recognize image changes on Force Update
- Startup log now shows build info for easier version verification

## [1.7.9] — 2026-07-15

### Added
- Shared test infrastructure (`tests/conftest.py`) with reusable fixtures: `fresh_db`, `seed_library`, `make_tool_registry`, `execute_tool`, and 9 dataset constants
- 43 P0 value-based validation tests for highest-risk tools: `search_library`, `query_library`, `recommend_hidden_gems`, `suggest_purge_candidates`, `what_to_watch_tonight`
- 68 P1/P2 value-based validation tests covering `explore_genre`, `summarize_tv_progress`, `query_tv_episodes`, `curate_watchlist`, `critique_watchlist`, `upcoming_premieres`, `suggest_titles_to_rate`, `get_user_reviews`, `query_watchlist`, `get_todays_anniversaries`, and more
- 82 database query validation tests for `telemetry_summary`, `export_training_corpus`, `get_chat_thread`, `preference_facts`, `semantic_search`, and other complex SQL methods
- Coverage infrastructure with `pytest-cov` integration and CI reporting
- `TESTING.md` documentation on the value-based testing pattern

### Changed
- Migrated duplicated `_seed_library` and `_make_db` helpers to shared `conftest.py` fixtures
- Test coverage from 1.4% to 76%+

## [1.7.8] — 2026-07-15

### Fixed
- "New reply" chip now properly dismisses when scrolled to bottom — fixed streaming race condition
- Turnstyle preview buttons ("Confirm all" + "Expand") now side-by-side with consistent outlined styling
- Library snapshot hidden gems SQL simplified — was using broken self-joining subquery
- Collection gaps keyword resolution — text keywords now resolve to TMDB IDs before API call

### Added
- 33 value-based agent tool validation tests covering gap detection, anniversaries, library snapshot, tonight picks, double feature, quick pick, watch patterns, and edge cases

## [1.7.7] — 2026-07-15

### Fixed
- Docker image now embeds version as OCI label via build arg — ensures each release produces a distinct image manifest, eliminating stale layer cache issues on Unraid "Force Update"
- Dockerfile version label was hardcoded at 1.7.3; now dynamically set from release script

## [1.7.6] — 2026-07-15

### Fixed
- Turnstyle viewport now shows the correct title when TMDB returns multiple same-year results — exact title match is preferred over fuzzy hits (e.g., "Munich" no longer shows "Munich Mambo")
- SSE streaming no longer concatenates intermediate LLM reasoning into the final message — only the last round's text is persisted; intermediate "thinking" text streams as live tokens but doesn't appear in chat history

## [1.7.5] — 2026-07-15

### Fixed
- Persona selector now appears on upgraded installs — builtin persona templates are re-seeded on every startup via `ensure_seed_data()`, fixing empty `persona_templates` table after upgrade from pre-1.5.0

## [1.7.4] — 2026-07-15

Persona audit: wire selector, complete slider set, sanitize error responses.

### Fixed
- PersonaSelector now wired into chat composer — per-conversation persona switching, custom creation, and set-as-default all functional
- PersonaSection (Admin > Persona) now shows all 7 personality sliders (was missing Depth, Obscurity, Verbosity, Formality)
- Sanitized 2 remaining raw `str(error)` responses in persona template endpoints
- Synced templates/curatorx.xml with unraid source for CA auto-update detection

## [1.7.3] — 2026-07-15

Fix Docker startup failure on existing installs with root-owned `/config` volumes.

### Fixed
- Docker container startup failure on existing installs — entrypoint now auto-fixes `/config` ownership before dropping to non-root user
- Compatible with both fresh installs and upgrades from root-based containers

## [1.7.2] — 2026-07-15

Heartbeat deadline bug fix, test suite isolation, zero failures.

### Fixed
- Scheduler heartbeat mechanism now actually resets the timeout deadline — previously `asyncio.wait_for()` ignored heartbeat timestamps entirely
- Test suite environment isolation: patched `PLEX_TOKEN`, `MOVIES_ROOT`, `TV_ROOT`, `RADARR_ROOT_FOLDER`, `SONARR_ROOT_FOLDER` leakage from developer `.env` into test assertions
- Added missing `python-multipart` dependency for webhook multipart form parsing

### Changed
- Heartbeat timeout uses `asyncio.shield()` + deadline loop instead of fixed `asyncio.wait_for()`
- Full test suite now passes with zero failures (698 Python + 102 frontend)

## [1.7.1] — 2026-07-15

Scheduler hardening, data retention, and trickle embedding ingestion.

### Added
- Scheduler circuit breaker: per-task timeout (default 5min), consecutive failure tracking, automatic quarantine after 3 failures with 1-hour cooldown
- Heartbeat mechanism for long-running tasks to signal liveness and reset timeout window
- Admin quarantine reset endpoint (`POST /api/admin/scheduled-tasks/{name}/reset`)
- Data retention pruning: telemetry (90d), interaction telemetry (90d), daily anniversaries (30d) with automatic VACUUM
- `data_retention` scheduled task registered as OOTB background task
- Trickle ingestion for semantic embeddings: MAX_ITEMS_PER_CYCLE=50 cap with cooperative yielding
- 38 new tests for circuit breaker, data retention, and embedding trickle patterns

### Changed
- Scheduler admin API (`GET /api/admin/scheduled-tasks`) now includes quarantine status per task
- Stale task selection skips quarantined tasks automatically
- Semantic embeddings task returns `cycle_limit` status when capped, remaining items picked up next cycle

### Documentation
- ARCHITECTURE.md: new "Agent tools vs. background scheduler" section with boundary rules and examples
- ARCHITECTURE.md: new "SQLite concurrency model" section explaining WAL mode, busy timeout, and trickle ingestion

## [1.7.0] — 2026-07-15

Non-root Docker, true SSE streaming, multi-method auth, and telemetry ingestion.

### Added
- Non-root Docker container user (security finding S13 mitigated) — UID/GID 1000
- True token-by-token SSE streaming for LLM chat responses (OpenAI + Anthropic providers)
- Local-password authentication (PBKDF2-HMAC-SHA256, owner-only registration)
- OIDC authentication for homelab identity providers (Authelia, Authentik, Keycloak)
- Multi-method login page — dynamically shows Plex, local, and/or OIDC based on configuration
- Telemetry ingestion module — non-blocking event capture for chat, feedback, preferences, reviews, playback, and tool invocations
- Admin telemetry API (`/api/admin/telemetry/summary`, `/api/admin/telemetry/events`)
- 48 new tests across SSE streaming, local auth, OIDC auth, and telemetry

### Changed
- Anthropic provider streams natively instead of buffering + simulating chunks
- SSE endpoint emits structured `token`, `tool_call`, `done`, and `error` events
- Frontend chat renders tokens incrementally as they arrive from the LLM
- Features API now returns `auth_methods` array and `oidc_provider_name`

### Security
- Container runs as non-root user `curatorx` (S13)
- OIDC state parameter prevents CSRF on authorization flow
- Local passwords hashed with PBKDF2-HMAC-SHA256 (600k iterations, constant-time verify)

## [1.6.0] — 2026-07-15

Owner dashboard, background idle task scheduler, and 5 chat delight features.

### Added
- Owner Dashboard at `/admin/dashboard`: library composition charts (decade, genre, runtime, country/language), health gauges (unwatched %, stale adds, rating coverage), storage intelligence (sortable purge table), taste profile timeline — all pure SVG/CSS, no charting library
- Background idle task scheduler (`curatorx/scheduler/`): asyncio-based, idle-detection (15 min default), cooperative interruption, SQLite-backed state, status dock integration
- 6 OOTB scheduled tasks: semantic embedding generation (24h), taste profile refresh (6h), library health metrics (6h), anniversary scanner (24h), recommendation pre-warming (12h), collection gap analysis (weekly)
- Admin API for scheduled tasks: `GET/PUT /api/admin/scheduled-tasks`, `POST .../run`
- "On This Day" anniversary prompts: `OnThisDayCard` above welcome panel + `GET /api/library/anniversaries` endpoint
- Post-sync "Library at a Glance" card: one-time summary after first sync with genre highlights, decade range, hidden gems count
- Night Owl time-aware suggestions: system prompt injects runtime caps after 9 PM, `get_tonight_picks` agent tool
- Double Feature pairing: `suggest_double_feature` agent tool + `DoubleFeatureCard` component with amber-glow bridge connector
- Quick-Pick Roulette: "Surprise me" dice button in composer + `QuickPickCard` reveal component + `GET /api/library/quick-pick` endpoint
- 4 reusable SVG chart components: `BarChart`, `DonutChart`, `Gauge`, `ProgressBar`
- Runtime badge emphasis on TitleCard for short films (<100 min)

### Fixed
- Genre filter in `quick_pick_roulette` and `/api/library/quick-pick`: comma-separated genres now match ANY (OR) instead of ALL (AND)

### Changed
- Chat endpoints (`POST /api/chat`, `GET /api/chat/stream`) record activity for idle scheduler
- Scheduler starts in FastAPI lifespan context, stops gracefully on shutdown

## [1.5.0] — 2026-07-15

Per-conversation persona selection, expanded personality sliders, login cleanup, test coverage infrastructure.

### Added
- Per-conversation persona system: `persona_templates` table with 5 built-in presets (Classic Curator, Blunt Archivist, Enthusiastic Scout, Academic Critic, Night Owl Host) plus owner-shared and user-private custom personas
- 4 new personality sliders: Depth (quick picks↔deep dives), Obscurity (mainstream↔arthouse), Verbosity (concise↔detailed), Formality (chatty↔structured) — total 7 dimensions
- Composer persona selector dropdown with create/edit modal and "Show Advanced" toggle for custom system prompts
- Per-conversation persona indicator in thread sidebar
- 404 catch-all route with "Page not found" page
- Custom `react-markdown` link renderer for privacy page — relative `.md` links rewrite to GitHub docs URLs
- `tests/test_session_tokens.py` (12 tests) and `tests/test_crypto.py` (15 tests) for security-critical modules
- `tests/test_persona_templates.py` and `tests/test_persona_api.py` (37 tests) for persona system
- Coverage tooling: `.coveragerc` for Python, `c8` + `.c8rc.json` for frontend
- Frontend unit tests wired into CI pipeline and top-level `npm test`

### Changed
- Persona sliders expanded from 3 to 7 dimensions; `build_system_prompt()` reads from conversation's persona template
- Login page decluttered: removed Admin link from footer, tightened card spacing
- `KeyboardHelpModal` privacy link changed from raw `<a>` to React Router `<Link>`

### Fixed
- Privacy page: relative markdown links (`SECURITY.md`, `MCP.md`, `wiki/*.md`) no longer navigate to dead SPA routes

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
