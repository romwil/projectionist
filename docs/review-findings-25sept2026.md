# Post-1.36.0 hardening — sprint guide

Working queue after Hub `romwil/projectionist:1.36.0`. Next agent: read [Vigilance](#vigilance) first, then pick the highest **open** High that is not already in flight, file-lock the files listed, implement, mark the finding done. Do not re-read the review chat.

Authoritative tree: `origin/release/1.36` @ `a5cf319` (v1.36.0). Citations below are verified there with `git show` / `rg`. Use `user-codegraph` first for symbol line numbers (`codegraph_explore` / `codegraph_node`). Do not `codegraph init` in worktrees. [PR #43](https://github.com/romwil/projectionist/pull/43) hooks `codegraph sync` after merge/commit/checkout when `.codegraph/codegraph.db` exists.

## How to use

1. Start **Thread A**. Inside a thread, order is Critical → High → Medium. This register has **no Criticals**. Slice 1 is already in flight — see [Vigilance](#vigilance).
2. File-lock before you edit so A/B/C/D can run in parallel. If two threads list the same file, they are **not** parallel — see [Locks](#locks).
3. Keep `curatorx_session` and compose/CA `${CURATORX_*}` interpolation. Never prod-rollout from this doc. UI proof is QA `:8792` only — never prod `:8788`, never smartmap `:8790`.
4. Defensive security only: no exploit PoCs, no pentest payloads, no weaponized setup-mode repros.
5. Gate merge with tests named on the finding. `clear_rate_limits()` in auth-heavy suites.

## Locks

| Thread | Owns | Do not overlap |
|--------|------|----------------|
| **A** (first) | `projectionist/web/auth.py`, `setup_mode.py`, `setup_routes.py` (allowlist / WAN / status gate), `frontend/src/components/MessageText.jsx`, chat stream in `app.py` + `frontend/src/api/client.js`, `jobs.py` **traceback only**, `webhooks.py`, Identify path in `investigate_routes.py` | — |
| **B** | `jobs.py` **`start_sync` single-flight**, `app.py` `library_stats` + `POST /api/library/sync`, `_library_query.py`, `acrcloud.py` identified-key cap, `rate_limit.py`, `whisper.py` pick, WAL `Database.close()` | **`jobs.py` with A** — same file (traceback vs single-flight). Sequential, or one owner lands both. `app.py` hunks differ from A (stats/sync vs stream/features) — rebase-aware, not a lock. |
| **C** | `ConfigPage.jsx` polls, `LibrariesSection.jsx` Investigate poll, `App.jsx` `listJobs` interval, Identify honesty copy (`episodeInvestigate.js` + Libraries UI) | Not `app.py`. Honesty copy stays frontend; B owns `acrcloud.py`. |
| **D** (waits) | Brand strings (except cookie + compose twins). Then real extract of `auth_routes.py` / `setup_routes.py`. Later `library_routes.py` + `chat_routes.py` from `app.py` | **Not parallel with A** on `setup_routes.py` / `auth.py` hunks, or on `app.py` chat/library carves. First slice can be CuratorX strings in `spa_routes.py`, `_write_serializer.py`, e2e scripts — those do not collide with A. |

`jobs.py`: A = failed-sync traceback in `_run_sync`. B = `start_sync` refuse-if-running. One PR or A-then-B.

`app.py`: A owns `GET /api/chat/stream` (~3862) and `_features_payload` (~1176). B owns `/api/library/stats` (~1377) and `/api/library/sync` (~1369). D carves those later — D waits until A/B land.

## Vigilance

Hard constraints from Will — later threads cannot miss these.

1. **P4-HIGH-01 / chat stream.** Native `EventSource` cannot POST. The client already uses `fetch` + reader. Reconnect/fallback must **not** construct `EventSource` after a dropped socket.
2. **Thread C polls.** HDMI / kiosk Chromium often will not fire `document.hidden` on standby. Idle backoff is **8–10s even when visibility is unreliable** — never hammer ASGI from a parked wall display. `document.hidden` pause is extra, not sufficient.
3. **WAL.** `PRAGMA wal_checkpoint(PASSIVE)` is the required close path. No `TRUNCATE` under live readers.
4. **Perimeter.** UI proof exclusively QA `:8792`. Never prod `:8788`. Never smartmap `:8790`.
5. **Thread D parked** until A and B have cleared `app.py` and `jobs.py`. Sequence: A strips jobs traceback before B single-flight; A patches features + chat stream in `app.py` before D carves routes.
6. **Now in flight.** Thread A slice 1 = **P3-HIGH-01 + P3-HIGH-02 only**.

## Scope and product locks

- **1.36 LICENSE + `pyproject.toml` are MIT.** [PR #42](https://github.com/romwil/projectionist/pull/42) (`feat/agpl-3.0-license`) is **open** — AGPL-3.0-only for *new* releases. Review license/docs/CA on that PR. **Do not couple AGPL to this sprint.**
- Python `CURATORX_*` dual-read is already gone (1.34). **Keep** cookie `curatorx_session` (`projectionist/web/session_tokens.py:16`) and compose/CA `${CURATORX_*}` twins (`docker-compose.yml`, `docker-compose.unraid.yml`, `unraid/curatorx.xml`). Do not restore `X-CuratorX-Webhook-Secret`.
- H1 extract tests only assert `register_*` exists and `/chat` is on the SPA router — they do not prove domain moved.
- `app.py` is still 6,080 lines. `App.jsx` is 1,664 (chat orchestration; `ChatWorkspace` is presentational). `ConfigPage.jsx` is 2,998 after Libraries carve-out.

## Severity × thread

| ID | Sev | Thread | One-line |
|----|-----|--------|----------|
| P3-HIGH-01 | High | A | Auth middleware fail-opens when `get_job_manager()` raises |
| P3-HIGH-02 | High | A | SETUP_MODE skips WAN interlock; unauthenticated plex/tmdb tests on allowlist |
| P3-HIGH-03 | High | A | Assistant markdown hrefs not sanitized |
| P4-HIGH-01 | High | A | Chat stream puts full message on the query string |
| P3-MED-01 | Med | A | Failed sync persists traceback in `GET /api/jobs` — **done** |
| P3-MED-02 | Med | A | `ChatRequest.message` / stream query unbounded (pair with P4-HIGH-01) — **done** (1.36.1) |
| P3-MED-03 | Med | A | Webhook `compare_digest` not length-stable — **done** |
| P3-MED-04 | Med | A | Identify test `path` has no media-root allowlist — **done** |
| P4-MED-01 | Med | A | Unauthenticated `/api/features` leaks household topology — **done** |
| P4-MED-04 | Med | A | `/api/setup/status` has no owner gate — **done** |
| P2-HIGH-01 | High | B | `/api/library/stats` materializes every `library_items` row — **done** |
| P2-HIGH-02 | High | B | HTTP `start_sync` is not single-flight — **done** |
| P2-MED-01 | Med | B | `_identified_keys` grows for process lifetime — **done** |
| P2-MED-02 | Med | B | Rate-limit buckets never evicted — **done** |
| P4-MED-02 | Med | B | Whisper seeds from household `last_viewed_at` — **parked** |
| WAL close | Med | B | Add `PRAGMA wal_checkpoint(PASSIVE)` on `Database.close()` — **done** |
| P2-HIGH-03 | High | C | Config / Libraries / Chat poll every 2–5 s while parked — **done** |
| P4-MED-03 | Med | C | Identify has no owner-facing leaves-the-LAN sentence — **done** |
| P1-HIGH-01 | High | D | `auth_routes` / `setup_routes` re-import `app.py` |
| P1-HIGH-02 | High | D | Next feature in `app.py` re-welds the god file |
| P1-MED-01 | Med | D | User-visible CuratorX strings (except cookie + compose) |
| P1-MED-02 | Med | D | ConfigPage still owns Live + job polls; App.jsx still owns chat state |

Closest mechanical patches (fail-closed auth, markdown hrefs, stats `COUNT`, sync single-flight) still need tests. Land as Thread A/B PRs — not a drive-by on this file.

---

## Thread A — perimeter (first)

### High

#### P3-HIGH-01 — fail-closed auth when DB is down

- **Where:** `projectionist/web/auth.py:437-440` (`multi_user_api_auth_middleware`). `get_job_manager().db` excepts then `return await call_next(request)`.
- **Do:** On exception, allow `/api/health`, `/api/features`, and non-`/api/` only; every other `/api/*` returns 503 `{"detail": "Service unavailable"}`. Log `auth middleware: database unavailable`.
- **Tests:** `tests/test_api_authz.py` — force `get_job_manager` to raise; `/api/library/stats` is 503, `/api/health` is 200.

#### P3-HIGH-02 — WAN interlock in SETUP_MODE

- **Where:** `auth.py:442-447` returns before `wan_interlock_blocks` (`:458-463`). Allowlist `setup_mode.py:34-43` includes unauthenticated `POST /api/setup/test/plex` and `test/tmdb`. Handlers `setup_routes.py:297` / `:352` use `require_role("owner")`, which is a no-op when `multi_user_enabled` is false (`auth.py:504-508` then `bootstrap_owner`). `POST /api/setup/commit` is the same first-owner window.
- **Do:** Inside `is_setup_mode`, run `wan_interlock_blocks(request, multi_user_enabled=False)` first (same allow-health/features pattern as ACTIVE). Drop plex/tmdb test routes from `SETUP_API_ALLOWLIST_EXACT` unless handshake classification is LAN. Require `PROJECTIONIST_OWNER_PASSWORD` before `commit_setup` accepts a WAN / `public_failsafe` peer. Do not publish a repro.
- **Tests:** setup handshake WAN case — interlock 403 on test/plex; LAN still works. Automat prod 1.36.0 is already ACTIVE; this is next CA install / setup reset.

#### P3-HIGH-03 — markdown href allowlist

- **Where:** `frontend/src/components/MessageText.jsx:15-31`. `https?:` gets `noreferrer`; every other scheme is a raw `<a href>`.
- **Do:** Allow `https?:`, in-app `title`/`library`, and `#` only; render other schemes as text. Prefer `rehype-sanitize`. Do not add `rehype-raw`.
- **Tests:** `MessageText` unit — `javascript:`, `data:`, `vbscript:` render as text. No live payloads.

#### P4-HIGH-01 + P3-MED-02 — chat stream POST + 8k cap

- **Where:** `app.py:3862` `GET /api/chat/stream?message=`. Client `frontend/src/api/client.js:1057-1061` (`sendChatStream` puts `message` on `URLSearchParams`). Schema `projectionist/models/schemas.py:112-116` — `ChatRequest.message` has no `max_length`.
- **Do:** Add `POST /api/chat/stream` with `message: Field(min_length=1, max_length=8000)` (same on `ChatRequest`). Client already uses `fetch` + stream reader — switch to POST JSON. Keep GET one release as 410 + changelog, then delete.
- **Tests:** POST stream 200 with body; GET 410; 8001-char message 400.

### Medium

#### P3-MED-01 — no traceback in job API

- **Status:** Done — merged on `release/1.36` via #53. `job.summary = {"failed": True}`; `to_dict()` strips any leftover `traceback` key.
- **Where:** `jobs.py:376-377` (`job.summary` stores `traceback.format_exc()`). Exposed by `app.py:1354-1357` `GET /api/jobs` then `job.to_dict()`.
- **Do:** `job.summary = {"failed": True}`; keep `friendly_job_error` on `job.error`. `logger.exception` server-side. Never put traceback in `to_dict()`.
- **Lock:** same file as B `start_sync` — sequential or one owner.

#### P3-MED-03 — webhook digest length-stable

- **Status:** Done — merged on `release/1.36` via #54. SHA-256 + `compare_digest`; empty secret/header still 401.
- **Where:** `projectionist/web/webhooks.py:179` — `secrets.compare_digest(provided, secret)` raises on length mismatch then 500.
- **Do:** Reject empty secret/provided as 401. Compare SHA-256 digests of both sides so `compare_digest` is fixed-length. Keep rejecting empty secret. Do not restore `X-CuratorX-Webhook-Secret`.

#### P3-MED-04 — Identify test path roots

- **Status:** Done — merged on `release/1.36` via #54. Roots = Plex / Radarr / Sonarr / `tv_root` / `movies_root` / `/tv` / `/movies`. `file_id` prefers snapshot `resolved_path`. Raw path ignored unless it matches a snapshot row.
- **Where:** `investigate_routes.py:234-250` (`identify_test`). Raw `payload.path` goes to `test_identify_clip` (`acrcloud.py:378-384`) if it is a readable file. Stills GET is already allowlisted (`:256-269`).
- **Do:** Resolve against configured media roots (Plex section paths / Radarr/Sonarr roots). Reject unless `resolved.is_relative_to(root)`. If only `file_id`, keep snapshot-row resolve (already implemented). Ignore raw `path` unless it matches a snapshot row. Owner-session only; no exploit write-up.

#### P4-MED-01 — shrink unauthenticated `/api/features`

- **Status:** Done — merged on `release/1.36` via #54. Guest payload also keeps `features.access_requests_enabled`. `_features_payload` only; `library_stats` untouched.
- **Where:** `app.py:1176` `_features_payload`; `app.py:1286` `GET /api/features`. `authenticated=False` still emits `household_domain`, `live_channels_ready`, `trust_proxy_headers`, Seerr flags, and `youth.max_content_rating` (`:1254-1262`).
- **Do:** When `authenticated=False`, return only `features.multi_user_enabled`, `auth_methods`, `setup_state`, `authenticated: false`, `user: null`.

#### P4-MED-04 — owner-gate `/api/setup/status`

- **Status:** Done — merged on `release/1.36` via #54. `Depends(require_role("owner"))`. Members get Radarr/Sonarr readiness from `features.arr`.
- **Where:** `setup_routes.py:67-69` — `setup_status()` has no `require_role`. Builder `setup.py:506` (`build_setup_status`) reports whether Plex/Radarr/Sonarr/TMDB/LLM are configured.
- **Do:** `Depends(require_role("owner"))` on `setup_status`. Members already get readiness from `/api/features`.

---

## Thread B — storage and concurrency

### High

#### P2-HIGH-01 — `library_stats` via COUNT(*)

- **Status:** Done — merged on `release/1.36` via #56. `counts = db.library_counts()`; `total` maps from `items`. Other `all_library_items()` callers unchanged.
- **Where:** `app.py:1377-1382` — `db.all_library_items()` then counts in Python. `all_library_items` is `_library_query.py:167`. The COUNT helper already exists: **`library_counts()`** at `_library_query.py:156` (not `library_item_counts` — that name is not on this tree).
- **Do:** `counts = db.library_counts()`; map `total` / `movies` / `shows` from those COUNTs. Keep `last_sync`, cached Plex name, `knowledge_coverage`, `_sanitize_library_payload`.

#### P2-HIGH-02 — single-flight `start_sync`

- **Status:** Done — merged on `release/1.36` via #56. Under `_lock`, return the existing queued/running `library_sync` job as HTTP 200 (same job dict; frontend `api()` throws on 409).
- **Where:** `jobs.py:173-182` — every `POST /api/library/sync` (`app.py:1369`) starts a new UUID + daemon thread. Scheduler already refuses a second run (`jobs.py:422-423`). Investigate / Sonarr-missing already single-flight via `admin_execution.store.begin`.
- **Do:** Under `_lock`, if a `library_sync` job is `queued`/`running`, return it. Return 200 with the existing job (or 409 — match Sonarr missing).
- **Lock:** same file as A P3-MED-01.

### Medium

#### P2-MED-01 — cap `_identified_keys`

- **Status:** Done — merged on `release/1.36` via #56. `OrderedDict` cap 4096; oldest evicted. Tests still call `reset_identify_throttle_for_tests`.
- **Where:** `acrcloud.py:52` (`set`) and `:417` (`_claim_file` adds forever). `reset_identify_throttle_for_tests` already clears (`:409-414`).
- **Do:** `OrderedDict` cap 4096; evict oldest when over. Tests still call reset.

#### P2-MED-02 — evict rate-limit buckets

- **Status:** Done — merged on `release/1.36` via #56. After `check()`, if `len(_hits) > 4096`, drop empty keys then oldest buckets. Do not apply the caller’s window cutoff to other buckets.
- **Where:** `rate_limit.py:19` — `_hits` keyed `(bucket, client_ip)` for process lifetime. Homelab-default is fine; Automat + `trust_proxy_headers` is not bounded.
- **Do:** After `check()`, if `len(self._hits) > 4096`, drop empty-after-cutoff keys, else evict oldest stale buckets. Same lock.

#### P4-MED-02 — whisper from per-user watch state

- **Status:** Parked (Thread B). Week filled; seed still household `last_viewed_at`. Do not implement in this cut.
- **Where:** `whisper.py:165-184` `_recent_seed` — household `library_items.last_viewed_at`. `:201` unwatched set is household `view_count=0`. Why-string names the member and that seed (`:23-26`). Inbox is correctly `user_id`-scoped.
- **Do:** Seed and unwatched set from `watch_tracker` / per-user view state for `user_id`. If none, cluster-only fallback — never another member `last_viewed_at`. Keep notification delivery scoped to `user_id`. Youth already excluded.

#### WAL close (no finding ID)

- **Status:** Done — merged on `release/1.36` via #56. `PRAGMA wal_checkpoint(PASSIVE)` after serializer shutdown. Never `TRUNCATE`.
- **Where:** `projectionist/library/db/_schema.py:71` `Database.close()`. Writer-serializer + WAL + `wal_autocheckpoint=1000` already exist.
- **Do:** `PRAGMA wal_checkpoint(PASSIVE)` on close so Unraid appdata does not accumulate `-wal` across restarts. Do not TRUNCATE under live readers. Do not Repair Plex. Do not touch smartmap `:8790`.

---

## Thread C — client polls and honesty

### High

#### P2-HIGH-03 — poll only the visible busy section — done

- **Where:** `ConfigPage.jsx:833` sync jobs 2 s (`[showWizard]` only — all `/admin/*`). `:854` Sonarr missing 2 s. `:885` Radarr register 2 s. Live `:705` is already gated to `live-channels`/`overview` while busy. `LibrariesSection.jsx:615` Investigate 2 s (`[]`). `App.jsx:747` `listJobs` every 5 s forever.
- **Do:** Poll only the visible section, only while busy, backoff 8–10 s when idle, pause on `document.hidden`. Drop chat-shell `listJobs` unless a sync toast is open.
- **Landed:** Done — merged on `release/1.36` via #55. `visibleBusyPoll.js` (2s busy / 8s idle / hidden pause). Config libraries polls, Investigate, and chat `listJobs` (toast-only). Live poll depends on a busy boolean; Sync keeps busy in a ref.

### Medium

#### P4-MED-03 — Identify leaves-the-LAN copy — done

- **Where:** Vision copy is honest — `frontend/src/lib/episodeInvestigate.js:3-4` `STILLS_LEAVE_LAN`, surfaced at `LibrariesSection.jsx:716`. Identify uploads a clip to `identify-*.acrcloud.com` (`acrcloud.py:309` `identify_file`). Host allowlist and key masking are already correct.
- **Do:** Add `IDENTIFY_LEAVES_LAN` next to `STILLS_LEAVE_LAN` (match `IDENTIFY_CLIP_SECONDS`; a miss does not rename files). Surface on Identify settings + test controls. Keep test `renamed: False`.
- **Landed:** Done — merged on `release/1.36` via #55. `IDENTIFY_LEAVES_LAN` + Identify settings / **Test Identify** on Admin → Libraries. Test honesty stays `renamed: false`.

Verify Investigate / Rematch / Whisper / House on QA `:8792` only (390-wide + desktop).

---

## Thread D — cruft and decoupling (after A)

### High

#### P1-HIGH-01 — make auth/setup routes real modules

- **Where:** `auth_routes.py:15` and `setup_routes.py:14` — `import projectionist.web.app as app_mod`, then bind `_db`, `_settings`, payloads, testers, `require_role`. Circular import survives because registration runs after `app` exists.
- **Do:** Inject factories like house (`house_routes.py:14-32`): `register_*(app, *, db_factory, settings_factory)`. Move route-local models to `auth.py` / `setup.py` (or `web/deps.py`). Stop `import projectionist.web.app`. Gate: `rg "import projectionist.web.app" projectionist/web/*_routes.py` is empty.
- **Wait:** A owns `setup_routes.py` allowlist/status first.

#### P1-HIGH-02 — carve library + chat from `app.py`

- **Where:** `app.py` still implements jobs (`:1354`), library sync/stats (`:1369-1377`), chat (`:3370`, stream `:3862`), plus title/person, actions, syllabus, taste, YIR, Sonarr missing, Radarr register, purge, telemetry, ~40 feed routes. Lifespan still starts sync scheduler, stream-warm, idle scheduler, live-session poller, facet warmup, watch-identity repair.
- **Do:** Operational split: `library_routes.py`, `chat_routes.py` (optionally `admin_jobs_routes.py`) using the house factory pattern. Do not add another `register_*` that imports `app_mod`. Leave lifespan in `app.py` as the composition root.
- **Wait:** A/B `app.py` hunks land first. Do not grow `live_channels_routes.py` (73 KB) or `agent/tools/__init__.py` (178 KB) in-place.

### Medium

#### P1-MED-01 — brand leftovers

User-visible / ops-visible CuratorX on a shipped Projectionist tag. Cookie and compose twins stay.

| File | Line | Do |
|------|------|----|
| `app.py` | 443 | Shutdown log to Projectionist |
| `app.py` | 462-463 | `FastAPI(title="Projectionist", ...)` |
| `spa_routes.py` | 27 | Fallback heading to Projectionist |
| `_write_serializer.py` | 51 | Thread name `projectionist-db-writer` |
| `auth_routes.py` | 75-77 | Memory export filename + header (also `:121` `.md`) |
| `scripts/start-e2e-server.sh` / `.mjs`, `scripts/dev-server.ps1` | print strings | Projectionist E2E — not CA-facing |

Do not rename `SESSION_COOKIE_NAME` or drop `${CURATORX_*}` without a CA/release note. First D slice can be these strings only — no collision with A.

#### P1-MED-02 — Config / App composition

- **Where:** `ConfigPage.jsx` (2,998) still owns Live Channels status/lifecycle/publish/continuity, Sonarr missing, Radarr register, wizard residue. `App.jsx:1536` renders `ChatWorkspace` with orchestration props — presentation only.
- **Do:** After C gates polls, move remaining job effects into the sections that display them. Keep `App.jsx` as hook composition (`useChatSession`) — do not grow it. Presentation models (job percent, live craft options) stay in the page, not the API client.

---

## Architecture (short)

Real modules: `spa_routes`, `investigate_routes`, `rematch_routes`, `whisper_routes`, `house_routes`, `LibrariesSection`, `ChatWorkspace`, `AppRoutes`. Leaky facades: `auth_routes.py` / `setup_routes.py`. Investigate/rematch/whisper lazy-import domain packages but all bind `get_job_manager()` — `house_routes` factory injection is the pattern to copy.

## Already hardened (do not redo)

Ingress: direct peer only; `X-Forwarded-*` ignored unless `trust_proxy_headers`; Docker `172.16/12` is not LAN on `0.0.0.0`; RFC 6598 handled without `is_private`. Handshake body clamp 64 KiB. Session HMAC + `compare_digest` + jti revocation + epoch; dummy PBKDF2 on unknown local user. Settings mask. Stills path allowlist + resolve-under-root. ACRCloud host allowlist `identify*.acrcloud.com`. SQLite write serializer (queue 128) + WAL + `wal_autocheckpoint=1000`. Jobs state 5 MiB cap. New 1.36 admin routes are `require_role("owner")`. Whisper inbox is `user_id`-scoped. Youth history scrub on thread reopen. Stills-leave-LAN copy exists.
