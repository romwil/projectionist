# 00 · Platform map — Projectionist 360° review, run 2026-11-01

**Reconnaissance lead · shared foundation for every department.** This is a map, not a verdict. It contains no graded findings. Where something looked off during the walk, it is listed under "Pointers" with a confidence note, so the owning department can confirm or dismiss it.

| Item | Value |
|---|---|
| Code reviewed | `05274cf` (merge of [PR #189](https://github.com/romwil/projectionist/pull/189), tag `v1.38.0`). Read from the read-only snapshot `/tmp/review360-05274cf`. Cite as `05274cf:path:line`. |
| Version | 1.38.0 (`05274cf:pyproject.toml:7`, `05274cf:frontend/package.json:4`) |
| Live instance | QA sidecar `http://10.10.1.202:8792`. `GET /api/health` → `{"status":"ok","version":"1.38.0"}` |
| Mode on QA | Multi-user, invite-only, local password sign-in only (`/api/features` → `auth_methods: ["local"]`). LLM configured (Anthropic). Live Channels feature enabled. |
| Walked as | **Owner**, using a browser session that was already signed in to a QA owner test account. Read-only, except for one chat prompt (which created one conversation thread) and dismissing the What's New modal (localStorage only). |
| Not walked live | Signed-out public pages as a true anonymous visitor, member role, youth role, Plex PIN sign-in, OIDC, setup wizard, invite redemption, Watch/Play, Live tuning, lobby theater `:8791`. These are mapped from code below. |

---

## 1. Platform map

### 1.1 What the product is

Projectionist is a self-hosted companion for one Plex household. One owner runs it, usually as a Docker container on Unraid next to Plex. It reads the Plex library into its own SQLite database, enriches every title with external metadata, and then gives the household:

- an LLM **chat curator** that recommends from (and beyond) the library,
- **Explore / Search / Library** browsing with taste-aware shelves,
- **Play** in the browser through Plex (`/watch/:ratingKey`),
- **Live** virtual TV channels built on Tunarr (guide + watch),
- per-person **watchlists, lists, reviews, badges, inbox, newsletters, Year in Review**,
- an owner **Admin** console for connections, libraries, members, persona, Live channel studio, tasks, health, mail, newsletters, youth, logs,
- an optional **MCP server** so external AI agents can read (and in "full" mode act on) the library.

The package description still frames it as an "Agentic Plex collection curator with BYOP LLM, RAG, and Radarr/Sonarr integration" (`05274cf:pyproject.toml:8`). The current login page frames it as "your household's private movie and TV companion" (live, `/login`). That gap between "curator tool for an owner" and "companion for a household" is a theme later departments should hold in mind.

### 1.2 Stack and versions

| Layer | Technology | Evidence |
|---|---|---|
| Backend runtime | Python 3.12 (`python:3.12-slim` image); package allows ≥3.10 | `05274cf:Dockerfile:39`, `05274cf:pyproject.toml:11` |
| Web framework | FastAPI ≥0.115, Uvicorn ≥0.32, Pydantic v2, sse-starlette (streamed chat), python-multipart | `05274cf:pyproject.toml:27-37` |
| Core deps | httpx, numpy (local embeddings / cosine), apprise | `05274cf:pyproject.toml:21-33` |
| Optional | `mcp>=1.30,<2` (MCP server, pinned off v2), `sqlite-vec` (ANN prefilter, not in default image) | `05274cf:pyproject.toml:40-50` |
| Dependency pinning | Hash-pinned `requirements/runtime.lock` installed with `--require-hashes` (new in this release window) | `05274cf:Dockerfile:59-61` |
| Data | SQLite in WAL mode under `DATA_DIR` (`/config`); `settings.json` with secrets encrypted at rest (`enc:v1:` prefix) | `05274cf:projectionist/library/db/_shared.py:96`, `05274cf:projectionist/secrets_crypto.py:1-10` |
| Frontend | React 18.3, React Router 6.28, TypeScript 5.9, Vite 5.4; react-markdown + rehype-sanitize + remark-gfm; hls.js (Live/Play) | `05274cf:frontend/package.json:18-44` |
| Fonts | Self-hosted Fontsource: DM Sans (body), Fraunces (display), Material Symbols Outlined (subset woff2). No Google Fonts requests. | `05274cf:frontend/package.json:19-21`, `05274cf:frontend/index.html:11`, `05274cf:frontend/src/styles/00-fonts.css:4` |
| Lint/format | ESLint 9 + jsx-a11y + react-hooks, Prettier; Python ruff (conservative baseline) and mypy (scoped to a few packages) | `05274cf:frontend/package.json:30-44`, `05274cf:pyproject.toml:78-160` |
| Tests | 219 pytest files (coverage floor 74%), frontend `node --test` unit tests in `frontend/src/lib/*.test.mjs`, 23 Playwright specs in `e2e/` (mocked server on :8799) | `05274cf:pyproject.toml:72`, `ls tests e2e` |
| Size | ~119k lines of Python under `projectionist/`, ~76k lines of TS/TSX under `frontend/src`, ~21k lines of CSS in 17 files | `wc -l` on the snapshot |
| License | AGPL-3.0-only | `05274cf:pyproject.toml:10` |

### 1.3 Hosting and deploy model

- **One container, two ports.** The main app listens on `PORT=8788`; a separate "lobby theater" ASGI app (kiosk display) runs in the same process on `8791` (`05274cf:projectionist/web/__main__.py:35-42`, `05274cf:docker-compose.yml:10-12`). The SPA is pre-built into `frontend/dist` and served by FastAPI (`05274cf:projectionist/web/spa_routes.py:30-40`). Runs as non-root UID 1000 via `gosu` (`05274cf:Dockerfile:73-77`).
- **Multi-stage image.** Node 20 builds the SPA on the build platform; the Python stage installs ffmpeg (Investigate stills / audio identify) and the hash-locked wheels (`05274cf:Dockerfile:16-66`). `docs/PRIVACY.md` and `docs/HELP.md` are compiled into the SPA as in-app pages.
- **Distribution.** Docker Hub image `romwil/projectionist:X.Y.Z`, published by `scripts/docker-release.sh` (multi-arch buildx). Unraid Community Applications template in `templates/projectionist.xml` / `unraid/projectionist.xml`. Ship order is Hub publish → PR merge + tag → CA proof by Hub pull on QA (Path B) → prod `rollout.sh` pull-only (`05274cf:docs/RELEASE.md:11-33`, `05274cf:docs/ops/AUTOMAT.md:116-133`).
- **Maintainer environments.** Prod `:8788`, QA sidecar `:8792` (ephemeral), lobby theater `:8791`, all on one Unraid host. The public hostname sits behind a CDN/proxy and is not authoritative.
- **Optional sibling container.** Live Channels can drive a BYO Tunarr instance, or Projectionist can pull/start a pinned `chrisbenincasa/tunarr:1.3.9` container itself if a Docker socket is mounted (`05274cf:projectionist/config_store.py:536-566`).
- **Config sources.** `settings.json` in `DATA_DIR` (owner UI writes it) merged with environment variables (`PROJECTIONIST_*`; legacy `CURATORX_*` still accepted) (`05274cf:projectionist/config_store.py:41-63`, `05274cf:projectionist/envcompat.py`).

### 1.4 Third-party integrations

| Integration | Purpose | Required? | Evidence |
|---|---|---|---|
| **Plex Media Server** | Library source, playback, watch state, collections, Live TV DVR attach | Effectively yes (setup can finish with Plex only) | `05274cf:projectionist/connectors/plex.py`, `plex_collections.py` |
| **plex.tv** | PIN-based sign-in for members; account profile | Optional (QA uses local passwords only) | `05274cf:projectionist/connectors/plex_account.py`, `05274cf:projectionist/web/auth.py:1-11` |
| **OIDC IdP** (Authelia, Authentik, Keycloak…) | Alternative sign-in | Optional | `05274cf:projectionist/config_store.py:515-524` |
| **LLM providers** | Chat curator, loglines, motifs, newsletters. OpenAI (default `gpt-4o-mini`), Anthropic (default `claude-sonnet-4-6`), Gemini, Groq, Mistral, Together, DeepSeek, Ollama, OpenRouter, any OpenAI-compatible | Optional ("Browse and Play work without one") | `05274cf:projectionist/config_store.py:54-108` |
| **Embeddings** | OpenAI-style embedding endpoint, or local hash embeddings (QA uses local) | Optional | `05274cf:projectionist/config_store.py:735-737`; live Tasks page "Vectors: local hash embeddings" |
| **Radarr / Sonarr** | Add / remove titles (acquire, purge) | Optional | `05274cf:projectionist/connectors/radarr.py`, `sonarr.py` |
| **Seerr** (Overseerr/Jellyseerr successor) | Member requests, user linking on login | Optional (off on QA) | `05274cf:projectionist/connectors/seerr.py`, `05274cf:projectionist/web/auth.py:586-601` |
| **Tautulli** | Watch history evidence | Optional | `05274cf:projectionist/connectors/tautulli.py` |
| **TMDB, TVDB, fanart.tv, OMDb, Wikipedia** | Metadata, images, long synopses | TMDB effectively needed for rich data | `05274cf:projectionist/connectors/`, `05274cf:projectionist/config_store.py:723-729` |
| **Tunarr** | Live Channels engine (HDHomeRun emulation + XMLTV for Plex Live TV) | Optional | `05274cf:projectionist/live_channels/`, `05274cf:projectionist/config_store.py:536-618` |
| **Open-Meteo** | Weather for Live "Weather" channel and theater | Optional | `05274cf:projectionist/theater/weather.py:25`, `weather_geo.py:12` |
| **ACRCloud** | Audio identification for Investigate clips | Optional | `05274cf:projectionist/config_store.py:663-669` |
| **Mail: SMTP or Resend** | Invites, newsletters, digests | Optional | `05274cf:projectionist/config_store.py:622-638`, `05274cf:projectionist/mail/transport.py` |
| **Apprise** | Push to Discord/Telegram/etc. (owner and per-member URLs) | Optional | `05274cf:projectionist/config_store.py:642-651` |
| **Browser-side** | TMDB/TVDB/fanart image CDNs and YouTube trailer embeds (allowed by CSP) | Implicit | Live CSP header on `:8792/login` (`img-src` + `frame-src` list) |
| **Plex webhooks (inbound)** | Play/scrobble events into watch tracking, shared-secret guarded | Optional | `05274cf:projectionist/web/webhooks.py:23-29,182` |
| **MCP clients (inbound)** | Privacy-mode key (read-only, scrubbed) and full-mode key (can propose; self-confirm only if enabled) | Optional | `05274cf:projectionist/mcp/mode.py:14-64`, `05274cf:projectionist/config_store.py:756-765` |

### 1.5 Background jobs and scheduler

- **Idle scheduler.** One in-process asyncio loop that runs tasks only when the server is "idle", meaning no chat request for 15 minutes, in staleness order, sequentially (`05274cf:projectionist/scheduler/engine.py:1,83,162-183`). It has auto-tuned cadence, run history, quarantine for failing tasks, and an owner "Catch-up" lever (live: Admin → Tasks).
- **33 task modules** in `05274cf:projectionist/scheduler/tasks/`, grouped roughly as:
  - *Library knowledge:* `metadata_enrichment`, `long_synopsis_enrichment`, `llm_logline_enrichment`, `keyword_theme_tagging`, `summary_motifs`, `semantic_embeddings`, `plot_neighbors`, `title_relations_refresh`, `kinship_augmentation`, `base_augmentation`, `facet_taxonomy_audit`, `entity_memory_enrichment`, `coverage_signals`, `coverage_deficit_audit`, `gap_analysis`.
  - *Per-member:* `taste_refresh`, `member_weekly_rail`, `seasonal_rail`, `whisper_inbox`, `arrival_notifications`, `enthusiast_nudge`, `anniversary_scanner`, `year_in_review`.
  - *Comms:* `weekly_digest`, `weekly_letter`, `member_newsletter`, `owner_monthly_curation`.
  - *Watch evidence:* `watch_history_ingest` (every 15 min while idle, per `docs/PRIVACY.md`).
  - *Hygiene:* `purge_candidates`, `collection_gc` (ephemeral Plex collections, TTL 168h), `data_retention`.
  - *Live:* `live_guide_week`.
- **Other in-process jobs:** library sync (interval 24h, optional preferred hour), admin batch jobs (bulk delete), Live publish/attach jobs with progress SSE (`05274cf:projectionist/web/jobs.py`, `05274cf:projectionist/library/admin_batch_jobs.py`, `05274cf:projectionist/live_channels/job.py`).
- There is **no external queue or worker**. Everything runs inside the web process.

### 1.6 Route inventory

**Backend:** about 394 route handlers across 18 modules in `05274cf:projectionist/web/` (131 still declared directly in the 4,378-line `app.py`). By prefix: `/api/admin/*` 128, `/api/library/*` 55, `/api/setup/*` 16, `/api/auth/*` 16, `/api/chat/*` 11, `/api/live-channels/*` 8 (plus many under `/api/admin/live-channels`), `/api/lists` 8, `/api/settings` 7, `/api/watchlist` 6, `/api/users` 6, `/api/saved-library` 6, persona/personas/lenses 16, reviews 5, plex 5, taste 4, syllabus 4, notifications 4, media-issues 4, plus roughly 40 explicit SPA HTML routes.

**Unauthenticated allowlist** (multi-user mode): `GET /api/health`, `GET /api/features`, `POST /api/access-requests`, `GET /api/invites/validate`, `POST /api/invites/redeem/local`, `POST /api/auth/local/login`, Plex PIN create/poll/confirm, `POST /api/auth/logout`, OIDC authorize/callback (`05274cf:projectionist/web/auth.py:52-69`). Everything else under `/api/` returns 401 without a session (live check: `/api/auth/me` 401, `/api/live-channels` 401). The middleware has extra modes for setup and a "WAN interlock" (`05274cf:projectionist/web/auth.py:480-532`).

**SPA routes** (`05274cf:frontend/src/AppRoutes.tsx:100-155`, `05274cf:frontend/src/routes/AdminRoutes.tsx:17-38`), mapped to the spec's four surfaces:

| Surface | Routes |
|---|---|
| **Public** (no session) | `/login`, `/join` (invite link), `/privacy`, `/help`, `/about`, `/setup` (first-run wizard, only while setup mode is on). `/tour` redirects to `/login` (guest tour retired). There is no marketing, pricing, or SEO surface; it is a private app. |
| **Consumer** (member / youth) | `/` (redirects to the user's default page: Chat, or Explore when no LLM), `/chat`, `/search`, `/explore` (+ `/explore/tags`, `/explore/related`, `/explore/section/:id`), `/library` (tabs: Shelves, Watchlist, Collections, Browse; `/library/saved`, `/library/shelves/:id`, `/library/collections/:id`), `/title/:mediaType/:itemId`, `/title/episode/:ratingKey`, `/person/:id`, `/tag/:name`, `/watch/:ratingKey` (+ `/popout`), `/live`, `/live/watch` (+ `/live/popout`), `/inbox`, `/whisper`, `/year-in-review/:year`, `/settings/{profile,voice,taste,notifications,watchlist,lists}` |
| **Owner** (household admin, same person as platform admin here) | `/admin/overview`, `/admin/connections`, `/admin/libraries`, `/admin/persona`, `/admin/household` (labelled "Members"), `/admin/live-channels`, `/admin/lobby`, `/admin/holidays`, `/admin/seerr` |
| **Admin / Ops** | `/admin/tasks`, `/admin/taxonomy` ("Library knowledge"), `/admin/health` (tabs incl. sync, usage, issues, security log), `/admin/mail`, `/admin/newsletters`, `/admin/access`, `/admin/youth`, `/admin/advanced` (incl. "Integrations & keys"), `/admin/logs` |

About 14 legacy redirects remain (`/my-journey`, `/watchlist`, `/lists`, `/collections`, `/config`, `/explore/plot-lab`, `/explore/browse`, `/explore/engagement`, `/admin/dashboard`, `/admin/usage`, `/admin/issues`, `/admin/scheduled-tasks`, `/admin/sync`, `/library/:pageId`). One chain is two hops: `/explore/engagement` → `/my-journey` → `/settings/profile#badges`.

**Navigation model** (single source of truth in `05274cf:frontend/src/lib/primaryNav.ts`):
- Top bar icons: Search → Chat → Explore → (Live, if `live_channels_ready`) → Inbox → (Admin, owner only) → Settings. Youth labels: Chat becomes "Ask", Explore becomes "Browse".
- Phone/iPad bottom nav: the same peers, capped at 5; Live and Admin drop off first (`primaryNav.ts:174-187`).
- Hamburger drawer: the same peers, then "More": Related titles, Tags, Library, Help, Privacy, About. Youth get "My list" and Help only (`05274cf:frontend/src/lib/appNavItems.ts:16-52`).
- Admin rail: five groups. Setup: Overview, Connections, Libraries, Persona, Members. Experience: Live Channels, Lobby, Holidays, Seerr. Platform: Tasks, Library knowledge, Health. Communications: Mail, Newsletters. System: Access, Youth, Advanced, Logs (`05274cf:frontend/src/lib/adminNav.ts:11-38`).

### 1.7 Roles and permissions

- **Two modes.** With `features.multi_user_enabled=false` (the default), there is no login. Every request is the bootstrap owner, and role checks are skipped (`05274cf:projectionist/web/auth.py:535-569`, `05274cf:projectionist/config_store.py:487`). With it on (QA and prod), sessions are signed cookies with a 30-day TTL and server-side revocation (`05274cf:projectionist/web/session_tokens.py:17`, `session_revocations` table).
- **Two roles plus a flag.** `UserRole = Literal["owner","member"]` with rank member=1, owner=2 (`05274cf:projectionist/web/auth.py:81,148`). **Youth** is a per-user boolean (`is_youth`) on a member, not a role. It applies a fail-closed content-rating ceiling (default PG-13; unrated content is blocked) and a reduced nav (`05274cf:projectionist/config_store.py:655-659`, `05274cf:projectionist/youth/rating_gate.py`). Owners can set Youth mode, disable, reset password, and remove members from Admin → Members (live: buttons present per member row).
- **Enforcement.** A global middleware enforces authentication on all `/api/*` except the allowlist. Role is enforced per route with the `require_role("owner")` dependency (`05274cf:projectionist/web/auth.py:562-571`). The SPA also guards `/admin/*` client-side and redirects non-owners to `/settings` (`05274cf:frontend/src/layouts/AdminLayout.tsx:65-67,135-137`).
- **Joining.** Invite-only by default (`invite_only=True`, `open_auto_provision=False`). Invites are HMAC-signed tokens with a 7-day TTL, created by owners at `POST /api/admin/invites` and redeemed at `/join` (`05274cf:projectionist/invites.py:21-38`, `05274cf:projectionist/web/auth_routes.py:569-750`). Access requests are on by default (`access_requests_enabled=True`).
- **Sign-in methods.** Plex PIN (default on), local username/password (PBKDF2), OIDC (`05274cf:projectionist/web/auth.py:1093-1112`, `05274cf:projectionist/config_store.py:515-524`). QA exposes only local sign-in.
- **Agent/MCP permissions.** The chat agent has 65 tool definitions (`05274cf:projectionist/agent/tools/_definitions.py`). Library mutations (add/remove via *arr) go through a confirm-token flow. In multi-user mode, personal-data writes by the agent need confirmation unless `agent_may_mutate_personal_data` is on (`05274cf:projectionist/config_store.py:506-509`). MCP has privacy and full modes with separate keys (`05274cf:projectionist/mcp/mode.py`).

### 1.8 Data stores and main entities

- **SQLite** (WAL) at `DATA_DIR`, 81 tables, schema versioned through 60 migrations (`05274cf:projectionist/library/db/_schema.py`, `05274cf:projectionist/library/db/migrations.py:319`). Writes go through a write serializer (`_write_serializer.py`).
- **settings.json**: all integration config and secrets. Secrets are encrypted with `PROJECTIONIST_SECRETS_KEY` or a key derived from the session secret (`05274cf:projectionist/secrets_crypto.py:1-10`). The live Admin overview nags the owner to pin a dedicated secrets key.
- **Files in DATA_DIR**: `session_secret`, avatars, poster cache, Tunarr volume, backups (owner downloads a zip of settings plus the DB; `05274cf:projectionist/web/backup.py`).

Main entity groups:

| Group | Tables |
|---|---|
| Identity & access | `users` (`_schema.py:157`), `invites` (`:1431`), `access_requests`, `session_revocations`, `security_audit_log` (`:2200`), `service_integrations` |
| Library | `library_items`, `library_episodes`, `library_facets`, `people`, `credits`, `title_relations`, `item_neighbors`, `embeddings`, `derived_contexts`, `staged_augmentations`, `knowledge_fetch_state`, `sync_state` |
| Chat & memory | `chat_sessions`, `chat_messages`, `message_feedback`, `pending_actions`, `memory_entities`, `memory_relations`, `memory_insights`, `memory_snapshots`, `memory_entity_activity`, `user_memory_events`, `user_memory_notes`, `preference_facts` |
| Taste & personalization | `user_taste_profile`, `lens_taste_profile`, `curation_lenses`, `persona_templates`, `curator_persona_metrics`, `user_recommendations`, `user_weekly_rails`, `seasonal_rail_snapshots`, `rating_prompt_queue`, `user_title_reviews` |
| Watching | `watch_events` (`:1736`), `watch_sessions`, `watch_session_events`, `watch_completions`, `watch_ingest_cursors`, `watch_source_identities`, `watchlist_pins` |
| Lists & collections | `curated_lists`, `curated_list_items`, `saved_library_pages`, `ephemeral_plex_collections`, `arr_queued_titles`, `acquisition_exclusions` |
| Engagement | `engagement_badges`, `engagement_challenges`, `engagement_explainers`, `user_badges`, `user_challenge_progress`, `user_streaks`, `user_course_progress`, `user_syllabus_sessions`, `year_in_review_snapshots` |
| Notifications & comms | `user_notifications` (`:1014`), `weekly_digests` |
| Ops & telemetry | `scheduled_tasks`, `scheduled_task_runs`, `llm_usage` (`:1642`), `telemetry_events` (`:1673`), `interaction_telemetry`, `system_telemetry_stream`, `owner_checklist_marks`, `grooming_action_log`, `purge_dismissals`, `media_issues`, `cached_gap_analysis`, `curator_system_config` |
| Calendar | `holiday_observances`, `holiday_rail_titles`, `holiday_rail_shelf_mode`, `daily_anniversaries` |

Telemetry is described as on-box only ("Counted here; nothing leaves your server", live Admin Overview; `05274cf:projectionist/telemetry/`).

### 1.9 Design system location

- **Tokens:** `05274cf:frontend/src/styles/01-tokens.css` (389 lines, about 107 custom properties; expanded heavily in Phase 4).
- **Global styles:** 17 numbered CSS partials `00-fonts.css` … `16-live-studio.css`, plus `styles.css` and two component CSS files (`OwnerOpsOverview.css`, `MessageText.css`). About 21k lines of CSS in total. No CSS-in-JS and no utility framework.
- **Themes:** "Lights Up" (light) and "Lights Down" (dark), plus "system". Per-user `ui_theme` and `ui_font_size` are stored server-side (`05274cf:projectionist/web/auth.py:104-105`).
- **Primitives:** `Button.tsx` (new in Phase 4), `ConfirmModal`, `InlineAlert`, `HelpHint`, `PosterArt`, `TitleCard`; hooks `useFocusTrap`, `useRouteAnnounce`; `focusContract.ts`.
- **Written spec:** `05274cf:docs/DESIGN.md` (sections: visual language, visual state tokens, UI design system, button and field primitives, focus contract). Docs voice standard: `docs/DOCS_STYLE.md`.
- **Brand:** Projectionist wordmark with a projector-reel glyph. Warm cream (Lights Up) with a mustard/gold accent, Fraunces serif headings, DM Sans body (live screenshots).

### 1.10 What changed since the last run (`94fcd3f..05274cf`, 14 commits, 2026-10-31 → 2026-11-02)

The **household invite launch**, shipped as v1.38.0 in seven phases:

| Commit | Phase | Substance |
|---|---|---|
| `4d89f83` | 1 Delivery gate | CI gate, Dockerfile switched to the hash-locked `requirements/runtime.lock` (1,353 lines), agent tool registry tidy, RELEASE.md additions |
| `3e32585` | 2 Trust core | Chat ownership checks, agent tool policy (confirmed-action gating), youth rating gate fail-closed, fail-closed corrupt settings (503), sign-out helper; `tests/test_phase2_trust_core.py` (510 lines) |
| `abc7203` | 3 Invite UX | BD-5 default page per user (`/` → Chat or Explore), BD-2 My Journey folded into Settings → Profile, member password management, Plex-only setup wizard, new Profile page (255 lines) |
| `6ec105f` | 4 Polish & a11y | Tokens rewrite (+129 lines), `PrimaryBottomNav` (phone/iPad), route titles + announcer, focus trap/contract, self-hosted Material Symbols subset, `Button` primitive, end-card rating prompt in players |
| `442c246` | 5 Speed | Lazy route splitting (`AdminRoutes` chunk), static asset caching headers (`static_assets.py`) |
| `48667b6` | 6 Owner ops | `OwnerOpsOverview` (Needs attention, Monday pass, setup checklist), on-box attribution metrics, Security log panel + `security_audit.py`, `owner_ops.py` (551 lines), newsletter changes |
| `48173c7` | 7 RC | Merge repairs, e2e contract updates, member Help additions |
| `bc6c4a4` | Live | Guide cells show start–end times |
| `6448369`, `5529a5b`, `05274cf` | Release | v1.38.0 version bump, release notes, test fix, merge |

---

## 2. Personas

These are derived from code, copy, and the data model. Projectionist is a **household** product, so the generic spec personas map as follows: "owner" means the person who runs the server, and "platform admin" and "support agent" collapse into that same person. Assumptions are stated.

### 2.1 Core personas

| Persona | Mapped to | Goal | Context & device | Frequency | Top 3 tasks |
|---|---|---|---|---|---|
| **First-time visitor** — *Invited household member* | Public → Consumer | Get in, and see quickly why this beats opening Plex directly | Taps an invite link from a text or email on a phone; may have no Plex account | Once | 1) Open `/join?token=…` and create a password (or use Plex). 2) Land on their default page (Chat, or Explore without an LLM). 3) Find something to watch tonight. |
| **Returning consumer** — *Household member* | Consumer | "What should I watch tonight?" in under a minute | Phone on the couch, laptop, or iPad; evenings | 2–5×/week | 1) Ask Chat or use a "Tonight under 2h" chip. 2) Open a title and press Play / Watch together. 3) Pin to watchlist or rate after watching (end-card prompt). |
| **Power consumer** — *Cinephile member* | Consumer | Explore lineage, themes, and connections; curate shelves | Desktop, long sessions | Weekly | 1) Related titles / Tags / Person pages. 2) Build Shelves and Lists, export CSV. 3) Tune persona sliders, taste preferences, and lenses. |
| **New owner** — *Homelabber installing from Unraid CA* | Owner | Get a working, trustworthy setup without reading the codebase | Desktop browser on the LAN; Unraid UI next to it | Day 1 | 1) Setup wizard: connect Plex, map libraries, first sync. 2) Optionally connect an LLM, *arr, and mail. 3) Invite the first family member. |
| **Established owner at scale** — *Household admin, 5–10 members, 5k+ titles* | Owner + Admin | Keep it healthy in about 20 minutes a week; avoid surprises | Desktop; sometimes iPad | Weekly ("Monday pass") | 1) Clear "Needs attention" and tick the Monday pass. 2) Review Members (youth, resets), media issues, purge pressure. 3) Keep Live channels and newsletters running. |
| **Platform admin** — *Same owner, ops hat* | Admin | Diagnose failures and keep secrets and backups safe | Desktop; sometimes SSH to the host | When something breaks | 1) Health / Logs / Tasks (quarantined tasks, catch-up). 2) Security log (sign-ins, invites, role changes). 3) Backup download, secrets key, MCP key rotation. |
| **Support agent** — *Owner answering family questions* | Admin | Answer "why can't I see X / why did it recommend Y?" | Phone message from a relative, then desktop | Ad hoc | 1) Check the member's role and youth flag. 2) Reset password or re-send invite. 3) Explain recommendations (Help, "why" strings). No "view as member" tool exists. |

Assumption: there is no separate support or moderation organization. "Moderation" is limited to media issues reported by members, access requests, and youth gating.

### 2.2 Edge personas

| Persona | Goal & context | Top 3 tasks | Notes for departments |
|---|---|---|---|
| **Screen-reader user** (member) | Pick and play a film by voice | 1) Navigate Chat replies and title cards. 2) Open a title and Play. 3) Use Inbox. | Route announcer and focus-on-h1 are new in Phase 4. On the live title page `document.title` stayed "Title · Projectionist" and no `<main>` landmark was found. |
| **Keyboard-only user** | Same journeys without a mouse | 1) Tab through the top bar and the chat composer. 2) Operate poster overlay menus (⋮). 3) Dismiss modals (What's New, confirm dialogs). | Keyboard shortcuts modal exists (`KeyboardHelpModal.tsx`); focus trap hook exists. |
| **Low-bandwidth mobile user** | Browse on a weak cell or Wi-Fi connection | 1) Load Explore rails (posters from TMDB CDN). 2) Search. 3) Start Play (HLS). | Explore at 390px rendered with blank poster areas at capture time; Help page is about 100k characters for owners. |
| **Non-native-language user** | Understand the curator and labels | 1) Chat in plain words. 2) Read title synopses. 3) Understand admin copy. | UI is English-only (no i18n layer found). Copy is idiomatic and cinephile ("Which thread of your library shall we pull on?", "turnstyle view", "Named kinship"). |
| **Older user with low vision** | Read and tap comfortably on an iPad | 1) Increase text size (Settings → Profile → Text size). 2) Use Lights Up/Down. 3) Tap poster actions. | Per-user font size and theme exist. Several captured states show very light text (login heading, Explore rail titles) that may be mid-animation; needs a contrast check. |
| **Youth member** (added: household-specific) | Find something allowed, without seeing adult picks | 1) "Ask" (chat) or "Browse". 2) "My list". 3) Play. | Fail-closed rating gate; reduced nav; youth-specific labels. Not walked live. |

---

## 3. Sacred cows register (initial)

Embedded assumptions each department should rule on in its own domain. These are not findings.

| ID | Assumption | Where it shows up | Domains most concerned |
|---|---|---|---|
| SC-01 | **Chat is the front door.** `/` lands on Chat unless the user picks otherwise, or no LLM is configured. | `05274cf:frontend/src/AppRoutes.tsx:63-78`, `05274cf:frontend/src/lib/defaultHome.ts` | Product, UX, Growth |
| SC-02 | **The product is "the Curator", with a persona** ("The Professor", seven personality sliders, voice mode). | `docs/DESIGN.md` §Persona tuning; chat composer persona picker | Product, UX, Design |
| SC-03 | **One self-hosted instance per household, one owner.** No hosted/SaaS tier, no multi-household tenancy. | Deploy model; `BOOTSTRAP_OWNER_ID` | Product, Architecture, Ops |
| SC-04 | **Two roles (owner/member) plus a youth flag are enough.** No co-admin, no granular permissions (contrast Seerr's per-user permissions). | `05274cf:projectionist/web/auth.py:81,148` | Security, Product, Ops |
| SC-05 | **Single-owner, no-login mode is the default** (`multi_user_enabled=False`). | `05274cf:projectionist/config_store.py:487` | Security, Privacy |
| SC-06 | **Invite-only with 7-day signed links is the right household onboarding.** Access requests on by default; open auto-provision off. | `05274cf:projectionist/invites.py:21`, `config_store.py:492-501` | Growth, Security, UX |
| SC-07 | **The LLM is optional, but the experience is designed around it.** "Browse and Play work without one". | Admin setup checklist copy; `llm_configured` flag | Product, Perf/cost |
| SC-08 | **Bring-your-own LLM provider (10+ providers) beats one opinionated default.** | `05274cf:projectionist/config_store.py:54-108` | Product, Architecture, Ops |
| SC-09 | **Everything runs in one Python process**: web, scheduler, Live publishing, theater app on a second port, batch jobs. | `05274cf:projectionist/web/__main__.py`, `scheduler/engine.py` | Architecture, Perf |
| SC-10 | **SQLite (WAL) is sufficient** for 81 tables, 60 migrations, telemetry, and memory, with no external DB. | `05274cf:projectionist/library/db/` | Architecture, Perf |
| SC-11 | **"Idle" background work (no chat for 15 min) is the right scheduling model** for 33 enrichment and comms tasks. | `05274cf:projectionist/scheduler/engine.py:83,162-183` | Perf, Ops, Architecture |
| SC-12 | **Deep library knowledge (motifs, kinship, embeddings, title relations) is worth its compute and complexity.** "Named kinship %" is the owner's north-star knob. | Live Tasks page; `scheduler/tasks/` | Product, Perf, Ops |
| SC-13 | **Live virtual channels belong in this product** (Tunarr orchestration, Plex DVR attach, Weather channel with muzak). | `05274cf:projectionist/live_channels/` (30+ modules), `config_store.py:536-618` | Product, Architecture, Ops |
| SC-14 | **In-browser Play / "Watch together" should exist**, rather than deep-linking to Plex apps. | `/watch/:ratingKey`, `LibraryPlayer.tsx`, `TheaterPlayer.tsx` | Product, Perf, UX |
| SC-15 | **Owners can delete library media from consumer surfaces** (bulk Delete in Search/Browse toolbars, typed-DELETE gate on by default). | Live `/search` toolbar shows "Delete" for owner; `config_store.py:748-750` | UX, Security, Ops |
| SC-16 | **Gamification fits a household companion** (badges, streaks, challenges, syllabus courses, Year in Review). | `engagement_*`, `user_badges`, `user_streaks`, `user_course_progress` tables | Product, Growth, Privacy |
| SC-17 | **Weekly comms (digest, letter, newsletter, nudges, whispers) are welcome**, opt-in per channel. | `scheduler/tasks/weekly_*`, `member_newsletter`, `whisper_inbox`; `CurrentUser.newsletter_opt_in` | Growth, Privacy |
| SC-18 | **Telemetry stays on the box** and is enough to steer the product (no product analytics). | Live Admin Overview "nothing leaves your server"; `telemetry/` | Growth, Privacy |
| SC-19 | **The owner wants a dense, cinephile Admin** with 20 sections, a Monday pass, and stage-level task stats. | Live Admin rail and Tasks page | UX, Ops, Design |
| SC-20 | **Editorial, idiomatic voice** ("Which thread of your library shall we pull on?", "turnstyle view", "Named kinship") is an asset for all members. | Live chat, Explore, Tasks copy; `docs/DOCS_STYLE.md` | Growth/content, A11y, UX |
| SC-21 | **Bespoke CSS (17 partials, ~21k lines) plus tokens** beats adopting a component library or utility framework. | `frontend/src/styles/` | Design, Architecture |
| SC-22 | **A hand-rolled SPA with client-side role guards**, served by FastAPI, with no SSR. Unknown deep URLs get a JSON 404 from the backend. | `05274cf:projectionist/web/spa_routes.py`; live `/this-route-does-not-exist` → `{"detail":"Not Found"}` | Architecture, UX |
| SC-23 | **Secrets live in settings.json, encrypted with a key derived from the session secret**, unless the owner pins a dedicated key. | `05274cf:projectionist/secrets_crypto.py:1-10` | Security, Ops |
| SC-24 | **An MCP server with a "full" mode** is a core feature, not an experiment. | `05274cf:projectionist/mcp/`, `config_store.py:756-765` | Security, Product, Privacy |
| SC-25 | **English-only, desktop-first admin; phone-first consumer** via a 5-item bottom nav. | `primaryNav.ts:174-187`; no i18n | UX, A11y |
| SC-26 | **Hub-first release and Unraid CA are the only distribution channel worth supporting.** | `docs/RELEASE.md`, `templates/projectionist.xml` | Ops, Architecture |

**26 items** (SC-01 … SC-26).

---

## 4. Live walkthrough

**Session:** QA `:8792`, version 1.38.0, signed in as a QA **owner** test account (session already present in the shared browser; I did not sign in, sign out, or change settings). Viewports were 1440×900 and 390×844 (CDP emulation, cleared afterwards). Library on QA: about 5,392 titles (4,595 movies, 797 shows) and 5 household users, one of them youth-flagged.

### 4.1 Screenshots saved (`screenshots/`, prefix `map_`)

| Screen / state | 1440 | 390 |
|---|---|---|
| What's New modal (first load after upgrade) | `map_whats-new-modal_1440.png` | — |
| Chat home (welcome state, starters, persona picker) | `map_chat_owner_1440.png` | `map_chat_owner_390.png` |
| Chat reply (success state: one prompt, one in-library pick) | `map_chat-reply-success_owner_1440.png` | — |
| Explore hub ("For you" rail) | `map_explore_owner_1440.png` | `map_explore_owner_390.png` |
| Search results (owner toolbar incl. bulk actions) | `map_search-results_owner_1440.png` | — |
| Title detail (Alien, 1979) | `map_title-detail_owner_1440.png` | `map_title-detail_owner_390.png` |
| Library → Shelves (empty state) | `map_library-shelves-empty_owner_1440.png` | — |
| Live guide (5 rows, timed cells) | `map_live-guide_owner_1440.png` | `map_live-guide_owner_390.png` |
| Settings → Profile | `map_settings-profile_owner_1440.png` | — |
| Admin → Overview (Needs attention, Household health, Monday pass) | `map_admin-overview_owner_1440.png` | `map_admin-overview_owner_390.png` |
| Admin → Tasks | `map_admin-tasks_owner_1440.png` | — |
| Help (owner render) | `map_help_owner_1440.png` | — |
| Login page (rendered while a session exists) | `map_login_signed-in-session_1440.png` | `map_login_signed-in-session_390.png` |
| Join with an invalid token (error state) | — | `map_join-invalid-invite_390.png` |

Admin → Members was walked but **not screenshotted**, because it lists household member names.

### 4.2 Walk notes by persona task

- **Returning consumer: "tonight" pick.** Chat loads with the composer disabled ("Describe what you're hunting for…") for a few seconds, then enables. There are starter chips ("Tonight under 2h", "Continue watching", "Something like…"), three idea prompts, mood "Surprise me" buttons, and a persona picker ("The Professor"). One prompt ("One short comedy under 100 minutes for tonight?") returned a single in-library pick with a rationale, a "Watch together" card, four follow-up chips, and thumbs feedback. The agent went back to idle about **7.7 s** after send. The thread list showed 5 untitled "New conversation" threads from 75 days ago.
- **Search.** `/search?q=alien` gives 135 results over 3 pages, with filters for type, watch state, decade/year, language, genres; sort; Posters/List view; per page up to "All"; column picker; **Export CSV**; and bulk **Select page / Pin to watchlist / Delete** (Delete is owner-only). A "Beyond your collection" escape hatch was offered.
- **Title detail.** Hero with Watch trailer, Leave a review, Mark as watched, Watch together, and More actions; then Synopsis, Your watch history, Subtitles ("Ask Plex for subtitles"), Plot knowledge (Motifs/Themes/Keywords), Tags, Cast, Title connections, "More in Alien Collection", and "Shared cast & crew" rails. This is a long page.
- **Explore.** Search box, four entry tiles (Movies, TV, Related titles, Tags), "Filling in shelves…" loading text, then a "For you" rail with "You watched X; Y — both stories turn on a spin off." explanations.
- **Library.** Tabs: Shelves, Watchlist, Collections, Browse, plus "Saved curator responses". The Shelves empty state reads "nothing shows up here until you make one. Create a shelf".
- **Live guide.** Five rows: 100 Comedian, 101 Refer, 102 Stand Special, 103 Youth Safe (empty), 104 Weather ("Local forecast"). Cells show start–end times (new in 1.38.0) and rating badges; gaps are labelled "Between programs". At 390px the guide scrolls horizontally inside its frame, and short cells clip their time text vertically. Before data loaded, the 390 page briefly showed "Not on the air yet — Ask the household owner to enable Live Channels in Admin." I did not tune any channel.
- **Settings → Profile.** Sections: Identity, Chat name, Weather place, Appearance, Default page, Text size, Playback, Badges & achievements, Requests, Link Plex, Password, Sessions. The Settings side nav has Profile, Voice & persona, Taste preferences, Notifications, Watchlist, Lists.
- **Owner: weekly upkeep.** Admin → Overview opens with "5 things need attention" (Radarr and Sonarr "marked connected but has no saved key", pin a secrets key, download a backup, Monday pass not done). Then come Household health tiles (Plex Connected, 5,392 Indexed, 88% Unwatched, 0% Rated, Live "Warming — Finish Setup to put stations on air"), the Monday pass checklist (Named kinship 33%, Open issues 0, Purge pressure 100, Tasks catch-up), on-box metrics ("last 7 days: 0 chat turns · 0 plays in Projectionist · 0 from a pick"), and Setup & stewardship (4 of 7 done).
- **Owner: tasks.** Admin → Tasks shows the idle-scheduler state, a knowledge summary line ("Named kinship (opened) 33% · Named kinship 38% · Similar cache 100% … Vectors: local hash embeddings"), Catch-up / All tasks / Next run / Heaviest load views, and a table with stage-level counters per task.
- **Owner: members.** Admin → Members (page heading "Household") has an optional "Household login" section and "Household users" with per-row Set Youth mode / Disable / Sync Seerr / Reset password / Remove.
- **Public: login & join.** `/login` (local only on QA) shows a value statement, Username, Password, Sign in, "Need an invite?", and footer Help · Privacy & data use · About. `/join?token=<invalid>` shows "Join this household — This invite is not available. Invite not found — Already a member? Sign in."
- **Unknown route.** `/this-route-does-not-exist` returns raw JSON `{"detail":"Not Found"}` from the backend, not the SPA's `NotFoundPage`.
- **Headers (public `/login`).** CSP `default-src 'self'` with an image CDN allowlist and YouTube `frame-src`, `frame-ancestors 'none'`, `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy: camera=(), microphone=(self), geolocation=()`. No HSTS on the LAN HTTP host, which is expected.

### 4.3 Pointers observed during the walk (for owning departments; not graded)

| # | Observation | Confidence | Suggested owner |
|---|---|---|---|
| P-1 | **Live is enabled but hidden from navigation.** `/api/features` (signed in) returns `live_channels_enabled: true, live_channels_ready: false`. The top bar, bottom nav, and drawer omit Live, yet `/live` renders a populated guide, and Admin Overview says Live is "Warming — Finish Setup". Members can only reach Live by URL. | Confirmed (live) | UX, Product, Ops |
| P-2 | **Unknown SPA URLs return a JSON 404** instead of the app's Not Found page. | Confirmed (live) | UX, Architecture |
| P-3 | **Title page a11y basics:** `document.title` stays generic ("Title · Projectionist") after load, and `document.querySelectorAll('main,[role=main]').length === 0` on `/title/movie/348`. | Confirmed (live, one page) | A11y |
| P-4 | **Inbox count mismatch.** The top bar accessible name says "Inbox, 12 unread"; the badge shows "12" on desktop and "9+" in the bottom nav. | Confirmed (live) | UX, A11y |
| P-5 | **The login page renders for a signed-in user** and, at 390px, shows the member bottom nav above the sign-in card. | Confirmed (live) | UX |
| P-6 | **Transient wrong empty state on Live** ("Not on the air yet — ask the owner to enable") flashes before data arrives. | Likely (seen once at 390) | UX |
| P-7 | **Admin "connected but no saved key" for Radarr/Sonarr** shows a status badge that can disagree with the stored config. | Confirmed (live copy) | Ops, Security |
| P-8 | **Very low-contrast text in captured states** (login "Sign in" heading and "Need an invite?", Explore rail titles, chat welcome heading at first paint). These may be fade-in animations caught mid-transition. | Suspected (verify with computed styles after animations settle, and with `prefers-reduced-motion`) | Design, A11y |
| P-9 | **Poster images blank in Explore and chat cards at capture time** (at 1440 and 390). | Suspected (may be lazy-load timing) | Perf, Design |
| P-10 | **Owner-destructive bulk "Delete" lives in the member-facing Search/Browse toolbar** (owner view). | Confirmed (live) | UX, Security |
| P-11 | **Naming drift:** admin rail says "Members", page h1 says "Household". Chat is "Curator" in the welcome copy, "The Professor" in the persona picker, and "CURATOR" on replies. | Confirmed (live) | UX, Content |
| P-12 | **Zero recorded usage on QA** ("0 chat turns · 0 plays" in 7 days) means QA data cannot validate engagement features. | Confirmed (live) | Growth |
| P-13 | **Chat composer disabled for several seconds on first load** while auth and session settle. | Confirmed (live) | Perf, UX |
| P-14 | **Help is about 100k characters** for owners in one route. | Confirmed (live: `innerText.length` ≈ 99,677) | Content, Perf |

---

## 5. Benchmarks

Web search was available. These are inspiration, not templates.

| Product | Why comparable | Patterns worth learning from |
|---|---|---|
| **[Seerr](https://seerr.dev/)** (Feb 2026 merger of Overseerr and Jellyseerr; [release notes](https://docs.seerr.dev/blog/seerr-release/)) | The household "discover and request" companion for Plex/Jellyfin/Emby | **Granular per-user permissions** and **default permissions for new users**; **request limits** per period; **import users from the media server** (or let anyone with server access sign in with defaults); **blocklist** for titles and tags managed by permitted users; installable PWA "near-native" mobile; many notification agents. Compare with SC-04, SC-06, and youth gating. |
| **[Tautulli](https://docs.tautulli.com/using-tautulli/notification-agents-guide)** | The owner's monitoring and newsletter tool for Plex | Notification agents built as **trigger + condition + template** (e.g. "playback start where user is not me"); **scheduled "recently added" newsletters** by cron, time window, and library, with self-hosted newsletter pages so emails stay small; grouping notifications by season/show to avoid floods. Compare with SC-17 and Admin → Newsletters. |
| **[Tunarr](https://github.com/chrisbenincasa/tunarr/) / [ErsatzTV](https://ersatztv.org/docs/clients/plex/)** ([comparison](https://www.bigiron.cc/guides/ersatztv-vs-tunarr-building-tv-channels-from-your-library)) | Virtual live channels from your own library (Projectionist builds on Tunarr) | Tunarr: first channel in 10–15 minutes, drag-and-drop lineups, filler, a web guide, in-browser streaming. ErsatzTV: duration-locked blocks and smart collections. Both note that **a 24/7 channel is a permanent transcode tenant**, and that "don't bother if your household is one or two people who are fine picking from a list". Compare with SC-13. |
| **[Trakt](https://roadmap.trakt.tv/changelog/rocket-trakt-product-update-summer-2026-edition) / [Letterboxd](https://support.letterboxd.com/hc/en-us/articles/15178711776911-What-notifications-does-Letterboxd-send)** | Taste tracking, lists, discovery | Trakt: **`/` or Cmd+K global search**, typed list positions instead of long drags, "Up to date" vs "Ended" progress views, premieres/finales filters. Letterboxd: **granular notification types per channel** (email vs push) and an opt-in weekly digest. Compare with Search, Lists, and Settings → Notifications. |
| **Plex discovery (own apps)** — from knowledge, not searched | The default alternative every member already has | Members can already browse, continue watching, and use watchlists in native Plex apps on every TV. Projectionist's in-browser Play and Live guide compete with that. Departments should test where Projectionist adds value beyond Plex itself (SC-14). |

---

## 6. Handoff for later batches

### 6.1 How to view the app

- **Live:** QA sidecar `http://10.10.1.202:8792` only (health 1.38.0). Use read-only HTTP. Do not start Watch/Play or tune a Live channel, because that opens a shared Plex session. Viewing `/live` is fine. Keep chat prompts to a few per department (they cost provider credit).
- **Session:** the shared Cursor browser was already signed in to a QA **owner** test account during Batch 1. Open your own tab; never sign out or switch accounts. No credentials are recorded here, and the credential file is off-limits.
- **Screenshot capture tip:** `browser_take_screenshot` timed out on a background tab. CDP `Page.captureScreenshot` worked; base64-decode the saved JSON. **Decode the exact file path returned by your call.** Other agents write to the same `~/.cursor/browser-logs/` folder, so "newest file" can be someone else's app. For 390px, use `Emulation.setDeviceMetricsOverride` with `deviceScaleFactor: 1`; a factor of 2 produced tiled duplicate captures. Clear the override when done.
- **Local (if a department needs it):** `DATA_DIR=./config PORT=<not 8788> PROJECTIONIST_SKIP_DOTENV=1 .venv/bin/python -m projectionist.web` from a checkout of `05274cf`. Single-owner mode by default (no login). e2e runs its own server on `:8799` (`AGENTS.md`).

### 6.2 What could not be run

- No anonymous walk: the browser session is owner-authenticated, so `/login` and `/join` were seen in a signed-in context. Public behavior was checked with `curl` (status codes, headers) and from code.
- No **member** or **youth** session. Role-specific nav and gating are mapped from code (`primaryNav.ts`, `appNavItems.ts`, `AdminLayout.tsx`, `youth/rating_gate.py`).
- No Plex PIN or OIDC sign-in, invite redemption, setup wizard, Watch/Play, Live tuning, lobby theater `:8791`, MCP server, mail send, or job triggers.
- No production data. QA usage counters are zero.

### 6.3 Areas later departments should examine closely (pointers, not conclusions)

1. **Product / UX:** Live visibility gating (`live_channels_ready` vs `live_channels_enabled`) and how members discover Live (P-1). `frontend/src/lib/liveNavReady.ts`, `projectionist/web/nav_bootstrap.py`.
2. **UX / Architecture:** SPA 404 handling and legacy redirect chains (P-2, §1.6). `projectionist/web/spa_routes.py`, `frontend/src/AppRoutes.tsx`.
3. **A11y:** per-route document titles and landmarks beyond the shell (P-3). `frontend/src/lib/routeTitles.ts`, `hooks/useRouteAnnounce.ts`, `TitleDetailPage.tsx`.
4. **Security:** the authorization model is a global auth middleware plus per-route `require_role`. Check the coverage of `require_role` across 128 `/api/admin/*` handlers and the object-level checks on chat/lists/reviews (Phase 2 "chat ownership"). `projectionist/web/auth.py:480-571`, `tests/test_phase2_trust_core.py`.
5. **Security / Privacy:** the new Security log and on-box attribution (Phase 6). `projectionist/security_audit.py`, `projectionist/telemetry/attribution.py`, `projectionist/web/owner_ops.py`.
6. **Privacy:** the per-member data footprint (memory entities, preference facts, watch sessions, telemetry) and what household members can see about each other; youth data. `docs/PRIVACY.md`, `library/db/_memory.py`, `_telemetry.py`.
7. **Architecture:** the 4,378-line `projectionist/web/app.py` (131 handlers still inline), 81 tables / 60 migrations in one SQLite file, and the single-process scheduler (SC-09–SC-11).
8. **Perf:** first-load latency of Chat (composer disabled) and Explore (posters), lazy chunks from Phase 5, `static_assets.py` caching headers, Help page size (P-9, P-13, P-14).
9. **Design:** contrast of animated headings and light text in Lights Up; the token coverage of the 17 CSS partials after the Phase 4 rewrite (P-8). `frontend/src/styles/01-tokens.css`.
10. **Ops:** the Admin Overview "connected but no saved key" status honesty, the Monday pass design, and the secrets-key/backup nags (P-7). `frontend/src/components/OwnerOpsOverview.tsx`, `projectionist/web/owner_ops.py`.
11. **Growth / Content:** naming consistency (Curator / The Professor / Members vs Household) and idiomatic copy for non-native readers (P-11, SC-20). Comms cadence across digest, letter, newsletter, nudges, and whispers (SC-17).
12. **Product:** whether destructive owner actions belong on shared consumer surfaces (P-10, SC-15), and whether gamification and Live earn their complexity (SC-13, SC-16).
