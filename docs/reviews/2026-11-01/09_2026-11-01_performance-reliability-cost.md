# 09 · Performance, reliability, and cost — 2026-11-01

Reviewed `05274cf` (tag `v1.38.0`) against QA `http://10.10.1.202:8792` only. Measurements below are from this pass unless noted. No Watch, no Live tune, no chat prompt, no SSH, no prod.

## Part A: Conclusions & findings

### 1. Bottom line

**Grade: C+.** On a LAN the app is already quick: health answers in about 100ms, the shell is gzip-compressed, and content-addressed JavaScript is cached for a year. The single most important fix is operability, not a faster query: there is no metric for the write queue, no request latency, and no scheduled backup, so a bad Saturday becomes a guess plus a zip the owner remembered to download (PERF-001, PERF-002). The single most important thing to protect is the pair of guards that keep a slow library from taking down first paint: `/api/health` does not touch SQLite, and `/api/library/query` hops off the event loop (PERF-003, PERF-004).

### 2. Key conclusions

1. **The first load is dominated by one JavaScript file, and the server already does the cheap things right.** The production build's entry chunk is `index-CSQsR6Mb.js` at 1,054.11 kB (gzip 321.43 kB). QA served it gzip-encoded, 320,588 bytes on the wire, with `Cache-Control: public, max-age=31536000, immutable`, in 0.46s from this laptop. CSS was 352.05 kB (gzip 57,525 bytes on the wire) in 0.28s. Repeat visits on a real browser should not re-download these. First visits and low-power devices still parse a megabyte of script (PERF-005, PERF-006).

2. **Health is fast because it is shallow, and that is deliberate.** `GET /api/health` returned `{"status":"ok","version":"1.38.0"}` in 97–99ms and the auth middleware skips SQLite for that path and for non-API GETs. A database that is locked for the 30s busy timeout will not move this number. `/api/ready` exists and also avoids the movie library, but nothing in this pass showed a probe using it (PERF-003, PERF-007).

3. **The library browse path was already pulled off the loop. Chat was not.** `library_query_endpoint` is `async` and wraps the query in `run_db`, with a comment that the main app and the theater share a loop. `POST /api/chat` is also `async` and calls `ensure_chat_session` and `set_thread_persona` on the loop before it awaits the model (PERF-004, PERF-008).

4. **Heavy idle tasks are mostly off the loop, and the heaviest one is the exception on paper.** Twenty-plus task modules pass `off_loop=True`. `semantic_embeddings.py` calls itself the heaviest idle task and never sets the flag, so it keeps the default `off_loop=False` and runs on the process loop (PERF-009).

5. **You cannot diagnose this box in 15 minutes from telemetry, and you cannot restore what you never practiced.** Logs rotate at 5 MiB with three backups and can redact tokens; JSON formatting is opt-in. `write_queue_stats()` exists and has no caller. Backups are an owner-downloaded zip built in memory, with no scheduler task and no restore test in the repo (PERF-001, PERF-002, PERF-007).

6. **LLM cost is bounded per call and unbounded per household.** Provider calls ask for `max_tokens` 4096 and use a 120s HTTP timeout. Migration 40 added an `llm_usage` table. This pass found no monthly budget that refuses a call when the table gets large (PERF-011).

7. **One process is still the availability story.** Web, idle scheduler, Live publish, and the optional theater port share a fate. That is acceptable for a household only while the off-loop and health-bypass guards stay intact (PERF-012, SC-09).

### 3. Foundations challenged

| Assumption | Evidence for | Evidence against | Verdict | Cost of change | Rationale |
|---|---|---|---|---|---|
| SC-09 One process is enough | Health stayed under 110ms while the box was up; threadpool and `off_loop` exist | A Live publish wedged in-process takes chat with it; no second replica | Keep | XL | A second container does not create the missing backup or metrics. Spend the quarter on those. |
| SC-10 SQLite is fast enough | WAL, 30s busy timeout, dedicated writer, library query off the loop | Busy timeout is 30s; a stuck writer stalls any sync handler that does touch the DB | Keep | XL | Measure `write_queue_stats` before replacing the database (PERF-001). |
| SC-11 Idle scheduling (15 min quiet) is right | Heavy tasks yield the box to people who are chatting | Embeddings can run for a long time once idle starts; default flag leaves them on the loop | Change | S | Keep the idle model. Set `off_loop=True` on the heaviest tasks (PERF-009). |
| SC-12 Deep library knowledge is worth the compute | Trickle caps in `semantic_embeddings.py` | No dollar or token budget tied to that trickle (PERF-011) | Investigate | M | Keep the feature. Put a visible cap on it before adding more enrichment. |
| SC-14 In-browser playback | `hls.js` is a direct dependency; player components are among the largest TSX files | This pass did not start playback, so cost is from the bundle graph only | Investigate | M | Do not tune playback from a guess. Confirm the player chunks stay off the chat entry path. |
| SC-07 LLM is optional but central | Chat is the home page when a provider is set | Each turn is a paid 120s call with no household ceiling | Change | M | Keep chat. Add a ceiling the owner can see (PERF-011). |

### 4. If we built it today

The same single container. A tiny status module from day one: request latency histogram, SQLite writer queue depth, last successful backup, LLM tokens this month. Health stays shallow; a separate ready check pings the writer with a 50ms timeout. The entry bundle would be split so chat does not download the admin page. Backups would be a nightly sqlite `backup` to a second file, plus a documented restore that CI actually performs on a fixture.

The gap is not the framework. Gzip, immutable caching, `run_db`, and `off_loop` are already the right mechanisms. What is missing is the gauge and the restore. Closing that is worth it. Rewriting the API in another language is not.

### 5. Findings by surface

**Public.** The HTML shell is 2,210 bytes uncompressed, 888 bytes on the wire with gzip, about 107ms to first byte. Favicon is 252 bytes with no cache header (PERF-013). Unknown paths are not a performance issue. Grade: **B.**

**Consumer.** Library query is designed not to block the loop (PERF-004). The entry script is the cost of opening Chat (PERF-005). This pass did not send a chat, so time-to-first-token is unmeasured (PERF-008). Grade: **C+.**

**Owner.** Settings saves go through the writer thread, which is the right queue, and nothing exports that queue's depth (PERF-001). Config is inside the big entry chunk rather than a separate lazy graph this pass did not fully attribute; the build log shows many route chunks, so the opportunity is real (PERF-005). Grade: **C+.**

**Admin.** Task runs are logged in application logs, not in a metric an alert can read. The snapshot download is the backup (PERF-002). Grade: **C.**

### 6. Findings by theme

**Front end.** Best: gzip on the middleware (`minimum_size=500`) and `immutable` on hashed `/assets/*`, confirmed live. Worst: a 1,054 kB entry chunk. Direction: keep the cache policy, split the entry so admin and Live players are not in the chat graph (PERF-005, PERF-006).

**Back end.** Best: `run_db` on library query, health bypass, writer thread. Worst: chat's synchronous session writes on an async route, and embeddings left on the loop by default (PERF-004, PERF-008, PERF-009).

**Reliability.** Best: corrupt settings fail closed with 503 (settings path, not re-argued here). Worst: backup is a manual zip held in a `BytesIO`, and ready is not the probe anyone is required to use (PERF-002, PERF-007).

**Observability.** Best: a redacting formatter and a rotating file under the data directory. Worst: no histograms, and `write_queue_stats` is dead code from an operator's point of view (PERF-001, PERF-007).

**Cost.** Best: per-call `max_tokens` and trickle caps on embeddings. Worst: no household ceiling (PERF-011).

### 7. Stop doing

- Stop adding new `async def` routes that call SQLite before their first `await` (PERF-008).
- Stop treating `GET /api/health` as proof the database is up (PERF-007). Keep the endpoint shallow; point operators at `/api/ready` or a real check.
- Stop adding enrichment tasks that spend provider tokens without a counter the owner can see (PERF-011).
- Do not add a second process or a second database this quarter. The measurements do not justify it (PERF-012).

### 8. Strengths worth protecting

- **Health does not take the SQLite busy lock.** The middleware comment names the failure it prevents: a 30s busy timeout stalling first paint, including About (`auth.py:465-469`). Do not "enrich" `/api/health` with a catalog count.
- **Hashed assets are immutable and compressed.** QA response headers for the entry script and the CSS matched the build. Do not put `no-store` on `/assets/*`.
- **Library query yields the loop.** `run_db` around `query_library` is the pattern. Copy it; do not inline the query back onto the loop for "simplicity" (PERF-004).
- **Idle work has an off-loop switch and a heartbeat.** `engine.py` runs `off_loop` tasks in a worker thread via `asyncio.to_thread`. New heavy tasks must set the flag (PERF-009).

### 9. Risks of inaction

Within six months an owner will notice Chat stalling while an embedding or Live publish runs, and the only evidence will be a text log that rotated past the incident (5 MiB times four files). A disk failure will meet a household whose last backup is whatever zip someone downloaded, with no one having restored it. LLM spend will move with library size because enrichment has a trickle cap but not a currency cap. None of these show up in the 100ms health check.

### 10. Recommended direction

Now: put `off_loop=True` on semantic embeddings, move chat's session writes off the loop, and expose three numbers on an owner-only status route (writer queue depth, last backup time, LLM tokens this month). Next: a nightly backup file plus a restore drill in CI using a fixture, and a bundle budget that fails the build if the entry chunk grows past 1.2 MB uncompressed. Later: only if queue depth says so, consider a separate process.

Ninety-day success: entry chunk at or under today's 1,054 kB, `/api/ready` or the status route shows writer health, one restore drill has been run and written down, and a chat turn cannot block `/api/health` (health already skips SQLite; the chat fix keeps the loop free for everything else).

### 11. Scorecard

| Surface | Speed | Resilience | Observability | Cost | Overall |
|---|---|---|---|---|---|
| Public | 4 — small gzip HTML, fast health | 3 — health ignores the database | 2 — status only | 5 — no third-party script on the shell | 4 |
| Consumer | 3 — query is off-loop; 1 MB JS | 3 — chat can still block the loop | 2 — no latency metric | 2 — LLM uncapped | 3 |
| Owner | 3 — settings writer exists | 2 — backup is a download | 2 — queue depth unread | 3 — enrichment trickle only | 2 |
| Admin | 3 — tasks are isolated when flagged | 2 — no practiced restore | 2 — logs only | 3 — admin LLM calls share the cap gap | 2 |

Scores are 1–5. Overall grade C+ is the operability drag on an otherwise decent LAN speed.

---

## Part B: Detailed findings

### 12. Scope and method

Code at `05274cf` via `/tmp/review360-05274cf`. Live probes were unauthenticated `curl` against `http://10.10.1.202:8792` on 2026-11-02 around 18:48 UTC, with `Accept-Encoding: gzip, br`. No authenticated library timing, no chat (provider credit), no playback, no Live tune. Lighthouse was not run; it is not assumed installed, and this pass did not install it.

Frontend production build reused `/tmp/review360-perf-root` (a full checkout, so `PrivacyPage.tsx` could import `docs/PRIVACY.md`). A frontend-only copy cannot build. Build time in the log was 2.44s. Vite reported the chunk sizes quoted below.

Not measured: disk latency on the Unraid host, WAL file size, CPU during embeddings, time-to-first-token, and a restore. Host SSH was out of scope.

### 13. Strengths

### PERF-003: Keep /api/health off SQLite

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Public |
| Persona(s) | Returning consumer, platform admin |
| Category | Resilience |
| Severity | High |
| Impact | 5 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 7.5 |
| Verdict | Protect |
| Dependencies | none |
| Labels | health, sqlite |

**Evidence:** `05274cf:projectionist/web/auth.py:465-469` returns before any database open when `GET /api/health` or the path is not under `/api/`. `05274cf:projectionist/web/app.py:1317-1319` returns `{"status":"ok","version"}` only. QA: `code=200 ttfb=0.098810 total=0.098920 size=34`.

**Current state:** The probe stays fast when the library file is busy. The comment records the old failure: a 30s `SQLITE_BUSY_TIMEOUT_MS` stalling first paint.

**Root cause:** Health used to share the database lock with readers that paint the UI.

**Recommendation:** Leave the body as status and version. Put any database ping on `/api/ready` or a new owner status route, with a timeout under 100ms, and document which URL the container should use for "process is up" versus "database accepts work".

**Rationale:** A health check that takes the busy lock will restart a container that is merely busy, which makes an incident worse. Rejected: deleting `/api/ready` and enriching health. The split is the design.

**User story:** As an owner, I want the container to stay up while a sync holds the database so the UI can tell me it is busy instead of restarting.

**Acceptance criteria:**
- [ ] `/api/health` source contains no database call.
- [ ] A test holds a write transaction and asserts health still returns in well under a second.

**Success metric:** Health p99 on the LAN stays under 200ms during a library sync.

**Validation:** The middleware branch and the curl timing above.

### PERF-004: Keep library query off the event loop

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Consumer |
| Persona(s) | Returning consumer |
| Category | Back-end performance |
| Severity | High |
| Impact | 4 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 6.0 |
| Verdict | Protect |
| Dependencies | none |
| Labels | asyncio, library |

**Evidence:** `05274cf:projectionist/web/library_routes.py:1349-1444`. The handler is `async def` and uses `await run_db(...)` for youth filters, `query_library`, and payload sanitizing. The comment at 1436–1438 says the main and theater servers share one loop.

**Current state:** Browse and search do not run SQLite on the loop. Semantic query uses `query_library_async` instead.

**Root cause:** A synchronous query here previously stalled every other request, including theater.

**Recommendation:** Treat `run_db` as mandatory for new async handlers that read or write SQLite. Add a short comment in the contributor notes with this function as the example.

**Rationale:** This is the hottest read in the product. Inlining it back onto the loop would regress theater and chat together. Rejected: converting the whole database layer to an async driver.

**User story:** As a member browsing while someone else searches, I want both pages to stay responsive.

**Acceptance criteria:**
- [ ] `/api/library/query` still awaits `run_db` for the synchronous query.
- [ ] A review check rejects a new `async def` that calls `query_library` directly.

**Success metric:** Health latency does not track library-query latency.

**Validation:** Code inspection of the handler.

### PERF-006: Keep gzip and immutable caching on hashed assets

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Public |
| Persona(s) | Low-bandwidth mobile user, returning consumer |
| Category | Front-end delivery |
| Severity | Medium |
| Impact | 4 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 4.0 |
| Verdict | Protect |
| Dependencies | none |
| Labels | cache, gzip |

**Evidence:** `05274cf:projectionist/web/app.py:475` adds `GZipMiddleware` with `minimum_size=500`. `05274cf:projectionist/web/static_assets.py:13-23` sets `public, max-age=31536000, immutable` when the filename matches a Vite hash. QA `GET /assets/index-CSQsR6Mb.js` with gzip: `bytes=320588`, `enc=gzip`, `cache=public, max-age=31536000, immutable`, `ttfb=0.101623`, `total=0.462245`. CSS `/assets/index-DiqPgHfU.css`: `bytes=57525`, same cache policy, `total=0.282154`.

**Current state:** The expensive files are compressed and safe to cache forever because the hash changes when the bytes change. HTML is gzipped too (888 bytes on the wire versus 2,210 uncompressed) and is not marked immutable.

**Root cause:** Asset names are content-addressed, so a year-long cache is correct.

**Recommendation:** Do not add `Cache-Control: no-store` to `/assets`. Keep the HTML response out of the immutable policy (it must update when the script name changes). Leave the gzip threshold at 500 so tiny JSON is not wasted on compression.

**Rationale:** Breaking the cache header would turn every visit into a 321 kB download on the household LAN and worse over remote access. The header is doing the work a CDN would do.

**User story:** As a returning member, I want the app to open without re-downloading a megabyte of script.

**Acceptance criteria:**
- [ ] Hashed files under `/assets/` keep `immutable` and a one-year max-age.
- [ ] `index.html` does not send `immutable`.
- [ ] A gzip request for the entry script is smaller than the uncompressed file.

**Success metric:** Second-visit transferred bytes for `/assets/index-*.js` are zero in the browser (304 or memory cache), not merely fast.

**Validation:** Response headers on QA, as above.

### PERF-012: Keep heavy scheduler tasks on worker threads

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Admin |
| Persona(s) | Established owner |
| Category | Isolation |
| Severity | Medium |
| Impact | 4 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 4.0 |
| Verdict | Protect |
| Dependencies | none |
| Labels | scheduler |

**Evidence:** `05274cf:projectionist/scheduler/engine.py:1022-1028` runs `off_loop` tasks with `asyncio.to_thread` and a private event loop. At least the following modules pass `off_loop=True`: `metadata_enrichment`, `plot_neighbors`, `summary_motifs`, `taste_refresh`, `long_synopsis_enrichment`, `live_guide_week`, `watch_history_ingest`, `data_retention`, and the newsletter/digest tasks (grep of `scheduler/tasks`).

**Current state:** The enrichment jobs that already opted in cannot freeze request handlers by running synchronous work on the main loop.

**Root cause:** The idle scheduler and the API share a process (SC-09). The flag is the isolation that makes that acceptable.

**Recommendation:** Default new tasks to `off_loop=True` unless they are known to be a few milliseconds. Do not remove the flag from the modules listed above.

**Rationale:** The household has one CPU budget. A motif rebuild on the loop is an outage. A second container is a larger change than a default on a flag.

**User story:** As a member, I want Chat to open while the server is enriching the library overnight.

**Acceptance criteria:**
- [ ] Existing `off_loop=True` tasks stay opted in.
- [ ] The task helper's default is documented next to `TaskDefinition.off_loop`.

**Success metric:** A long enrichment run does not move `/api/health` latency.

**Validation:** Grep `off_loop=True` after any scheduler edit.

### 14. Weaknesses

### PERF-001: Expose writer-queue depth and request latency to the owner

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Admin |
| Persona(s) | Established owner, platform admin |
| Category | Observability |
| Severity | High |
| Impact | 5 |
| Effort | M |
| Confidence | Confirmed |
| Priority score | 5.0 |
| Verdict | Fix |
| Dependencies | none |
| Labels | metrics, sqlite |

**Evidence:** `05274cf:projectionist/library/db/_schema.py:70-72` defines `write_queue_stats` and nothing else in the tree calls it (grep over `projectionist/`). There is no `/metrics` route and no Prometheus client. Logs are the rotating file in `logging_config.py` (5 MiB, 3 backups, JSON only when the format is set to `json`). QA health carries no timing header.

**Current state:** An owner who suspects "the app is slow" can read a text log or guess. The writer thread already records queue depth and wait samples, and the HTTP layer never asks.

**Root cause:** The serializer was built for correctness, and the gauge stopped at the method boundary.

**Recommendation:** Owner-only `GET /api/admin/runtime` returning `write_queue_stats()`, process uptime, and a rolling p50/p95 of `/api/library/query` and `/api/chat` computed in memory (a fixed-size reservoir, not a new database). No new service. Log one JSON line per minute with those three numbers even if the admin page is closed.

**Rationale:** Fifteen-minute diagnosis needs a number that exists before the incident. A full tracing stack is more moving parts than a household image should carry. Rejected: shipping Prometheus inside the container by default.

**User story:** As an owner, I want to see whether writes are queued so I know the library sync is the cause of a stall.

**Acceptance criteria:**
- [ ] The route is owner-only and returns queue depth and wait.
- [ ] A unit test feeds the serializer and reads the route.
- [ ] Members receive 403.

**Success metric:** During a sync, an owner can point at queue depth without opening a shell.

**Validation:** Hit the route on QA as owner after it exists; this pass did not, because the route does not exist.

### PERF-002: Schedule a database backup and practice one restore

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Owner |
| Persona(s) | Established owner |
| Category | Backups |
| Severity | High |
| Impact | 5 |
| Effort | M |
| Confidence | Confirmed |
| Priority score | 5.0 |
| Verdict | Fix |
| Dependencies | none |
| Labels | backup, restore |

**Evidence:** `05274cf:projectionist/web/backup.py:31-80` builds a zip in a `BytesIO`, copying `settings.json` and a SQLite online `backup()` into a temp file. `record_household_backup` only appends an audit row when someone downloads it. Grep of `projectionist/scheduler` found no backup task. The readme inside the zip says restore is "stop, replace files, start."

**Current state:** If nobody downloads a snapshot, there is no backup. The zip holds the whole database in memory before it is sent. Nothing in CI restores a fixture and boots health against it.

**Root cause:** Backup was implemented as an admin download, which is a good export and a bad safety net.

**Recommendation:** A weekly idle task writes `projectionist-auto.db` next to the live file using the same `backup()` API, keeps two generations, and records the timestamp in the runtime status from PERF-001. Add a CI job that boots a container from a tiny fixture snapshot and asserts `/api/ready`. Document the restore in the existing ops doc in one screen. Do not upload the zip anywhere.

**Rationale:** Household disks fail. A download button depends on memory and on a person. An untested restore is a file, not a backup. Rejected: a cloud copy, which fights the on-box privacy stance.

**User story:** As an owner, I want last week's library to be on disk even if I never opened Admin, so a bad upgrade is recoverable.

**Acceptance criteria:**
- [ ] After seven days of uptime, two snapshot files exist without a manual download.
- [ ] CI restores a fixture and gets a ready response.
- [ ] The zip download still works for people who want an off-machine copy.

**Success metric:** One successful restore drill recorded before the next minor release.

**Validation:** Run the CI job and check the data directory timestamps.

### PERF-005: Split the 1,054 kB entry chunk

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Consumer |
| Persona(s) | Low-bandwidth mobile user, returning consumer |
| Category | Front-end performance |
| Severity | High |
| Impact | 4 |
| Effort | M |
| Confidence | Confirmed |
| Priority score | 4.0 |
| Verdict | Fix |
| Dependencies | none |
| Labels | bundle, vite |

**Evidence:** Build log from `/tmp/review360-perf-root/frontend`: `dist/assets/index-CSQsR6Mb.js` 1,054.11 kB, gzip 321.43 kB, map 4,002.37 kB. Vite warned that some chunks exceed 500 kB. A second `index-DQ08qxwO.js` is 156.87 kB (gzip 47.27 kB). CSS `index-DiqPgHfU.css` is 352.05 kB (gzip 57.91 kB). QA transferred 320,588 gzip bytes for the entry script. Route chunks already exist (`LiveWatchPage`, `VoicePage`, `AdminRoutes` in the same log), so the tool can split; the entry is still over a megabyte. Fonts are self-hosted woff2 files in that build (DM Sans, Fraunces, Material Symbols), not a Google Fonts request.

**Current state:** First visit downloads and parses roughly a third of a megabyte of script after gzip, plus 58 kB of CSS, plus fonts. Return visits are saved by the immutable cache (PERF-006), which does not help the first open or a cache clear after each release.

**Root cause:** The shell imports too much that every route does not need. The bundler already splits some routes, so this is leftover static imports, not a missing plugin.

**Recommendation:** Set Vite `build.chunkSizeWarningLimit` only after the entry is under 600 kB uncompressed, not before. Move admin, Live player, and theater player imports behind `React.lazy` if they are still in the entry graph. Add a CI check: fail if `index-*.js` entry (the module script in `index.html`, not every chunk) exceeds 1.2 MB uncompressed, so it cannot grow quietly. Do not raise the limit to silence the warning.

**Rationale:** A 321 kB gzip file is survivable on a LAN and rude on a phone over VPN, and the parse cost hits every device. A ground-up SPA rewrite is not justified; the split points are already in the build output.

**User story:** As a member on a phone, I want Chat to load without also downloading the admin studio.

**Acceptance criteria:**
- [ ] The script tag in `index.html` points at a file under 600 kB uncompressed.
- [ ] Admin and Live player chunks are absent from that file's static import list.
- [ ] CI fails the build when the entry grows past 1.2 MB.

**Success metric:** Gzip entry under 180 kB on the wire, measured the same way as this pass.

**Validation:** `vite build` output and curl `--compressed` size.

### PERF-008: Move chat's session writes off the event loop

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Consumer |
| Persona(s) | Returning consumer |
| Category | Back-end performance |
| Severity | Medium |
| Impact | 3 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 3.0 |
| Verdict | Fix |
| Dependencies | none |
| Labels | chat, asyncio |

**Evidence:** `05274cf:projectionist/web/chat_routes.py:155-170`. `async def chat` calls `enforce_rate_limit`, `scheduler.record_activity`, `_assert_thread_access`, `db.ensure_chat_session`, and possibly `db.set_thread_persona` before the first `await` (the agent call at line 187). Those database calls use the synchronous connection. The library handler next door already refuses to do this (PERF-004).

**Current state:** A chat send holds the event loop for however long SQLite takes, including up to the 30s busy timeout if a writer is stuck. Theater and other async work wait with it.

**Root cause:** The handler was declared `async` for the model stream, and the bookkeeping stayed inline.

**Recommendation:** Wrap the session ensure, thread access check, and persona write in `run_db` (or `run_in_threadpool`) before awaiting the agent. Do the same for the streaming chat handler if it repeats the pattern. Do not change the rate limit or the prompt.

**Rationale:** Chat is the front door. A locked database should slow the send, not the whole process. This is a small copy of a pattern that already exists.

**User story:** As a member, I want the rest of the app to keep working while my message is being saved.

**Acceptance criteria:**
- [ ] No synchronous `db.` call remains before the first `await` in `chat` or the stream handler.
- [ ] A test with a held write lock shows `/api/health` still fast while a chat request is blocked in `run_db`.

**Success metric:** Chat bookkeeping time is absent from the event-loop lag, once PERF-001's latency reservoir exists.

**Validation:** Read the handler; add the regression test.

### PERF-009: Run semantic embeddings off the loop

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Admin |
| Persona(s) | Returning consumer, established owner |
| Category | Scheduler |
| Severity | Medium |
| Impact | 4 |
| Effort | XS |
| Confidence | Likely |
| Priority score | 3.2 |
| Verdict | Fix |
| Dependencies | PERF-012 |
| Labels | embeddings, scheduler |

**Evidence:** `05274cf:projectionist/scheduler/tasks/semantic_embeddings.py:10-11` says this is the heaviest idle task. The file does not contain `off_loop`. `register_severity_task` in `base_augmentation.py:85-107` forwards kwargs and otherwise leaves `TaskDefinition.off_loop` at its default. `05274cf:projectionist/scheduler/engine.py:111` sets `off_loop: bool = False`. When the flag is false, `engine.py:1029` awaits `run_fn` on the caller loop.

**Current state:** The task trickles work and uses `run_db` for some SQLite, so it is not blindly blocking on every query. Any CPU-heavy step inside `run_fn` still shares the loop with requests. Neighboring heavy tasks opted out of that risk explicitly.

**Root cause:** The off-loop flag was added to tasks one by one, and this one was missed or assumed safe because it awaits HTTP.

**Recommendation:** Pass `off_loop=True` for `semantic_embeddings` and for any other `register_severity_task` caller that embeds or scans the catalog (`llm_logline_enrichment`, `coverage_deficit_audit`, `entity_memory_enrichment` — confirm each the same way). Change the helper default to `off_loop=True` only after those callers are checked, so a tiny task is not surprised.

**Rationale:** The module's own header says it is the heavy one. The fix is a keyword argument. Confidence is Likely rather than Confirmed because this pass did not watch a cycle run; the source default is confirmed.

**User story:** As a member, I want the app to stay responsive after everyone goes idle and embeddings start.

**Acceptance criteria:**
- [ ] `semantic_embeddings` is registered with `off_loop=True`.
- [ ] A unit test reads the registered definition and asserts the flag.

**Success metric:** Embedding cycles do not increase event-loop lag on the runtime status route.

**Validation:** The registration site and the test.

### PERF-007: Point operators at a ready check that notices a dead database

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Admin |
| Persona(s) | Platform admin |
| Category | Health checks |
| Severity | Medium |
| Impact | 3 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 3.0 |
| Verdict | Fix |
| Dependencies | PERF-003 |
| Labels | health, ready |

**Evidence:** `05274cf:projectionist/web/app.py:1322-1327` defines `/api/ready`, which returns 503 until `app.state.ready` and does not read the movie library. `/api/health` cannot fail because of SQLite (PERF-003). QA ready was not required by the curl in the Unraid docs this pass re-read only via the health behavior. CI docker-smoke greps `/api/health` (`ci.yml` around the smoke step).

**Current state:** "Healthy" means the process answers. A database that will not open still looks healthy to the check the release path uses.

**Root cause:** The shallow probe was the right fix for restarts-during-lock, and it became the only probe.

**Recommendation:** Keep health shallow. Make `/api/ready` run `SELECT 1` through `run_db` with a 100ms timeout and return 503 on timeout, without scanning `library_items`. Switch the CI smoke's second curl, and the ops health example, to ready. Leave the liveness curl on health so a busy writer does not restart the container.

**Rationale:** Liveness and readiness are different questions. Using one URL for both recreates the stall PERF-003 removed, or hides a dead file. Two URLs already exist; ready is just incomplete.

**User story:** As an owner, I want the status light to go red when the database file cannot be opened so I do not hunt a Plex outage that is actually SQLite.

**Acceptance criteria:**
- [ ] `/api/ready` returns 503 when `SELECT 1` exceeds 100ms or raises.
- [ ] `/api/health` is unchanged.
- [ ] CI smoke calls both, and only ready is allowed to fail the job on a bad database.

**Success metric:** A renamed database file fails ready and not health.

**Validation:** Disposable data dir with the file missing.

### PERF-011: Put a household ceiling on LLM spend

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Owner |
| Persona(s) | Established owner |
| Category | Cost |
| Severity | Medium |
| Impact | 4 |
| Effort | M |
| Confidence | Likely |
| Priority score | 2.1 |
| Verdict | Fix |
| Dependencies | PERF-001 |
| Labels | llm, cost |

**Evidence:** `05274cf:projectionist/agent/providers/__init__.py:243-420` uses `httpx.AsyncClient(timeout=120.0)` and a payload `max_tokens` of 4096 (line 373). Migration 40 is named `llm_usage` (`library/db/migrations.py:294`). `semantic_embeddings.py` caps items per idle cycle. Admin batch jobs carry an `llm_budget` dict (`library/admin_batch_jobs.py:301`). This pass did not find a setting that stops chat or enrichment after a monthly token total.

**Current state:** One reply cannot run away forever. A month of chat plus logline enrichment plus embeddings can. Usage rows exist, so the data to enforce a cap is the point of that table, and the gate is not wired to chat.

**Root cause:** Cost controls were added at the call site (max tokens, trickle) and not at the household.

**Recommendation:** An owner setting, default on, `llm_monthly_token_ceiling` (start at 2,000,000 tokens, the number is a default the owner can edit). When `llm_usage` for the UTC month exceeds it, chat returns a clear error and enrichment tasks no-op until next month. Show the month-to-date count on the runtime status route. Do not pick the provider for them.

**Rationale:** The product's promise is a local app with a bring-your-own key. An uncapped key is the bill. A hard vendor switch would not cap spend. Confidence is Likely because a ceiling could live in settings this pass did not exhaustively read; the provider path itself has no such check.

**User story:** As an owner, I want enrichment to stop after a limit I chose so a large library cannot run up the model bill overnight.

**Acceptance criteria:**
- [ ] A ceiling of 1 token in a test makes the next chat call return a controlled error and makes the embedding task skip.
- [ ] The owner UI shows tokens used this month.
- [ ] The default is on, with a documented number.

**Success metric:** A test household cannot exceed the configured ceiling in a calendar month.

**Validation:** Unit test with a fake usage row.

### PERF-013: Cache the favicon

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Public |
| Persona(s) | Returning consumer |
| Category | Front-end delivery |
| Severity | Low |
| Impact | 1 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 1.0 |
| Verdict | Fix |
| Dependencies | none |
| Labels | cache |

**Evidence:** QA `GET /favicon.svg`: `code=200`, `bytes=252`, `total=0.097230`, empty `content-encoding` (under the gzip minimum) and empty `cache-control`. `spa_routes.py:176-181` returns the file with a media type and no cache header.

**Current state:** Every document load revalidates a 252-byte file that almost never changes.

**Root cause:** Public files were given explicit headers only when someone hit a stale-content bug. The favicon was not one of those bugs.

**Recommendation:** `Cache-Control: public, max-age=86400` on `/favicon.svg`. Do not mark it immutable unless the URL is hashed.

**Rationale:** This is not the 1 MB problem. It is a free header on a file every page requests. Rejected: inlining it into the HTML, which would enlarge the document that must stay fresh.

**User story:** As a returning member, I want the tab icon to stay cached so the browser does not request it on every navigation.

**Acceptance criteria:**
- [ ] Response includes `max-age=86400`.
- [ ] Body is unchanged.

**Success metric:** Browser devtools shows the favicon served from cache on the second navigation.

**Validation:** curl headers.

### 15. Opportunities

### PERF-014: Adopt the SLOs below and check them from the runtime route

| Field | Value |
|---|---|
| Type | Opportunity |
| Surface | Cross-cutting |
| Persona(s) | Established owner, platform admin |
| Category | SLOs |
| Severity | Medium |
| Impact | 3 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 3.0 |
| Verdict | Add |
| Dependencies | PERF-001 |
| Labels | slo |

**Evidence:** Today's numbers are point samples, not objectives. Health ~99ms and entry-script ~0.46s are LAN samples from one laptop to `10.10.1.202`, so they include the network.

**Current state:** There is no stated target, so a regression has nothing to miss.

**Root cause:** Performance work has been incident-driven (the busy-timeout comment) rather than objective-driven.

**Recommendation:** Adopt the SLOs in the table below. Evaluate them from the in-memory reservoir in PERF-001, not from a hosted vendor. Review them when a release changes the entry chunk or the query path.

**Rationale:** A household does not need an error-budget committee. It needs three numbers the owner can compare to last month.

**User story:** As an owner, I want a written target for "Chat and browse feel immediate" so a release that misses it is a bug.

**Acceptance criteria:**
- [ ] The three SLOs are written in the ops doc.
- [ ] The runtime route can show a pass/fail against the latency SLOs from local samples.

**Success metric:** The next release notes say whether the SLOs held.

**Validation:** Read the route payload.

Proposed SLOs (LAN, from the browser to the container):

| Journey | SLI | Target |
|---|---|---|
| Process up | `GET /api/health` p99 | under 200ms, and it never takes a SQLite lock |
| Ready | `GET /api/ready` p99 | under 300ms, 503 if `SELECT 1` exceeds 100ms |
| Browse | `GET /api/library/query` p95, limit 25, no semantic query | under 800ms |
| Chat | time to first token p95, warm provider | under 8s, excluding the household's own model queue |
| First paint | entry script gzip size | under 180 kB after PERF-005; today it is 321 kB and does not meet this |

Chat and browse targets are goals. This pass did not measure them. Health does meet its target on the sample above.

### 16. Remediation plan

| Horizon | ID | Title | Effort | Owner | Dependencies |
|---|---|---|---|---|---|
| Now | PERF-009 | off_loop on semantic embeddings | XS | Backend | none |
| Now | PERF-008 | Chat session writes via run_db | S | Backend | none |
| Now | PERF-013 | Favicon cache header | XS | Backend | none |
| Now | PERF-007 | Ready runs SELECT 1; docs use it | S | Backend | PERF-003 |
| Next | PERF-001 | Owner runtime stats | M | Backend | none |
| Next | PERF-002 | Weekly sqlite backup and a CI restore | M | Backend | PERF-001 |
| Next | PERF-005 | Split the entry chunk; CI size cap | M | Frontend | none |
| Next | PERF-014 | Write the SLOs down | S | Maintainer | PERF-001 |
| Later | PERF-011 | Monthly token ceiling | M | Backend | PERF-001 |

**Sequencing.** The XS/S items do not need the status route. The backup and the ceiling are only operable once the owner can see "last backup" and "tokens used", so they follow PERF-001. Bundle work is independent and can land beside them.

### 17. Quick wins

- PERF-009 (XS): one keyword.
- PERF-013 (XS): one header.
- PERF-008 (S): `run_db` around chat bookkeeping.
- PERF-007 (S): a timed `SELECT 1` on ready.

### 18. Open questions

- What token volume does a real household use in a month? The 2,000,000 default in PERF-011 should be replaced with a number from `llm_usage` on a production-like library before it ships. This pass did not read QA's usage rows.
- Is the theater port (:8791) on the same event loop in the QA container as the main app? The code comment says yes for the dual-serve path. This pass did not probe theater, by rule.
- Should the entry-chunk SLO be gzip size or uncompressed parse size? Both are listed; pick uncompressed in CI (stable) and gzip on the wire (what phones pay).

### Phase 6 self-check

- [x] Part A is first; conclusions cite finding IDs.
- [x] Every High finding (PERF-001, PERF-002, PERF-005) appears in the narrative. Strengths marked High are in the narrative as things to protect.
- [x] Foundations challenged, "If we built it today", and "Stop doing" are present.
- [x] All four surfaces are covered in section 5.
- [x] Strengths use the full finding format.
- [x] Evidence, root cause, rationale, and acceptance criteria are on every finding.
- [x] IDs PERF-001 through PERF-014 are unique. PERF-003, 004, 006, and 012 are strengths; the rest are weaknesses or the SLO opportunity.
- [x] No application code was modified.

### Changelog

- 2026-11-02 (red team, `21_2026-11-01_red-team.md` section 7): Part A referenced PERF-010, which does not exist; changed to PERF-007 (ready check). Grade and finding IDs unchanged.
