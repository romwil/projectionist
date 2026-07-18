# Changelog

## [Unreleased]

## [1.8.16] — 2026-07-18

### Fixed
- Deep-linked Explore facet walls now use the shared browse controls, Poster/List results, current-page CSV export, and the same card action grip as full Tag, Explore section, Watchlist, and collection views.

### Documentation
- Help now calls out deep-linked Explore facets as full browse walls; only short contextual rails and credit-annotated person filmography remain intentional toolbar exceptions.

## [1.8.15] — 2026-07-18

Browse actions and Surprise Me now follow the same compact recommendation language across CuratorX.

### Changed
- Watchlist and named list/playlist walls now offer the shared current-page CSV menu alongside Poster/List, sort, filters, and columns. Household recommendation actions are available there as on other browse walls.
- The shared ⋮ action grip uses clear watchlist wording and adds **Recommend like this in chat**, which seeds Chat with the selected title, year, and media type for a related-picks conversation.
- **Surprise Me** now appends one compact recommendation card followed immediately by its rationale in the chat transcript; it no longer renders a separate full-bleed card near the composer.

### Documentation
- Help explains why short Explore rails, Plot Lab’s neighbor strip, and credit-annotated person filmographies intentionally remain context-dense exceptions rather than duplicate browse toolbars.

## [1.8.14] — 2026-07-18

Explore feed browsing now uses the same visible controls as the rest of CuratorX.

### Fixed
- **Recently Added** and **Recent Releases** now include Poster/List, sort direction, type/watch/year/genre filters, columns, and a clearly available CSV export. Feed CSV exports only the current loaded page so it does not imply an unrestricted library export.
- List mode preserves feed selection, pinning, and owner delete actions; control menus are no longer clipped by the Explore toolbar.

## [1.8.13] — 2026-07-18

Shared media browsing, local collections, and safe owner-reviewed media repair.

### Added
- **Browse controls** support explicit `sort_dir`, up to 100 results, poster/list pivots, and a privacy-filtered CSV export of the active library query.
- **Curated lists** carry a `list_kind` (`list` or `playlist`) and share the poster/list-row action grip with watchlist collection actions.
- **Media issue queue**: household members can report media problems; owners can review, resolve, and run logged *arr repair playbooks. Auto-repair remains off until an owner allowlists issue codes.

### Fixed
- Frontend browse contract now uses backend `vote_average` / `last_viewed_at` fields and exports only backend-allowlisted columns; collection membership sends `tvdb_id` and optional library item identity.
- Compact chat TitleCards now expose the same role-aware action grip as browse posters.

### Documentation
- Expanded in-app Help and operator guides for browse/export intent, lists vs. playlists vs. watchlist, the shared grip, issue reporting, owner queue workflow, and conservative repair limits.

## [1.8.12] — 2026-07-18

AppNav hamburger on every core shell (chat, browse, Settings, Admin, Privacy); chat footer links move into the drawer.

### Changed
- **AppNav hamburger** is always reachable on chat (desktop + mobile), watchlist/person/title browse shells, Settings, Admin, and Privacy — same drawer as Explore/Help/About. Chat no longer shows the Help · Privacy · About footer trio (those live in AppNav). Privacy joins Help/About in the menu and uses AppShell chrome.

## [1.8.11] — 2026-07-18

Watched poster badges, Revisit These rail, and durable Unraid update hygiene after Force Update 0 B no-ops.

### Added
- **Watched posters**: Plex-like upper-right watch overlays on every poster surface (`WatchProgressBadge`) — checkmark when fully watched, distinct in-progress glyph for movie playhead progress or partially watched shows.
- **Revisit These** Explore rail: random sample of up to 20 partially watched TV series with no activity for 60+ days (`GET /api/library/feeds/revisit-these`).
- **`scripts/unraid-force-pull.sh`**: CLI pull + RepoDigest verify; optional `--rmi-retry` / `--recreate` when Force Update reports 0 B.
- **`scripts/unraid-rollout.sh`**: canonical vendored copy of appdata `rollout.sh` for sync onto Unraid hosts.

### Changed
- Library/query and title-card payloads include `view_count` / `view_offset_ms` / episode progress fields needed for badges without extra fetches.
- Dockerfile OCI labels: `org.opencontainers.image.version` / `.revision` / `.created`; `/app/.build-info` includes git short SHA.
- `docker-release.sh`: passes `VCS_REF`, prints Hub digests after push, optional `--date-tag` (`:latest-YYYYMMDD`).
- CA templates / `ca_profile.xml`: honest update notes when Force Update pulls 0 B; keep Repository `:latest`.

### Fixed
- **Docs**: Unraid Force Update systemic root cause — Dockerman *does* pull, but Engine can keep a stale local `latest` mapping (TOTAL DATA PULLED: 0 B). Prior BUILD_DATE / label cache-busting remains for Hub uniqueness only; it does not bypass the no-op. Supported path: `docker pull` / `unraid-force-pull.sh` / appdata `rollout.sh` ([DOCKER.md](docs/DOCKER.md), FAQ, wiki Unraid).

## [1.8.10] — 2026-07-17

Wikipedia-default long synopsis and first-start idle bootstrap so fresh installs gain plot depth without waiting days or spending LLM tokens.

### Added
- **First-start idle bootstrap**: on IdleScheduler start, never-run foundational tasks run once in sequence (`metadata_enrichment` if backlog → `summary_motifs` → `keyword_theme_tagging` → `long_synopsis_enrichment` when source enabled → `semantic_embeddings` only if zero embeddings). Persists `idle_bootstrap_completed` / queue so restarts do not loop. Logs/history use trigger `bootstrap`.

### Changed
- **`long_synopsis_source` defaults to `wikipedia`** (free, no API key, deeper plot without LLM). Missing/unset → wikipedia; explicit empty or preferred **`off`** (also `none`/`disabled`) disables the trickle.
- Docs (`CONFIGURATION`, `CURATOR_KNOWLEDGE`, `HELP`) explain why Wikipedia is default and why first-start sequencing exists.

## [1.8.9] — 2026-07-17

Library knowledge Wave 2: optional long synopsis enrichment, free keyword→theme facets, knowledge coverage UI across Admin/Explore/Tasks, Plot knowledge on title detail, and Plot Lab theme chips.

### Added
- **Knowledge coverage UI**: Admin Dashboard panel + compact strips on Explore and Scheduled Tasks (`GET /api/library/knowledge-coverage`); themes/synopsis metrics feature-detected when present.
- **Title detail Plot knowledge** panel: plot layers present, motif/keyword/theme chips, neighbor count (`plot_knowledge` on title detail).
- Plot Lab **theme chips** when `facet_type=theme` catalog returns data; Why? layer labels humanized (Motif / Keyword / Plot text).
- Optional **long synopsis** (`long_synopsis` / `synopsis_source`) via idle `long_synopsis_enrichment` (Wikipedia or OMDb when `long_synopsis_source` is set). Never overwrites Plex/TMDB; skips cleanly when unconfigured.
- Offline **keyword→theme** mapping (`keyword_theme_tagging`) writes controlled `facet_type='theme'` from TMDB keywords — no API key or LLM.
- Long synopsis feeds motif extraction, embedding text, and hybrid Plot Lab plot-text match; hybrid also considers theme facets.

### Changed
- Help / `CURATOR_KNOWLEDGE.md` / `WEB_UI.md`: document coverage surfaces, multi-signal Plot Lab, and how to read knowledge depth.
- `llm_theme_tagging` remains a reserved stub (skips); production themes come from `keyword_theme_tagging`.
- Docs: `DATA_MODEL`, `ARCHITECTURE`, `CONFIGURATION`, `HELP` cover synopsis opt-in and free theme mapping.

## [1.8.8] — 2026-07-17

Library knowledge Wave 1: richer motif extraction, multi-signal Plot Lab AND, durable scheduled-task run history with measured rate and auto-tune, in-app Help + curator knowledge guide, plus About/Surprise Me/sidebar polish.

### Added
- **Help** (`/help`): in-app guide from `docs/HELP.md` with role-aware jump links (browse/chat for everyone; owners see curation, Scheduled Tasks, coverage, LLM-vs-free). Entry points in AppNav, footer, user menu, login, keyboard `?` modal, and `/help` slash-command note.
- **Curator knowledge guide** (`docs/CURATOR_KNOWLEDGE.md`): educational why/what/how for library knowledge dimensions, Kill Bill bride∩coma sparsity case study, idle-task trickle, coverage expectations, and Phase A–D roadmap hooks (multi-signal Plot Lab, durable run history / auto-tune, long synopsis, coverage UI).
- Motif extraction upgrades: possessive normalize, bigrams, keyword-stem retention, higher per-title budget; sources include tagline + optional `llm_logline`.
- Plot Lab **Multi-signal** / **Motifs only** modes (`plot_match_mode`); Why? cites match layers (`match_layers`).
- Knowledge coverage stats on `/api/library/stats` (`knowledge_coverage`) and `GET /api/library/knowledge-coverage`.
- **Durable scheduled-task run history** (`scheduled_task_runs`): every idle/manual run is persisted with metrics, items processed, and outcome; Admin shows recent runs + measured items/hour (p50/p95 duration, success rate). Retention via `data_retention` (`task_run_retention_days`, default 60).
- **Scheduler auto-tune** for trickle tasks (`metadata_enrichment`, `semantic_embeddings`, `plot_neighbors`, `llm_logline_enrichment`): persists tunable `items_per_cycle`, safely raises/lowers batch and interval from measured duration vs timeout and backlog ETA vs target horizon; decisions logged in run metrics. Owner can still override cadence and batch in Admin.
- **Neighbor catch-up**: `plot_neighbors` progress scope is titles missing neighbor rows (`neighbors_backlog`); cycles prefer those seeds so a full library can densify with auto-tune.
- Owner APIs: `GET /api/admin/scheduled-tasks/{name}/history`, `GET /api/admin/scheduled-tasks/{name}/rate`; `PUT` accepts `items_per_cycle`.

### Fixed
- **About / What’s New release notes**: FastAPI now serves `/release-notes.json` from `frontend/dist` (Vite root public file). Previously only `/assets/*` was mounted, so Docker builds returned 404 and the About page showed “Could not load release notes.”
- **Surprise Me no-op**: quick-pick card now mounts below the transcript (near the composer) and scrolls into view on click; normalize API `summary`→`overview`, `in_library`, and genres so loading/empty/error feedback is always visible.
- **Plot Lab intersections**: sparse motif facets no longer brick AND walls — hybrid mode matches each token via motifs ∪ keywords ∪ live plot text (e.g. `bride` + `coma` → Kill Bill).

### Changed
- **About page** (`/about`): AppShell chrome (hamburger AppNav + BackLink), explore reading-column layout, and Fraunces/DM Sans section typography aligned with Explore/Settings; remains public when multi-user auth is on.
- **Sidebar library totals**: server name / movie·show counts moved from under Conversations to the sidebar footer above Explore + Watchlist.
- **Docs**: `ARCHITECTURE.md`, `DATA_MODEL.md`, `FAQ.md`, `ONBOARDING.md`, and `WEB_UI.md` link the knowledge guide and Help; onboarding adds a post-sync “warm library knowledge” checklist. Motif sparsity + multi-signal Plot Lab documented in `DATA_MODEL` / `ARCHITECTURE`. Idle-scheduler history, measured ETA, and auto-tune safety caps documented in `ARCHITECTURE` / `CONFIGURATION`.
- Admin Scheduled Tasks ETA prefers measured throughput when history exists (falls back to theoretical `progress.py`).

## [1.8.7] — 2026-07-17

Sidebar conversation layout polish, turnstile Why? collapsed by default, faster watchlist loads, and consistent centered Play on in-library posters.

### Fixed
- Conversation list no longer stretches uneven gaps between threads; items stay top-aligned with consistent spacing.
- Turnstile **Why this?** stays collapsed by default (reason/overview no longer pretends to be expanded).
- Watchlist page load: skip Plex pull on open; enrich large lists with bulk library lookups instead of per-pin queries.

### Changed
- Sidebar: **+** new-thread control shares the Conversations header row with collapse; Explore and Watchlist are full-width nav buttons.
- Poster actions: centered always-on Play for in-library titles (clears the multi-select checkbox corner); trailer/recommend stay as hover corners; person filmography uses the same card actions.

## [1.8.6] — 2026-07-17

Security hardening (proxy-aware rate limits, OpenAPI off by default), pentest protocol v1.0, Scheduled Tasks cadence/ETA controls, Discover watchlist GUID enrichment, person-page credit grouping, and Plot Lab motif Why?.

### Security
- Ignore `X-Forwarded-For` for rate limiting unless `CURATORX_TRUST_PROXY_HEADERS=1` (fixes LAN auth throttle bypass — finding S14 / TC-AUTH-RL-01).
- Hide FastAPI `/docs`, `/redoc`, and `/openapi.json` unless `CURATORX_EXPOSE_OPENAPI=1` (finding S15 / TC-PERIM-05).

### Added
- Repeatable penetration-test protocol v1.0: `docs/security/pentests/`, harness `scripts/security/pentest/` (bootstrap, loopback mocks, checklists, runners), baseline engagement `2026-07-platform-full/` (29 pass / 0 fail / 1 skip).
- Admin **Scheduled Tasks**: selected-task description, owner frequency controls (presets + custom hours), and live library/backlog throughput ETAs that update as cadence is adjusted.

### Fixed
- **Plex Discover watchlist sync**: request Guids (`includeGuids=1`), prefer JSON list payloads, parse typed provider paths (`tmdb://movie/550`), and enrich missing TMDB/TVDB via metadata lookup — fixes “Pulled N · unresolved N” when Discover only returned `plex://` keys.
- **Person page filmography**: collapse repeated poster cards for the same title into a single card with all credits (e.g. actor role + Director/Producer/Writer) listed underneath, instead of one card per credit.

### Changed
- **Plot Lab motif wall**: multi-motif selection is now an intersection (AND), matching tag browse; each poster gets a **Why?** control explaining the match with selected motifs and plot-summary excerpts.

## [1.8.5] — 2026-07-16

Watchlist explore page, title detail drawer and polish, Settings/Admin UX, Plex Discover pagination, bulk library delete, watched-state controls, and scheduled-task outcome messaging.

### Changed
- **Settings redesign** (Profile, Voice, Watchlist): shared card layout (`SettingsPanel` / `SettingsPageHeader` / toggle-switch `SettingsToggle`) with constrained content width, short section leads, and Fraunces page titles / DM Sans section headings — replaces sparse left-aligned checkboxes
- **Watchlist IA split**: Settings → Watchlist is **sync preferences only** (Plex Discover toggles, Sync now, token + pull stats); the media list moved to `/watchlist`
- Sidebar **Watchlist (N)** and AppNav **Watchlist** route to `/watchlist` (legacy `/?watchlist=1` deep links redirect)
- Admin **Advanced**: disk paths, sync, and MCP keys in panel cards with aligned forms, scoped save actions, and compact MCP key rows; TMDB image-size controls removed from the UI (still in `settings.json` / API)
- Chat top bar: **CuratorX** wordmark links home; agent activity on the **X** (idle/thinking/error); removed curator name under the logo
- Title detail polish: decade/genre/language/country meta drill-ins, unified accent links, MPAA chip, language full names, TMDB score chip (`TMDB ★`), merged year/release chip; removed Type/Rating sidebar tiles
- Library Pulse: per-type Movies/Shows cards (unwatched, stale adds, top genre, runtime)
- Removed compact **Tonight** strip above the composer (agent watch-tonight tools unchanged)
- Sidebar **Explore** moved to a full-width button above **Watchlist**; library totals moved to sidebar; removed streak/pinned blurbs from top bar
- Plot Lab: longer motif chips, All/Movies/TV filter, motif-wall pagination, corner poster action icons

### Added
- **Watchlist explore page** (`/watchlist`): poster/title grid with multi-select bulk **Remove** (soft unpin) and owner-only **Delete** (typed `DELETE`, library index only); **TitleDetailDrawer** with **Open full page**; `?enrich=1` list API
- Settings → Watchlist shows last-pull stats (`Pulled N · added M · unresolved K`) after Sync now
- Admin Dashboard purge candidates and Explore section multi-select: owner-only bulk **Delete** (typed `DELETE`)
- Title detail owner **Delete** and **Mark watched/unwatched** for in-library titles (CuratorX `view_count` + Plex scrobble)
- Trailer modals: privacy-enhanced YouTube embeds under app CSP with external fallback

### Fixed
- **Plex Discover watchlist sync**: paginates full watchlist (`X-Plex-Container-Start/Size`) instead of first page only; sync reports pulled/added/updated/unresolved counts
- Delete-thread undo toast docks in conversations sidebar with theme-aware styling
- Admin config typography: DM Sans section headings; Fraunces for rail/page titles
- Explore multi-select toolbar contained at ~1024px; poster hover actions no longer cover title text
- `/rate` review prompt uses logged-in user name; half-star ratings in review prompts and title detail
- Title detail **Leave a Review** opens in-place editor; trailer CSP note for reverse-proxy operators
- Admin Scheduled Tasks: human-readable skip/fail reasons, last-run impact summaries, immediate Started log line; `error_timeout` and other `error*` statuses format consistently in messages, summaries, and outcome detail
- Chat workspace crash on load: restore missing `isRateFlowRequest` import used by the `?rate=1` deep-link effect
- Watched-state DB writes: `last_viewed_at` as INTEGER epoch seconds and `updated_at` as REAL, matching `library_items` column conventions

## [1.8.4] — 2026-07-16

Shared AppShell chrome and Watchlist IA, What’s New release notes, capability/empty CTAs, and Explore/page completeness across title, person, tags, and chat.

### Added
- Shared **AppShell** (hamburger AppNav + header) on Explore, Tags, Plot Lab, tag/person/section, and title detail; DESIGN docs for hub children and Watchlist surfaces
- AppNav **Watchlist** opens the chat pin panel (`/?watchlist=1`); Settings → Watchlist stays sync/token only
- **What’s New** modal after upgrades; About release-notes panel; `scripts/generate-release-notes.sh` + docker-release hook → `frontend/public/release-notes.json`
- Guest **Ask owner** guidance on add/request CTAs; owner empty Explore rails deep-link to `/admin/tasks`
- Title Detail: reviews CTA, TV episode progress chip, collection peers rail
- Person browse: role filter + library-owned % (TMDB combined credits)
- Tags: multi-tag **AND** paths + sort; section pages: sort + bulk pin; Scheduled Tasks **Warm Explore** preset
- Chat: thread search, delete-thread undo toast, compact **Tonight** strip above the composer
- Library query `collection_name` filter; keyword facets AND-combined for tag browse
- Unit coverage for release notes, tonight strip, thread filter, title extras, person browse helpers, tag AND paths, explore empty CTAs

### Changed
- Leaf browse/detail pages keep BackLink *plus* AppShell (never BackLink instead of chrome)
- Explore empty-state copy stays honest; owners get a Scheduled Tasks CTA when caches are cold

### Fixed
- Serve SPA HTML for `/explore/tags`, `/explore/plot-lab`, and `/explore/section/{id}` (full page loads no longer 404)

## [1.8.3] — 2026-07-16

Explore navigation and section drill-downs, Scheduled Tasks admin, avatar upload/cache, concurrent card adds, and agent library-search quality.

### Added
- **Scheduled Tasks** admin (`/admin/tasks`) — list tasks, last run, Run now, live monitor with pollable run log
- Explore section pages for **Recently Added** / **Recent Releases** — All/Movies/TV filters, page sizes 20/40/100, pagination
- Dedicated routes `/explore/tags` and `/explore/plot-lab`; hamburger **AppNav**; sidebar Explore button
- Avatar cache/upload — Plex thumb → `/config/avatars`, Profile upload, serve `/api/auth/avatar/{id}`
- Delete conversation from the sidebar thread list
- Title Detail **Add/Request** for out-of-library titles; richer metadata (`release_date` / `first_air_date`)
- Tag facet search via API `q` (server-side, not only on-screen chips)
- LibraryMediaCard hover actions (Watch / Trailer / Recommend)
- Unit coverage for scheduled tasks admin, avatars, facet search, library keyword search, turnstyle items, back nav, add concurrency

### Changed
- Direct card adds skip the tray confirmation path; adds run **concurrent / non-blocking**
- Consistent **BackLink** / backNav (tag results → tags, not always chat)
- Chat overflow containment after agent responses
- Turnstyle Confirm/Expand counts align with addable shows (drop items without `tvdb_id`)

### Fixed
- Agent library search is **keyword/text-first** with semantic fallback only
- Gap tool confident keyword resolution; TMDB title/id mismatch hardening

## [1.8.2] — 2026-07-16

Hot-path latency, Surprise Me reliability, responsive Explore/recommendations, composer chrome, and scheduled purge-candidate caching.

### Fixed
- **Title Detail latency** — optional `enrich` flag; skip purge scoring on the hot path; short TMDB/Fanart/Plex timeouts; `library_item_by_rating_key` index lookup
- **Surprise Me / quick-pick no-op** — loading/empty/error states; `COALESCE(view_count,0)=0`; genres hardening; agent tool alignment
- Explore/recommendations responsive layout — contained rails/chips, auto-fit grid
- Default persona selected on load (`resolveActivePersona`)
- `/admin/persona` crash — defensive slider fields
- Chat scroll containment — media strips scroll within the transcript

### Changed
- Composer redesign — Cursor-like chrome: persona dropdown + mic/surprise/circular send in toolbar
- Removed TV completion from `/admin/dashboard`

### Added
- Purge candidates scheduled cache + **Refresh now** (`scheduler/tasks/purge_candidates.py`, refresh endpoint)
- Unit coverage for quick-pick, `resolveActivePersona`, chat card scroll, purge cache, and title hot path

## [1.8.1] — 2026-07-16

Person/tag browse surfaces on Explore and Title Detail, plus Windows-native e2e/dev tooling and Unraid rollout docs.

### Added
- **Person browse** (`/person/{tmdb_person_id}`) — profile + library filmography from structured credits; resolve-by-name API for cast/crew links
- **Tag browse** (`/tag/{tag_name}`) — genre/motif/theme facet pages with library title grids
- Clickable cast, crew, genre, and motif chips on Title Detail and Explore that deep-link into person/tag pages
- Windows PowerShell helpers: `scripts/setup-dev.ps1`, `scripts/dev-server.ps1`, `scripts/run-e2e.ps1`; cross-platform `scripts/start-e2e-server.mjs`
- Playwright coverage for person/tag browse (`e2e/person-tag-browse.spec.ts`) and unit tests (`tests/test_person_browse.py`)
- Unraid appdata **rollout** docs (`docs/DOCKER.md`) — `rollout.sh` pull/recreate without wiping `/config`

## [1.8.0] — 2026-07-16

Platform expansion: structured credits + metadata enrichment, layered plot embeddings with materialized neighbors, title relations graph, Explore feed APIs, dual theme, and structural UI (Title Detail, Explore shell, agent avatar). Teaching-kit docs updated for sync-vs-idle trickle, honest provenance, and homelab SQLite constraints.

### Added
- **Lights Up / Lights Down** dual theme (+ Match system) with icon top-bar chrome
- **Explore hub** (`/explore`) — feed rails (recently-added, recent-releases, on-this-day), Library Pulse strip, Plot Lab (motifs + seed neighbors)
- **Title Detail** redesign — backdrop hero, trailer, Watch on Plex, **More Like This** neighbors carousel
- **Agent avatar** beside assistant messages; expandable **agent activity log** on the thinking indicator (SSE `tool_call` args/summary)
- Frontend helpers + e2e for Explore feeds (`exploreFeeds.js`, `e2e/explore.spec.ts`)
- Library **metadata enrichment** + structured **people / credits** (dual-written with legacy cast/directors JSON)
- Layered plot text (`tmdb_overview`, `tagline`, optional `llm_logline`) and `embedding_model` hygiene
- Materialized **`item_neighbors`** (similar + surprising scores) via idle `plot_neighbors`
- **`title_relations`** graph (collection / neighbor / shared_crew; optional llm_theme) via `title_relations_refresh`
- Motif / theme facets (`summary_motifs`, optional `llm_theme_tagging`)
- Agent tools: `find_similar_titles`, `list_relations`, `walk_relations`, `titles_by_person`; `get_facet_catalog` supports `motif` / `theme`
- Explore/library APIs: `/api/library/feeds/*`, `/api/library/neighbors/{item_id}`, `/api/library/motifs`, title neighbors route
- Value-based tests for feeds, neighbors, relations, and person tools (`tests/test_explore_wave3.py`, `tests/test_title_neighbors_api.py`)
- Docs teaching kit: ARCHITECTURE, DATA_MODEL, DESIGN, MCP, TESTING, README, wiki (Home / FAQ / Library-Sync)

### Changed
- Idle scheduler registers enrichment → embeddings → neighbors → motifs → relations trickle path
- Provenance honesty: feeds never invent release dates from year alone; empty caches return explanatory notes

## [1.7.13] — 2026-07-15

### Fixed
- Surprise Me blank screen — genres returned as a JSON string caused TitleCard to crash on `.join`
- Watchlist refresh now pulls from Plex (sync existed but was never called)
- TMDB ID "crossed wires" — `get_title_detail` dropped `tmdb_id` when `tvdb_id` was present; enrichment used the wrong field
- Context label stuck on old topic for new/switched threads (`initializeThreads` now reads per-thread `context_label`)
- Profile dropdown menu items unclickable (topbar stacking context under chat; z-index fix)
- ConfigPage / related error handling when touched

### Added
- Click movie/TV cards (chat + turnstyle) to open title detail with YouTube trailer modal
- Watch on Plex action on cards/detail when title is in library
- Plex server name shown before library totals in top bar
- Click watchlist items to open title detail
- Recommend titles to household users with delightful unread inbox on home
- Per-user UI font size (small/medium/large) in Profile settings
- Playwright/e2e coverage for profile menu clicks and card affordances

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
