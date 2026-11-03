# 09 · Performance, Reliability & Cost / SRE (PERF) — run 2026-10-28-2

**Commit reviewed:** `94fcd3f` (`origin/main`, version 1.37.72). All `path:line` citations come from `git grep -n` / `git show 94fcd3f:path`, not the working tree.
**Instance measured:** QA sidecar `http://10.10.1.202:8792` only (Path A host build `projectionist-qa:wip` of `94fcd3f`; the served bundle hashes match a clean `vite build` of `git archive 94fcd3f` byte for byte). Prod `:8788`, smartmap `:8790`, prod theater `:8791`, and the VIP hostname were not requested.
**Reviewer lens:** Is it fast, does it stay up, can we see what's happening, and are we spending wisely?

---

# Part A — Conclusions & findings

## 1. Bottom line

**Grade: C−.** On the LAN, Projectionist feels quick: a warm `/login` paints in about 110 ms and the database discipline underneath (one writer thread, WAL, 30 s busy timeout, health and documents kept off SQLite) is better than most single-container apps (PERF-001). Away from the LAN it falls apart. The origin sends a **2.08 MiB uncompressed JavaScript bundle plus 336 KiB of CSS on every first visit**, with no compression and no cache headers. On a throttled slow-4G phone profile, `/login` first paints at **12.6 s** (PERF-007, PERF-011). The single most important fix is a backend one, though. **The Movies query runs synchronous SQLite work inside an `async` handler and freezes the whole process.** While one member browses Movies, `/api/health` goes from 15 ms to 646 ms, and with three members it takes 2.16 s. Chat streams, Live polling, and the lobby theater share that event loop (PERF-008). Next come recoverability and release safety. Backups run weekly, are unverified, and have never been restore-tested (PERF-009). `main` CI has been red for 33 of its last 60 runs, and the docs say a red run does not block rollout (PERF-010). **Protect** the SQLite write serializer and the connector retry and circuit-breaker design (PERF-001, PERF-002).

## 2. Key conclusions

1. **The app was built for a LAN and ships as if every client is on gigabit.** The origin has no `GZipMiddleware`, and `StaticFiles` sends no `Cache-Control` (`projectionist/web/app.py:616`). Everything goes out raw: the JS bundle (2,178,954 B; 645,698 B gzipped), the CSS (344,428 B; 56,441 B gzipped), the Explore hub JSON (199,740 B; 31,777 B gzipped), and About's `release-notes.json` (613,415 B; 175,471 B gzipped). On top of that, Vite produces **one** chunk. `frontend/src/AppRoutes.tsx` statically imports 44 pages, so every member downloads hls.js (513 KiB minified), about 240 KiB of owner-only Admin pages, and the raw `HELP.md` and `PRIVACY.md` (115 KiB) just to see the sign-in form (PERF-007, PERF-011). Compression is a one-line XS change that removes roughly 70% of cold bytes. Route splitting is an M change that cuts the login critical path again. Do both before any visual work. Members who use the public hostname or a phone are paying for this today.

2. **One `async def` handler doing blocking work stalls every user, the health check, and the theater.** `library_query_endpoint` is declared `async` (`projectionist/web/library_routes.py:1347`), but it calls the synchronous `query_library(_db(), filters)` directly (`:1436`). FastAPI does not offload that call, so the event loop is pinned for about 650 ms per Movies page. Main and theater servers run in one `asyncio.gather` (`projectionist/web/__main__.py:152`), so they share the loop. I measured this directly. Five parallel Movies queries each took 3.73 s. A health probe sent 150 ms after one query took 646 ms, and one sent during three queries took 2.16 s (PERF-008). This is the highest-leverage backend fix on the platform: S effort, and it removes the household's main concurrency cliff. Root cause is a missing rule ("no sync I/O in `async def`"), so the fix must include a lint or test guard and not just this one handler (PERF-023).

3. **We cannot currently prove we can recover, and we would learn about an outage from a household member.** Prod's 218 MB SQLite database is covered only by the Unraid Appdata Backup plugin. It runs weekly (Mon 03:03), keeps 4 copies, and has `verifyBackup: no`. The latest archive is 1.92 GB, dominated by 3.7 GB of Tunarr state. There is no pre-migration snapshot, migrations are forward-only with no downgrade guard (`projectionist/library/db/migrations.py:320-331`), and no restore has ever been drilled. That gives an RPO of up to 7 days and an unknown RTO (PERF-009, PERF-013). Observability is a log file plus an owner log viewer. There are no metrics, no request-latency logging, and no alert path. `/api/health` returns a constant `{"status":"ok"}` without touching the DB or the scheduler (`projectionist/web/app.py:1269-1271`), and nothing on the host watches it (PERF-012). We could not detect an incident in under 15 minutes. Roadmap: nightly verified `sqlite3 .backup` plus a pre-rollout snapshot (Now), then a readiness endpoint plus an external probe with Apprise alerting (Next).

4. **The release pipeline has lost its gate.** On `main`, CI failed on 33 of the last 60 runs, and the last green run was 2026-10-24 (`71bd4b2`). At `94fcd3f`, pytest is healthy: 2,749 passed, coverage 76.74% against the 74% floor, 15 min 37 s. The red comes from two Playwright Explore specs and `ruff check`. `docs/RELEASE.md:157` explicitly says "A red Actions job does not block a human rollout", and nine patch releases (1.37.63 → 1.37.72) shipped over red (PERF-010). When red is normal, the perf budget (PERF-003, PERF-020) and the Docker smoke job stop protecting anything. Treat "main is green" as a release precondition again and quarantine the flaky specs explicitly.

5. **Several pages do far more work than their job needs.** About renders all **270 releases / 2,745 bullets as about 7,000 DOM elements** (CDP node count about 15,700). Style recalculation takes 362–443 ms, and on a 4× CPU profile the release list becomes usable at 16.7 s cold (PERF-014). A signed-in `/chat` load makes **24 API calls**. That includes `/api/features` ×3, `/api/auth/me` ×2, and a `POST /api/watchlist/sync` to Plex on every app boot (`frontend/src/App.tsx:251-252`) (PERF-015). Explore's Continue Watching rail makes an uncached synchronous Plex call on every view, taking 0.75–1.6 s (PERF-019). Every authenticated call has a fixed cost of about 70 ms, against 15 ms for health and about 33 ms anonymous. A likely cause is that settings are re-read from disk and decrypted on every `_settings()` call (PERF-017). None of these is dramatic alone. Together they explain why a 10-person household feels slow while the lab benchmark looks fine.

6. **Cost is low and mostly well governed. The open risk is LLM spend with no ceiling.** Prod runs at 474 MiB RSS and about 0.3% CPU idle on a 125.8 GiB host. Infrastructure cost is effectively the Unraid box (PERF-006). LLM usage is accounted by purpose with no prompt text stored, and background logline enrichment defaults to 5 items every 24 h (PERF-005). But the system has no daily token or USD cap, and each provider call opens a fresh `httpx.AsyncClient(timeout=120.0)` with no retry or fallback (`projectionist/agent/providers/__init__.py:243`) (PERF-022). Host hygiene shows 17.76 GB of reclaimable images, with 11 retained `romwil/projectionist` tags at about 750 MB each (PERF-027). Add a spend cap before turning on any new background LLM task.

7. **The perf budget exists but measures the wrong moment with loose floors.** `e2e/release-perf.spec.ts` is a real asset: it runs in CI, measures LCP, CLS, and server time, and keeps a committed baseline (PERF-003). But About's "content" is the heading "The story", not the release list. Budgets floor at 1,500 ms on a localhost mocked server, and Explore's CLS of 0.1604 was accepted into the baseline (PERF-020). It never measures bytes, compression, or a throttled profile, so it cannot catch conclusion 1. Add a byte budget and a throttled cold run.

## 3. Foundations challenged

| Assumption | Evidence for | Evidence against | Verdict | Cost of change | Rationale |
|---|---|---|---|---|---|
| One Python process (main + theater + scheduler + MCP) on one event loop is enough | 474 MiB, 0.3% CPU idle; simple ops; SQLite is single-writer anyway | One blocking handler freezes health and theater (PERF-008); scheduler VACUUM runs in-process (PERF-024) | **Keep, with guard rails** | S (offload) → L (split worker) | A household app does not need horizontal scale. It needs the loop to never block. Fix the handlers first (PERF-008); split background work only if SLOs still burn (PERF-023). |
| SQLite (WAL) under `DATA_DIR` is the right store | Write serializer + WAL + busy timeout (PERF-001); 218 MB prod DB; zero ops | Backups weekly and unverified (PERF-009); no downgrade guard (PERF-013) | **Keep** | — | Postgres would add a second container and backups for no user gain. The gap is backup discipline, not the engine. |
| One Vite bundle is fine because it's a LAN app | LAN FCP ~250 ms cold | 2.08 MiB raw JS; 12.6 s slow-4G FCP; members use the public hostname and phones (PERF-007, PERF-011) | **Change** | XS (gzip) + M (split) | The audience is not LAN-only. |
| About should show the full CHANGELOG history | Transparency; a nice touch for owners | 7,000 elements, 613 KB JSON, 16.7 s throttled (PERF-014) | **Change** | S | Show the last 10 releases and fetch older ones on demand. Full history lives on GitHub. |
| Google Fonts CDN for brand + Material Symbols icons | Zero build effort | Two render-blocking third-party stylesheets; 316 KB icon font; also a privacy leak (PERF-016) | **Change** | S | Self-host subsetted WOFF2s and swap the icon font for inline SVGs of the ~60 icons used. |
| A red CI run should not block a human rollout | Owner can ship urgent fixes | 33/60 red; nine releases over red (PERF-010) | **Change** | S | Allow an explicit `--override-red-ci "<reason>"`, not silent normalisation. |
| Weekly Appdata Backup is our backup | Exists, offsite share, 4 kept | Weekly RPO, `verifyBackup: no`, no restore drill, 1.9 GB tarball dominated by Tunarr (PERF-009) | **Change** | S | Add a nightly app-level SQLite backup with integrity check and retention. |
| `/api/health` as the container health signal | Cheap, DB-free (deliberately, `projectionist/web/auth.py:449-453`) | Says "ok" with a dead DB, stuck scheduler, or blocked loop; Docker does not restart unhealthy containers anyway | **Change** | S | Keep `/api/health` as liveness and add `/api/health/ready` with DB, scheduler, and write-queue checks (PERF-012, PERF-025). |
| Hub-first, pull-only rollout | Pull before stop (`scripts/unraid-rollout.sh:131-133`); health smoke (`:254-280`); old tags retained | No DB snapshot before the new schema runs; no automated rollback (PERF-013) | **Keep + extend** | S | Add the snapshot step and a documented rollback. |

## 4. If we built it today

A zero-based design for a single-household media companion would keep **one container and SQLite**. It would also:

- Serve a **compressed, content-hashed, route-split SPA** with `Cache-Control: public, max-age=31536000, immutable` on `/assets/*` and `no-cache` on the HTML shell.
- Use a **strict sync/async boundary**. Handlers are sync (threadpool) unless every awaited call is truly async, enforced by a lint rule.
- Run **background work (scheduler, enrichment, VACUUM, Plex sync) in a separate worker process** sharing the DB, so request latency is independent of jobs.
- Write a **nightly verified backup** into `DATA_DIR/backups` with 14 copies, a restore script, and a snapshot taken automatically before any schema migration.
- Expose **liveness vs readiness endpoints, a tiny Prometheus-style `/metrics`** (request latency histogram by route group, write-queue depth, scheduler last-success, LLM tokens per day), and an external probe that alerts through the Apprise transport the app already ships.
- Set **an LLM daily budget** with hard stop and owner notification.

The gap to today is mostly configuration and guard rails, not architecture. Closing it is worth it. Most items are XS–S, and the only L item (worker split, PERF-023) should wait for SLO data.

## 5. Findings by surface

**Public (`/login`, `/about`, `/privacy`, `/help`).** The HTML shell is tiny (2,607 B), and the theme script prevents a flash, so CLS is about 0 on `/login`. But every public page is the same 2.47 MB-transfer SPA shell. On slow 4G with a 4× CPU profile, `/login` first paints at 12.6 s and About's release list appears at 16.7 s. About also builds about 7,000 DOM elements from a 613 KB JSON with a 60 s cache. The fixes are compression (PERF-007), a split login chunk (PERF-011), and a paginated About (PERF-014). Fonts are third-party and render-blocking (PERF-016). **Grade: D** (PERF-007, PERF-011, PERF-014, PERF-016).

**Consumer (chat, Explore, search, Play, Live).** Warm LAN numbers are fine: Explore LCP 860 ms, Movies LCP 988 ms, Chat LCP 1,208 ms. Under household concurrency it degrades badly, because a Movies query blocks the loop for about 650 ms (PERF-008). Chat boot fans out to 24 calls, including a Plex watchlist sync (PERF-015). Continue Watching costs 0.75–1.6 s of Plex round trip per view (PERF-019). Explore CLS is 0.096 live and 0.16 in the baseline (PERF-020). Chat first-token and Play start could not be measured because LLM is unset on QA and Play needs a live Plex stream. SLOs are proposed below so they can be measured once instrumented (PERF-025). **Grade: C−** (PERF-008, PERF-015, PERF-017, PERF-019, PERF-020, PERF-025).

**Owner (`/admin/*`).** Admin pages are shipped to every member, at about 240 KiB minified in the main chunk (PERF-011). The backup snapshot download builds the whole DB copy and zip in RAM inside a request (`projectionist/web/backup.py:35-59`). For prod's 218 MB DB, that means several hundred MB of peak memory and a long-held worker (PERF-018). The LLM Usage page and the scheduler quarantine are good foundations (PERF-005), but quarantine state is in-memory only and nothing is pushed to the owner when a task is quarantined (PERF-012). **Grade: C** (PERF-005, PERF-011, PERF-012, PERF-018).

**Admin / operator (maintainer, Automat host, CI, release).** The rollout script is solid: Hub pull-only, pull before stop, health smoke, and build-info echo (PERF-004). Around it, the controls are weak. Backups are weekly and unverified (PERF-009). There is no downgrade guard or pre-migration snapshot (PERF-013). CI has been red as a norm since 10-24 (PERF-010). Nothing external monitors the stack (PERF-012). **Grade: D+** (PERF-004, PERF-009, PERF-010, PERF-012, PERF-013, PERF-027).

## 6. Findings by theme

**Front-end performance.** The best part is the HTML shell plus inline theme bootstrap: 2.6 KB and no flash. The worst is serving 2.08 MiB of raw JS with no compression and no `Cache-Control` to the sign-in page (PERF-007, PERF-011). Direction: compress, then mark hashed assets immutable, then split by route (login, consumer, admin, player), then set a byte budget in CI.

**Back-end performance.** The best part is that health, documents, and assets never touch SQLite (`projectionist/web/auth.py:449-453`), and writes are serialized (PERF-001). The worst is the `async` handler blocking the loop (PERF-008). Next come uncached Plex calls in request paths (PERF-019, PERF-015) and per-request settings reload (PERF-017). Direction: no sync I/O in `async def`, a short TTL cache for Plex on-deck, and a settings cache keyed on file mtime.

**Reliability.** The best part is connector HTTP: idempotent-only retries with jitter and a `Retry-After` cap, plus per-host circuit breakers with a 60 s cooldown (PERF-002). The worst is backups and migrations (PERF-009, PERF-013). Single points of failure: one host, one container, one SQLite file, one event loop. That is acceptable for a household app only if backups and restore are real.

**Observability.** There is a rotating file log (5 MiB × 3) with secret redaction and an owner log viewer (`/api/admin/logs`). There are no metrics, no latency logging, no alerting, and the health check is constant (PERF-012). Direction: readiness endpoint, `/metrics`, external probe, and Apprise alerts (PERF-025, PERF-026).

**Deployment.** Hub-first, pull-only rollout is good (PERF-004). The broken part is the gate: CI is red on main, and red is explicitly non-blocking (PERF-010). Direction: green main as a release precondition, quarantine flaky specs, add a pre-rollout DB snapshot.

**Cost.** Infrastructure is negligible (PERF-006). LLM accounting exists (PERF-005), but there is no cap (PERF-022). 17.76 GB of reclaimable images sit on the host (PERF-027).

## 7. Stop doing

- **Stop shipping full CHANGELOG history to every About visit.** 270 releases is 613 KB and about 7,000 nodes. Show 10 and link to GitHub for the rest (PERF-014).
- **Stop releasing over red CI by default.** Make an override explicit and logged (PERF-010).
- **Stop syncing the Plex watchlist on every SPA boot.** Do it on login, on Watchlist open, or on a schedule (PERF-015).
- **Stop declaring handlers `async def` unless every call inside is awaited I/O** (PERF-008, PERF-023).
- **Stop loading Material Symbols as a 316 KB variable web font from Google** for a few dozen icons (PERF-016).
- **Stop keeping every Hub tag on the host.** Keep the current release and two previous (PERF-027).
- **Stop accepting CLS regressions into the perf baseline** (Explore 0.1604) (PERF-020).

## 8. Strengths worth protecting

- **SQLite write discipline.** A dedicated writer thread, WAL, `synchronous=NORMAL`, a 30 s busy timeout, and documents, assets, and health kept off the DB (PERF-001). Do not add "just one quick write" outside `run_write`.
- **Connector resilience.** Retries are idempotent-only, with backoff, jitter, a `Retry-After` cap, and per-host circuit breakers (PERF-002). Keep POST/PUT non-retrying.
- **A perf harness in CI with a committed baseline** (PERF-003). Tighten it; don't delete it.
- **Pull-only, pull-before-stop rollout with health smoke** (PERF-004).
- **LLM usage accounting without prompt text, and a tiny default enrichment batch** (PERF-005).
- **Small runtime footprint and a healthy backend test suite**: 2,749 tests, 76.7% coverage over a 74% floor (PERF-006).

## 9. Risks of inaction (6–12 months)

- As the household grows past 3–5 concurrent users, Movies or search browsing will make chat streams stutter and the lobby theater freeze. Docker healthchecks (5 s timeout, 3 retries) can start flapping during busy evenings (PERF-008).
- A corrupted DB, a bad migration, or a failed disk loses up to a week of ratings, watch history, chat threads, and taste. No restore has ever been proven to work (PERF-009, PERF-013).
- With CI red as the norm, a real regression (security, data, or perf) ships unnoticed. The perf budget stops meaning anything (PERF-010).
- Members on phones and on the public hostname see 5–13 s cold starts. Some will stop opening the app in favour of Plex directly (PERF-007, PERF-011).
- A misconfigured cloud LLM model or a runaway agent loop can burn money with no ceiling or alert (PERF-022).

## 10. Recommended direction

Sequence by **blast radius per hour of effort**:

1. **Now (0–2 weeks):**
   - Add `GZipMiddleware` and immutable asset caching (PERF-007).
   - Make `library_query_endpoint` sync, or wrap the call in `run_in_threadpool`, plus a guard test (PERF-008).
   - Run a nightly verified `sqlite3 .backup` with 14 copies, take a pre-rollout snapshot, and do one restore drill (PERF-009, PERF-013).
   - Get main green and make green a release precondition (PERF-010).
   - Paginate About (PERF-014).
2. **Next (2–6 weeks):**
   - Split routes (login, consumer, admin, player) with a byte budget (PERF-011, PERF-020).
   - Add a readiness endpoint, `/metrics`, an external probe, and Apprise alerts (PERF-012, PERF-025).
   - Trim chat boot fan-out, cache Plex on-deck, and cache settings (PERF-015, PERF-017, PERF-019).
   - Self-host fonts (PERF-016).
   - Add the LLM budget (PERF-022).
3. **Later (6+ weeks):** move background work to a worker process if SLOs still burn (PERF-023), add an RUM beacon (PERF-026), and run a small QA load test per release (PERF-028).

**90-day success indicators:**

- Cold `/login` transfer ≤ 400 KB compressed; slow-4G + 4× CPU FCP ≤ 4 s.
- `/api/health` p99 ≤ 100 ms while 5 Movies queries run concurrently.
- Nightly backups verified for 30 consecutive days, with one documented restore taking ≤ 30 min.
- CI on main green ≥ 90% of runs.
- Every SLO in the table below has a live indicator and an alert.

### Proposed SLOs (single container, SQLite, household scale)

Indicators must be collectable from inside the app (a middleware histogram exported at `/metrics`, or JSON log lines) plus one external prober. Windows are 28 days unless noted.

| Journey | SLI (how measured) | SLO target | Alert (burn) | Measured today |
|---|---|---|---|---|
| **Health / availability** | External probe every 60 s to `/api/health/ready` (DB `SELECT 1`, scheduler heartbeat < 10 min old, write-queue depth < 50), counting 2xx within 2 s | 99.5% of probes succeed (about 3.6 h/month budget; covers weekly backup and rollouts) | 3 consecutive failures → Apprise to owner; 2% budget in 1 h → page | `/api/health` 15–17 ms (n=6); ready endpoint does not exist |
| **Loop responsiveness** | `/api/health` latency from the same probe | p99 < 250 ms | p99 > 1 s for 10 min | 646 ms with 1 concurrent Movies query, 2,155 ms with 3 |
| **Chat first token** | Server-side: time from `POST /api/chat/stream` accept to first SSE `data:` frame, histogram by provider | p90 < 3 s local LLM / < 2 s cloud; error rate < 2% | p90 > 6 s for 15 min, or > 5% errors in 1 h | **Not measurable** (LLM unset on QA) |
| **Explore rails** | Server: `/api/library/feeds/hub` latency; client: RUM "rails visible" mark | Server p95 < 400 ms; client p75 rails visible < 2.5 s | Server p95 > 1 s for 15 min | Hub 216–239 ms warm (200 KB raw); Continue Watching 0.75–1.6 s; LCP 860 ms LAN warm |
| **Library search (Movies)** | `/api/library/query` latency | p95 < 500 ms at 5 concurrent users | p95 > 1.5 s for 15 min | 653–671 ms single; 3.73 s at 5 concurrent |
| **Play start** | Client: `/watch` click → first `playing` event (RUM); server: HLS manifest proxy latency | p75 < 4 s; failure rate < 3% | p75 > 8 s for 15 min | **Not measured** (needs live Plex stream) |
| **Backup freshness** | Age of newest verified backup in `DATA_DIR/backups` (exported gauge) | < 26 h, 100% of days | > 26 h → owner alert | Up to 7 days; unverified |

---

## 11. Scorecard (1–5)

| Surface | Front-end speed | Back-end latency | Reliability | Observability | Deploy safety | Cost efficiency |
|---|---|---|---|---|---|---|
| Public | 2 — 2.47 MB raw cold, 12.6 s slow-4G FCP | 4 — HTML 2.6 KB, 16–25 ms TTFB | 3 — static, but same blocked loop | 1 — no RUM | 3 — rides the same pipeline | 3 — bytes wasted, no egress cost on LAN |
| Consumer | 3 — warm LAN LCP 0.86–1.2 s; 24-call chat boot | 2 — Movies 650 ms, loop-blocking | 3 — retries + breakers good; loop SPOF | 1 — no latency metrics | 3 | 4 — low compute |
| Owner | 3 — admin ships in main chunk | 3 — snapshot in RAM | 3 — quarantine in-memory | 3 — log viewer, LLM usage | 3 | 3 — no LLM cap |
| Admin / operator | n/a | n/a | 2 — weekly unverified backups, no downgrade guard | 1 — no external probe/alerts | 2 — red CI ships | 3 — 17.8 GB reclaimable images |

---

# Part B — Detailed findings

## 12. Scope & method

**What was reviewed:** front-end payloads, page timing and DOM cost on QA `:8792`; back-end hot paths at `94fcd3f`; reliability (DB, retries, backups, migrations, rollout); observability; CI and release gates; cost drivers on the Automat host (read-only `docker`/`ls`/`du`).

**What could not be reviewed:**

- **Chat first token:** LLM is unset on QA.
- **Play start:** needs a live Plex HLS session. It was not exercised to avoid playback load.
- **Live On:** left Off, as in the earlier batches.
- **VIP / CDN path:** forbidden. Whether the public proxy compresses is **unknown**.
- **Lighthouse:** not installed. Playwright Chromium in a temp dir was used instead.
- **Python lockfile:** none at `94fcd3f`, so no `pip-audit` against pinned versions.
- **Full local pytest:** not run. CI's run at `94fcd3f` is cited, plus a local timed subset.

**Tools missing:** Lighthouse (`lighthouse not found`), Python lockfile / `pip-audit`. Present: curl, Node v26.3.0, Playwright 1.61.1 (installed only into a temp `git archive` dir, then deleted), `gh`.

**Commands and summarized output** (no secrets; QA owner credentials were read from the host `.env.qa` into a process environment variable and never printed or written):

1. **QA health.** `curl -sS -D - http://10.10.1.202:8792/api/health` returned `200`, body `{"status":"ok","version":"1.37.72"}`. Headers: `server: uvicorn`, `content-type: application/json`, `content-length: 35`. There is **no `content-encoding`, no `cache-control`**. CSP, `x-frame-options: DENY`, `nosniff`, `referrer-policy`, and `permissions-policy` are present. Three timed calls took 14.8 / 16.8 / 16.9 ms.

2. **Asset weight** (curl `-D -`, `-w size_download`, local `gzip -9 | wc -c`). The request sent `Accept-Encoding: gzip, br`, and the server still returned identity encoding.

| URL (QA `:8792`) | Status | Bytes served | gzip -9 bytes (what compression would send) | `Cache-Control` | Notes |
|---|---|---|---|---|---|
| `/login` (HTML) | 200 | 2,607 | — | none | Same document for `/chat`, `/about`, `/explore`, `/watch/1`, `/admin` (identical md5); TTFB 19–25 ms |
| `/assets/index-buFnxk8x.js` | 200 | **2,178,954** (2,128 KiB) | **645,698** (631 KiB) | none (ETag + Last-Modified only) | The only JS chunk referenced. 0 lazy `assets/*.js` references inside it |
| `/assets/index-DlGI-Pbi.css` | 200 | **344,428** (336 KiB) | **56,441** (55 KiB) | none | 18 source CSS files, 429,913 B |
| `/release-notes.json` (About) | 200 | **613,415** (599 KiB) | **175,471** (171 KiB) | `public, max-age=60` | 270 releases, 687 sections, 2,745 bullets |
| `/api/library/feeds/hub` (Explore) | 200 | **199,740** | **31,777** | none | 340 JSON objects |
| Google Fonts CSS (DM Sans + Fraunces) | 200 | 8,361 | — | (Google) | 19 `@font-face`, 7 unique WOFF2 URLs |
| Google Fonts Material Symbols WOFF2 | 200 | **323,576** | — | (Google) | Variable icon font, render-blocking stylesheet at `frontend/index.html:17` |

   **About CHANGELOG is not in the JS bundle.** The bundle has 0 occurrences of `### Highlights` and 0 `## [1.x.y` headings. About fetches `/release-notes.json` at runtime (`frontend/src/pages/AboutPage.tsx:47-53`; route `projectionist/web/spa_routes.py:163-172`). `docs/HELP.md` (96,062 B) and `docs/PRIVACY.md` (23,255 B) **are** in the bundle via `?raw` imports (`frontend/src/pages/HelpPage.tsx:5`, `frontend/src/pages/PrivacyPage.tsx:5`).

3. **Page timing** (Lighthouse missing; Playwright Chromium 1440×900 desktop, plus a 390×844 cold profile; "slow 4G" = 150 ms RTT, 1.6 Mbps down, 750 kbps up, 4× CPU throttle, cache disabled):

| Page | Profile | FCP | LCP | CLS | DOM elements (CDP nodes) | Transfer | Long tasks | Style recalc | Ready |
|---|---|---|---|---|---|---|---|---|---|
| `/login` anon | LAN cold | 252 ms | 252 ms | 0.0001 | 42 (97) | 2,471 KB | 0 | 6 ms | input at 255 ms |
| `/login` anon | LAN warm | 108 ms | 108 ms | 0 | 42 | 4 KB | 0 | 4 ms | 99 ms |
| `/login` anon | **slow 4G + 4× CPU, cold** | **12,612 ms** | 12,612 ms | 0 | 42 | 2,471 KB | — | — | **12,625 ms** |
| `/about` anon | LAN cold | 220 ms | 220 ms | 0.065–0.069 | **7,048 (15,783)** | 3,071 KB | 2 / 143 ms | **362 ms** | release list at 326–451 ms |
| `/about` anon | warm, 4× CPU | 428 ms | 428 ms | 0.065 | 7,048 | 5 KB | 3 / 411 ms | 338 ms | 973 ms |
| `/about` anon | **slow 4G + 4× CPU, cold** | 12,628 ms | 12,628 ms | — | 7,048 | 3,071 KB | — | — | **release list at 16,706 ms** |
| `/chat` owner | LAN cold | 236 ms | **1,208 ms** | 0.0023 | 199 (369) | 2,614 KB | 0 | 72 ms | **24 API calls** |
| `/explore` owner | LAN warm | 116 ms | 860 ms | **0.096** | 4,593 (7,403) | 204 KB | 0 | 65 ms | 6–7 API calls |
| `/explore` owner | warm, slow 4G + 4× CPU | 424 ms | 424 ms | 0.096 | 4,593 | 204 KB | 3 / 386 ms | 215 ms | — |
| `/search?media_type=movie` owner | LAN warm | 116 ms | 988 ms | 0.0065 | 1,335 | 56 KB | 0 | 81 ms | — |

   About release panel alone: 6,988 elements and 2,745 `<li>`. Estimate (not measured): with gzip the cold `/login` critical path would be about 705 KB, roughly 3.5–4.5 s on the same slow-4G profile.

4. **Bundle composition.** I ran `git archive 94fcd3f` into a temp dir, then `npm ci` and `vite build --sourcemap`. Output hashes were **identical** to QA (`index-buFnxk8x.js`, `index-DlGI-Pbi.css`). Bytes were attributed from the source map with `source-map-js`. Vite warned "Some chunks are larger than 500 kB".

| Contributor (minified bytes in the single chunk) | KiB | Needed on `/login`? |
|---|---|---|
| `hls.js` | **513.0** | No (`/watch`, `/live` only; `frontend/src/components/theater/TheaterPlayer.tsx:2`) |
| `src/components/**` | 360.5 | Partly |
| `src/lib/**` | 264.9 | Partly |
| `react-dom` | 127.0 | Yes |
| Admin/owner pages (`pages/admin` 103.3 + ConfigPage 35.8 + ScheduledTasks 21.1 + StagedAugmentations 17.8 + Dashboard 15.5 + Holidays 12.2 + Mail 11.2 + AccessRequests 7.1 + Logs 6.4 + LlmUsage 5.9) | **≈236** | No (owner only) |
| `docs/HELP.md?raw` + `docs/PRIVACY.md?raw` | **115.1** | No |
| Markdown stack (micromark, mdast, hast, property-information…) | ≈110 | No |
| `src/api/**` + `src/hooks/**` | 89.6 | Partly |
| All npm packages | 832.1 | — |
| **Total** | 2,128 | — |

5. **Test coverage and CI at `94fcd3f`.**
   - Floor: `pyproject.toml:72` `addopts = "--cov=projectionist --cov-report=term-missing --cov-fail-under=74"`, and the same floor in `.github/workflows/ci.yml:48`.
   - CI run 40801000625 for `94fcd3f` (via `gh run view --log-failed`): `2749 passed, 43 skipped … in 937.14s (0:15:37)`, `Total coverage: 76.74%`. Playwright had `2 failed, 108 passed (3.9m)`. The failures were `e2e/explore.spec.ts:10` (both attempts timed out at 1.0 m) and `e2e/mobile-native.spec.ts:210`. `release-perf.spec.ts` passed in 13.6 s. The Lint workflow run 40801000691 failed on `ruff check`. `docker-smoke` succeeded.
   - Local timed subset from the temp archive (`PYTHONPATH=<archive>`, `-o addopts=""`, verified `projectionist.__file__` resolved to the archive): `tests/test_api_authz.py tests/test_youth_guest_phase4.py` gave **46 passed in 12.48 s**.
   - Main history: `gh run list --branch main --workflow CI --limit 60` showed **33 failure / 27 success**. The last success was 2026-10-24T01:12Z (`71bd4b2`). Every one of the 15 most recent main runs (`26accd2` … `94fcd3f`) failed.

6. **Dependency audit** (temp archive lockfiles from `94fcd3f`):
   - `frontend/`: `npm audit --omit=dev --audit-level=high` reported **2 moderate** (`react-router` 6.0.0–7.17.0: GHSA-wrjc-x8rr-h8h6 open redirect via backslash; GHSA-337j-9hxr-rhxg SSR-only) and **0 high in production deps**.
   - `frontend/`, full audit: 4 (3 moderate, 1 high). The high is `vite` ≤ 6.4.3 (dev server path traversal), and `esbuild` ≤ 0.24.2 is moderate. Both are dev-only.
   - Root `package-lock.json` (Playwright): **0 vulnerabilities**.
   - Python: **no lockfile at `94fcd3f`**. CI installs `pip install ".[web,dev,mcp]"` with unpinned ranges (`ci.yml:30`), so this was not audited.

7. **Timed API reads on QA** (owner session, n=3 each unless noted, curl `time_total`):

| Endpoint | Bytes | Time |
|---|---|---|
| `GET /api/health` (anon) | 35 | 14.8–16.9 ms |
| `GET /api/health` (with session cookie) | 35 | 15.0–16.6 ms |
| `GET /api/features` (anon) | — | 30.5–36.2 ms |
| `GET /api/features` (owner) | 1,498 | 71.4–74.6 ms |
| `GET /api/auth/me` | 508 | 72.6–84.0 ms |
| `GET /api/live-channels/guide` (Live Off) | 342 | 72.5–80.2 ms |
| `GET /api/notifications` | 22,767 | 93.2–94.9 ms |
| `GET /api/chat/threads` | 2,870 | 94.5–109.7 ms |
| `GET /api/library/feeds/hub` | 199,740 | 215.9–239.0 ms |
| `GET /api/library/feeds/continue-watching?limit=12` | 14,388 | 754–1,045 ms (1,613 ms in-browser) |
| `GET /api/library/query?media_type=movie` | 22,931 | **652.6–670.8 ms** |
| same, `limit=24` | 22,004 | 347.5 ms |
| **5 × Movies query in parallel** | — | **3.727–3.731 s each** (wall 3.76 s) |
| `/api/health` sent 150 ms after 1 Movies query | — | **645.8 / 645.9 ms** (two trials) |
| `/api/health` sent 200 ms after 3 parallel Movies queries | — | **2,155 ms** |
| `POST /api/auth/local/login` (once) | — | 520 ms |

   The concurrency probe was 5 normal reads: no fuzzing, no authz probing.

8. **Host (read-only via `ssh automat`):**
   - `docker stats`: prod `projectionist` 474 MiB / 0.29% CPU / 42 PIDs; QA 309 MiB / 0.26%.
   - Both containers: `RestartPolicy=unless-stopped`, no memory or CPU limits.
   - Prod DB `config/projectionist.db` is 227,655,680 B. The `config/tunarr` dir is 3.7 GB. Logs are 5 MiB × 3 rotated.
   - Appdata Backup plugin: cron `3 3 * * 1` (weekly), `keepMinBackups: 4`, `verifyBackup: no`. Latest `ab_20261026_030301/projectionist.tar.gz` is 1,920,393,141 B.
   - No monitoring or alerting container (Uptime Kuma, Gatus, Prometheus, autoheal, and similar) was found.
   - Images: 11 `romwil/projectionist` tags at about 750 MB each; `docker system df` shows 17.76 GB reclaimable.
   - QA log: 23,186 lines in 12 h, 0 `ERROR`/Traceback lines.

**Cleanup:** temp archive, `node_modules`, source map, cookie jar, and downloaded payloads were deleted. No application code, `_status.md`, or other department docs were modified or read (beyond `00_` platform map and `_status.md` handoff).

---

## 13. Strengths

### PERF-001: Protect the SQLite write serializer and DB-free hot paths

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Cross-cutting |
| Persona(s) | All |
| Category | Back-end / data |
| Severity | High |
| Impact | 5 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 15.0 (5×3×1.0÷1) |
| Verdict | Protect |
| Dependencies | PERF-008, PERF-024 |
| Labels | sqlite, wal, concurrency, protect |

**Evidence:**
- Dedicated writer thread: `projectionist/library/db/_schema.py:41-61` (`run_write` → `WriteSerializer`, with `run_with_db_lock_retry` inside the worker so sleeps never pin the loop).
- Pragmas: `projectionist/library/db/_shared.py:95-97` (`SQLITE_BUSY_TIMEOUT_MS = 30_000`, `SQLITE_SYNCHRONOUS = "NORMAL"`); `projectionist/library/db/_users.py:756-768` (`journal_mode=WAL`, `busy_timeout`).
- Health and documents skip SQLite: `projectionist/web/auth.py:449-453`.
- Measured: health 15 ms with or without a session; HTML TTFB 16–25 ms.

**Current state:** This is the right concurrency model for single-file SQLite: one writer, many short WAL readers, and a write-queue stats hook (`write_queue_stats`, `_schema.py:70-72`).

**Root cause:** Earlier incidents (comment at `auth.py:449-451`: a contended file "was stalling first paint on every page") were fixed at the cause.

**Recommendation:** Keep it. Expose `write_queue_stats()` on the proposed readiness and metrics endpoints (PERF-025). **Protect this:** every mutation goes through `run_write`/`try_run_write`, and no new middleware touches SQLite for non-`/api/` paths.

**Rationale:** Regressing this brings back the 30 s stalls on every page. The alternative (Postgres) adds an operational burden with no household-scale benefit.

**User story:** As a household member, I want pages to load even while a library sync is writing, so the app never "hangs".

**Acceptance criteria:**
- [ ] A test fails if a new `sqlite3.connect` write path bypasses `run_write`
- [ ] `/api/health` and `/` stay DB-free

**Success metric:** zero `database is locked` errors in logs per week.

**Validation:** run a library sync while loading `/about` and `/explore`; TTFB stays < 50 ms.

### PERF-002: Protect idempotent-only retries with jittered backoff and per-host circuit breakers

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Cross-cutting |
| Persona(s) | All; owner during Plex/Tunarr outages |
| Category | Reliability |
| Severity | Medium |
| Impact | 4 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 8.0 |
| Verdict | Protect |
| Dependencies | — |
| Labels | retries, circuit-breaker, integrations |

**Evidence:**
- `projectionist/connectors/http.py:24-30`: "Idempotent reads only. Mutating methods never retry". 3 attempts, 0.25 s base delay, 8 s max, `Retry-After` capped at 30 s with jitter.
- `projectionist/connectors/http.py:198`: `attempts = … if _is_idempotent_method(...) else 1`; `:208` uses `urlopen(..., timeout=timeout)`.
- `projectionist/circuit_breaker.py:21-25`: `QUARANTINE_THRESHOLD = 3`, `HOST_CIRCUIT_COOLDOWN_SECONDS = 60`.

**Current state:** This is textbook client resilience. It fails fast when Plex or Tunarr is down instead of hammering the socket.

**Root cause:** It was designed deliberately (module docstring `circuit_breaker.py:1-7`).

**Recommendation:** Keep it. Extend the same breaker and timeout policy to LLM providers (PERF-022). **Protect this:** never add retries to POST/PUT/DELETE; keep the 60 s host cooldown.

**Rationale:** Prevents retry storms and duplicate *arr adds. Rejected alternative: generic `tenacity` decorators everywhere, which make retry policy invisible.

**User story:** As a member, I want Explore to still render when Plex blips, so one outage doesn't break the app.

**Acceptance criteria:**
- [ ] Existing connector tests keep asserting no retry on mutating methods

**Success metric:** no repeated identical POSTs in *arr logs.

**Validation:** stop Plex on QA; Explore returns within 2 s with degraded rails.

### PERF-003: Protect the release page-speed harness running inside CI

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Cross-cutting |
| Persona(s) | Maintainer |
| Category | Performance governance |
| Severity | Medium |
| Impact | 3 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 6.0 |
| Verdict | Protect |
| Dependencies | PERF-020 |
| Labels | perf-budget, ci, playwright |

**Evidence:**
- `e2e/release-perf.spec.ts:22-28` sets sanity ceilings: `contentMs: 2500, lcpMs: 2500, cls: 0.1, documentServerMs: 800, jsonServerMs: 800`.
- `frontend/perf/baseline.json` covers About, Explore, Movies, Inbox, and Live.
- `docs/RELEASE.md:151-157`.
- CI at `94fcd3f`: "release-perf … stay within budget (13.6s)", passed.

**Current state:** Few hobby-scale projects have a committed perf baseline. It already caught server-time regressions (budget formula in `baseline.json` `tolerance`).

**Root cause:** —

**Recommendation:** Keep it, and tighten as in PERF-020. **Protect this:** do not move it out of `npm run test:e2e`.

**Rationale:** It is the only automated perf signal the project has.

**User story:** As the maintainer, I want regressions flagged on the PR, so slow pages don't ship.

**Acceptance criteria:**
- [ ] Spec remains in the default Playwright project

**Success metric:** spec runs on 100% of PRs.

**Validation:** `npm run test:release-perf` passes locally.

### PERF-004: Protect the Hub pull-only, pull-before-stop rollout with health smoke

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Admin |
| Persona(s) | Maintainer / owner-operator |
| Category | Deployment |
| Severity | Medium |
| Impact | 3 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 6.0 |
| Verdict | Protect |
| Dependencies | PERF-013 |
| Labels | rollout, deployment, docker |

**Evidence:**
- `scripts/unraid-rollout.sh:131-133`: `docker pull "$IMAGE"` and only then `stop_rm_container`, so the outage window excludes the pull.
- `:254-280`: health smoke requiring `"status":"ok"`, with fallbacks.
- `:315-317`: prints `/app/.build-info`.
- `Dockerfile:115-116`: `HEALTHCHECK --interval=30s --timeout=5s --retries=3`.
- Host shows prior tags retained (1.37.66–1.37.72).

**Current state:** Downtime per rollout is just container restart plus migrations. Previous images are available for rollback.

**Root cause:** —

**Recommendation:** Keep it. Add a DB snapshot step and a `rollback.sh` (PERF-013). **Protect this:** pull-only, with no host builds for prod.

**Rationale:** Reproducible, reversible deploys are the cheapest reliability win.

**User story:** As the owner, I want upgrades to take seconds and be reversible.

**Acceptance criteria:**
- [ ] Pull failure aborts before the running container is stopped (already true)

**Success metric:** rollout downtime < 60 s.

**Validation:** time `rollout.sh` on QA with Path B.

### PERF-005: Protect LLM usage accounting and conservative background batches

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Owner |
| Persona(s) | Owner |
| Category | Cost |
| Severity | Low |
| Impact | 3 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 3.0 |
| Verdict | Protect |
| Dependencies | PERF-022 |
| Labels | llm, cost, telemetry |

**Evidence:**
- `projectionist/telemetry/llm_usage.py:1-6`: "Persists call metadata (never prompt/completion text)… unknown models keep token totals without inventing a USD figure", with per-purpose constants for chat, tool, embed, logline, and others.
- `projectionist/scheduler/tasks/llm_logline_enrichment.py:7-9,33-34`: batch 5, every 24 h, "to avoid burning API credits".

**Current state:** The owner can see spend by purpose, and background spend is throttled by default.

**Root cause:** —

**Recommendation:** Keep it, and add the budget cap (PERF-022). **Protect this:** never log prompt text in usage rows.

**Rationale:** This makes spend visible without creating a privacy liability.

**User story:** As an owner, I want to see what the curator costs me per month.

**Acceptance criteria:**
- [ ] Usage rows never contain message text

**Success metric:** owner can answer "what did chat cost last month" in under 1 minute.

**Validation:** Admin → Health → Usage shows tokens by purpose.

### PERF-006: Protect the small runtime footprint and the healthy backend suite

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Cross-cutting |
| Persona(s) | Owner-operator |
| Category | Cost / quality |
| Severity | Medium |
| Impact | 3 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 6.0 |
| Verdict | Protect |
| Dependencies | PERF-010 |
| Labels | footprint, tests, coverage |

**Evidence:**
- `docker stats`: prod 474 MiB, 0.29% CPU; QA 309 MiB.
- Image about 752 MB.
- CI at `94fcd3f`: 2,749 passed, 76.74% coverage vs `--cov-fail-under=74` (`pyproject.toml:72`, `.github/workflows/ci.yml:48`).

**Current state:** The app runs comfortably alongside a dozen other Unraid services, and the backend tests are broad and green.

**Root cause:** —

**Recommendation:** Keep the floor at 74% or raise it to 76%. Never lower it. **Protect this:** keep Debian slim plus `ffmpeg` as the only system dependency.

**Rationale:** A low footprint makes self-hosting viable.

**User story:** As an owner, I want Projectionist to be a good neighbour on my server.

**Acceptance criteria:**
- [ ] Idle RSS < 600 MiB with Live Off

**Success metric:** RSS trend flat release over release.

**Validation:** `docker stats` after 24 h uptime.

---

## 14. Weaknesses (sorted by priority score)

### PERF-007: Compress responses and mark hashed assets immutable

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Cross-cutting |
| Persona(s) | Low-bandwidth mobile user, remote member, first-time visitor |
| Category | Front-end performance |
| Severity | High |
| Impact | 5 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | **15.0** (5×3×1.0÷1) |
| Verdict | Fix |
| Dependencies | Blocks PERF-020 byte budget |
| Labels | compression, caching, bytes, quick-win |

**Evidence:**
- No `GZipMiddleware` or Brotli anywhere in `projectionist/` (`git grep -n -i "gzip\|GZip\|brotli" 94fcd3f -- projectionist` matched nothing relevant).
- `projectionist/web/app.py:616` mounts `StaticFiles(directory=FRONTEND_DIST / "assets")` with default headers.
- Measured with `Accept-Encoding: gzip, br`: the JS came back as **2,178,954 B identity** (645,698 B if gzipped). The CSS was 344,428 B (56,441 B), the hub JSON 199,740 B (31,777 B), and `release-notes.json` 613,415 B (175,471 B).
- No `cache-control` on `/assets/*`; only ETag and Last-Modified.
- Cold `/login` on slow 4G + 4× CPU: **FCP 12,612 ms**, transfer 2,471 KB.

**Current state:** Every cold visit pays about 2.5 MB. Browsers fall back to heuristic freshness (a fraction of the time since Last-Modified), so shortly after each release, repeat visits revalidate assets that can never change.

**Root cause:** The app was designed for LAN use, where bytes are free. FastAPI does not compress by default.

**Recommendation:**
1. Add `app.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=6)` in `projectionist/web/app.py`. Exclude `text/event-stream`, because chat SSE must not buffer. Check SSE flushing by test and use an exclude-paths wrapper for `/api/chat/stream` and `/api/admin/logs/stream`.
2. Serve `/assets/*` with `Cache-Control: public, max-age=31536000, immutable`, using a `StaticFiles` subclass that overrides `file_response`.
3. Serve the HTML shell with `Cache-Control: no-cache`.
4. Later: pre-compress at build (`vite-plugin-compression` → `.br`/`.gz`) and serve the precompressed file when `Accept-Encoding` allows.

**Rationale:**
- This cuts about 72% of cold bytes (2.53 MB → about 705 KB) for one line of code.
- It helps every remote member and every phone.
- Rejected: relying on the public proxy or CDN to compress. That is unverified, does not cover LAN or Tailscale clients, and leaves the theater and QA paths uncovered.

**User story:** As a member on my phone, I want the app to open in a few seconds, so I don't give up and open Plex instead.

**Acceptance criteria:**
- [ ] `curl -sI -H 'Accept-Encoding: gzip' :8792/assets/index-*.js` shows `content-encoding: gzip` and `cache-control: public, max-age=31536000, immutable`
- [ ] `/api/chat/stream` still streams tokens incrementally (e2e chat spec green)
- [ ] HTML shell has `cache-control: no-cache`

**Success metric:** cold `/login` transfer ≤ 750 KB now (≤ 400 KB after PERF-011); slow-4G FCP ≤ 5 s.

**Validation:** re-run the cold Playwright profile in Scope & method step 3, then compare the table.

### PERF-008: Stop blocking the event loop in `async` handlers (Movies query)

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Consumer |
| Persona(s) | Every concurrent member; lobby theater viewers; health checker |
| Category | Back-end performance / reliability |
| Severity | High |
| Impact | 5 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | **7.5** (5×3×1.0÷2) |
| Verdict | Fix |
| Dependencies | PERF-023; enables SLO "loop responsiveness" (PERF-025) |
| Labels | asyncio, event-loop, concurrency, sqlite |

**Evidence:**
- `projectionist/web/library_routes.py:1347` `async def library_query_endpoint(`; `:1436` `result = query_library(_db(), filters)`, a synchronous call made directly on the loop (only the `semantic_query` branch awaits at `:1434`).
- Main and theater share one loop: `projectionist/web/__main__.py:152` `await asyncio.gather(main_server.serve(), theater_server.serve())`.
- Measured on QA:
  - Single Movies query: 653–671 ms.
  - **5 in parallel: 3.727–3.731 s each** (perfect serialization).
  - `/api/health` (normally 15 ms) took **646 ms** when sent 150 ms after one query started, and **2,155 ms** during three.
- Other `async def` route handlers at this commit that may call sync work include `library_export_csv`, `create_saved_library_page`, `delete_library_items`, `delete_purge_candidates`, and `approve_staged_augmentation`. Run `git grep -n -A1 -E "^@(app|router)\.(get|post|put|patch|delete)\(" 94fcd3f -- projectionist/web | rg "async def"` to list them (14 handlers vs 292 sync).
- The middleware also calls `_settings()` (file read + decrypt) on the loop: `projectionist/web/auth.py:497`.

**Current state:** One member browsing Movies freezes chat SSE, Live polling, the lobby theater, and the healthcheck for the duration of the query.

**Root cause:** `async def` was used as a default rather than a contract. FastAPI only offloads plain `def` handlers to the threadpool. No rule or test enforces the boundary.

**Recommendation:**
1. Change `library_query_endpoint` to: `if filters.semantic_query: result = await query_library_async(...)`, `else: result = await run_in_threadpool(query_library, _db(), filters)`. Wrap `_sanitize_library_payload` the same way if it is heavy.
2. Audit the other 13 `async def` handlers the same way.
3. Move the middleware's `_settings()` into the existing `run_in_threadpool(_open_perimeter)` call (`auth.py:465-470`).
4. Add a regression test: start a Movies query in a thread and assert `/api/health` responds in < 100 ms using the `TestClient` plus a real server fixture. Or add a ruff/AST check that flags `async def` route functions calling known-sync `projectionist.library` functions without `await`/`run_in_threadpool`.
5. Optionally enable `asyncio` debug slow-callback logging (`loop.slow_callback_duration = 0.1`) in QA to find the rest.

**Rationale:**
- Household concurrency (evening, 3–5 people) is exactly when this bites.
- Docker's 5 s × 3 healthcheck could flap under worse queries.
- Rejected: more uvicorn workers. That breaks the in-process scheduler, write serializer, rate limiter, and SSE state, and it hides the bug.

**User story:** As a member chatting while my partner browses Movies, I want my chat to keep streaming smoothly.

**Acceptance criteria:**
- [ ] `/api/health` p99 < 100 ms while 5 Movies queries run concurrently on QA
- [ ] 5 parallel Movies queries complete in ≤ 1.5 s each (threadpool parallel reads under WAL)
- [ ] Guard test or lint fails on a new sync DB call inside `async def` routes

**Success metric:** loop-responsiveness SLO (p99 < 250 ms) met for 28 days.

**Validation:** repeat the Scope & method step 7 concurrency probe.

### PERF-009: Make backups nightly, verified, app-consistent, and restore-tested

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Admin |
| Persona(s) | Owner-operator; every member (their history) |
| Category | Reliability / backup |
| Severity | High |
| Impact | 5 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | **7.5** |
| Verdict | Fix |
| Dependencies | PERF-013, PERF-025 |
| Labels | backup, restore, rpo, rto, sqlite |

**Evidence:**
- Host Appdata Backup: cron `3 3 * * 1` (weekly), `keepMinBackups: "4"`, `verifyBackup: "no"`. Latest archive `ab_20261026_030301/projectionist.tar.gz` is 1,920,393,141 B; the `config/tunarr` dir is 3.7 GB, against a 218 MB DB.
- No `backups/` dir under prod `config/`.
- In-app backup is a manual owner download only: `projectionist/web/app.py:2851-2859` → `projectionist/web/backup.py:27-76`.
- `docs/DOCKER.md:320-338` documents a manual `sqlite3 .backup` recipe that nothing runs.
- No restore drill is documented or recorded.

**Current state:** RPO is up to 7 days. RTO is unknown. A file-level tar of a live WAL database may be inconsistent unless the container is stopped; the plugin's per-container stop setting was not verifiable without `jq`/`python3` on the host, so this part is *Suspected*. Tunarr bloat makes each backup about 2 GB, and slow.

**Root cause:** Backups were delegated to a generic host plugin with no app-level, DB-aware job or restore test.

**Recommendation:**
1. Add a scheduler task `db_backup_nightly` at 04:15 local. It runs `sqlite3` `src.backup(dst)` into `DATA_DIR/backups/projectionist-YYYYMMDD.db`, then `PRAGMA integrity_check` on the copy (must return `ok`), then gzips it, copies `settings.json`, and keeps 14 daily and 8 weekly copies.
2. Export `backup_last_success_ts` and `backup_last_size` (PERF-025). Send an Apprise alert if older than 26 h.
3. Exclude `config/tunarr` and `theater-poster-cache` from the Appdata Backup job, or back them up monthly. They can be regenerated.
4. Write `scripts/restore-db.sh <file>` (stop container → move current DB aside → copy → start → health). Drill it on QA `:8792` quarterly and record the RTO.

**Rationale:**
- Watch history, ratings, and chats are the product's memory, and losing a week is user-visible.
- Rejected: Litestream. It is excellent but adds a sidecar and an object store, which is overkill at 218 MB. Revisit if RPO < 1 h becomes a requirement.

**User story:** As an owner, I want to know that a disk failure costs me at most a day, and I want to know how to restore.

**Acceptance criteria:**
- [ ] `DATA_DIR/backups` holds ≥ 7 nightly verified copies after a week
- [ ] A restore on QA from last night's copy completes in ≤ 30 min, and `/api/health/ready` is green after it
- [ ] An alert fires when the newest backup is older than 26 h

**Success metric:** backup freshness SLO 100% of days; one documented drill per quarter.

**Validation:** QA restore drill; check `integrity_check` output in logs.

### PERF-010: Restore green CI on main and make it a release precondition

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Admin |
| Persona(s) | Maintainer; indirectly all users |
| Category | Deployment / quality gates |
| Severity | High |
| Impact | 4 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | **6.0** |
| Verdict | Fix |
| Dependencies | PERF-003, PERF-020 |
| Labels | ci, flaky-tests, release-gate |

**Evidence:**
- `gh run list --branch main --workflow CI --limit 60`: **33 failure / 27 success**. The last success was 2026-10-24 (`71bd4b2`). The 15 latest runs, from `26accd2` (1.37.63) to `94fcd3f`, all failed.
- At `94fcd3f`: `e2e/explore.spec.ts:10` "Explore hub › loads feed rails, pulse, and Related titles hub" timed out at 1.0 m twice. `e2e/mobile-native.spec.ts:210` failed `toBeVisible`. Lint's `ruff check` failed.
- `docs/RELEASE.md:157`: "A red Actions job does not block a human rollout"; checklist `:354` repeats it.

**Current state:** Nine patch releases shipped over red, so red is now noise. The Explore failure is a 60 s timeout on the page with a 1.6 s uncached Plex rail (PERF-019), so it may be a real perf signal being ignored (*Likely*).

**Root cause:** No branch protection requiring CI. Flaky specs are not quarantined. Release docs normalise the bypass.

**Recommendation:**
1. Fix or `test.fixme()` the two specs with an owner and a date, and fix `ruff` findings.
2. Enable branch protection on `main` requiring `CI / test`, `CI / docker-smoke`, and `Lint`.
3. Change `docs/RELEASE.md:157` and `:354` to: "A red Actions job blocks `docker-release.sh` unless `--override-red-ci "<reason>"` is passed; the reason is written into the GitHub release notes."
4. Have `scripts/docker-release.sh` check `gh run list --commit $(git rev-parse HEAD) --json conclusion` before building.

**Rationale:**
- The perf budget, Docker smoke, and coverage floor only protect anyone when red means stop.
- Rejected: deleting the failing e2e specs, because they cover the Explore journey.

**User story:** As the maintainer, I want a red build to mean "don't ship", so regressions are caught before Hub.

**Acceptance criteria:**
- [ ] 10 consecutive green main runs
- [ ] `docker-release.sh` refuses on red without an override

**Success metric:** ≥ 90% green main runs over 30 days.

**Validation:** `gh run list --branch main --limit 20`.

### PERF-011: Split the single 2.08 MiB bundle by route and role

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Public, Consumer, Owner |
| Persona(s) | First-time visitor, mobile member, youth |
| Category | Front-end performance |
| Severity | High |
| Impact | 4 |
| Effort | M |
| Confidence | Confirmed |
| Priority score | **4.0** (4×3×1.0÷3) |
| Verdict | Fix |
| Dependencies | PERF-007 |
| Labels | code-splitting, vite, bundle, hls |

**Evidence:**
- One JS chunk, `index-buFnxk8x.js`, 2,178,954 B. The Vite build warns "Some chunks are larger than 500 kB".
- `frontend/vite.config.js:20-23` has no `manualChunks`.
- `frontend/src/AppRoutes.tsx` has 44 static `./pages/` imports, such as `:4` `ConfigPage`, `:11` `AdminLayout`, `:19` `LivePage`, `:21` `LibraryWatchPage`.
- No `React.lazy` (the only dynamic imports are `uiPrefs.js` and `downloadAdminBackupSnapshot`).
- Source-map attribution: hls.js 513.0 KiB, owner/admin pages about 236 KiB, `HELP.md`+`PRIVACY.md` raw 115.1 KiB, markdown stack about 110 KiB.

**Current state:** A youth member opening `/login` downloads the HLS player, every Admin page, and the full help and privacy markdown.

**Root cause:** Routes were added over time with static imports, and nothing enforces a byte budget.

**Recommendation:**
1. Convert `AppRoutes.tsx` page imports to `React.lazy(() => import("./pages/X"))` with a shared `<Suspense fallback={<RouteSkeleton/>}>`. Keep `LoginPage`, `ChatPage`, and `AppShell` eager.
2. Group chunks: `admin-*` (all `/admin/*` and `ConfigPage`), `player` (`TheaterPlayer` → `hls.js`, dynamically imported in `LibraryPlayer`/`LivePlayer`), `docs` (`HelpPage`, `PrivacyPage` with their `?raw` markdown), and `markdown` (react-markdown + remark-gfm + rehype-sanitize, used by chat; load on first render of a markdown block).
3. Set `build.chunkSizeWarningLimit: 250` so the warning becomes a failure in CI via a bundle-size script.

Expected `/login` JS after the split: ≤ 450 KiB raw / ≤ 150 KiB gzip (*estimate*).

**Rationale:**
- Bytes, parse, and compile time dominate mobile cold start. At 4× CPU, script time on `/login` was 148 ms even warm.
- Rejected: an SSR rewrite. It is not needed for a signed-in app.

**User story:** As a youth member on a tablet, I want sign-in to appear immediately.

**Acceptance criteria:**
- [ ] `/login` loads ≤ 150 KiB gzip JS
- [ ] `hls.js` is fetched only on `/watch` or `/live`
- [ ] Admin chunk is never requested by a member session (Playwright network assertion)

**Success metric:** slow-4G + 4× CPU cold `/login` FCP ≤ 4 s (with PERF-007).

**Validation:** source-map attribution re-run, then the cold Playwright profile.

### PERF-012: Add readiness checks, metrics, and an alert path

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Admin |
| Persona(s) | Owner-operator, maintainer |
| Category | Observability |
| Severity | High |
| Impact | 4 |
| Effort | M |
| Confidence | Confirmed |
| Priority score | **4.0** |
| Verdict | Fix |
| Dependencies | PERF-025, PERF-009 |
| Labels | observability, alerting, health, metrics |

**Evidence:**
- `projectionist/web/app.py:1269-1271`: `def health(): return {"status": "ok", "version": __version__}`, which is constant.
- No `prometheus`, `/metrics`, `opentelemetry`, `sentry`, or `statsd` anywhere (`git grep` empty).
- No request-id or latency logging (`git grep -i "request_id\|x-request-id\|duration_ms"` in `projectionist/web` only hits playback payload fields).
- `projectionist/logging_config.py`: file log with redaction, 5 MiB × 3, JSON optional via `LOG_FORMAT`.
- `projectionist/scheduler/engine.py:35`: "Quarantine state is held in-memory and does not persist across restarts".
- The host runs no monitoring container. `Dockerfile:115-116` HEALTHCHECK only marks status; Docker does not restart on `unhealthy` without an autoheal helper.

**Current state:** A wedged scheduler, a locked DB, or a blocked loop all still report `ok`. Incidents are found by members.

**Root cause:** Health was designed as liveness only (correctly DB-free; see PERF-001), and no readiness or alerting layer was ever added.

**Recommendation:**
1. Add `GET /api/health/ready` (unauthenticated, LAN-only via the existing WAN interlock). It runs `SELECT 1` on a read connection with a 1 s timeout and checks the scheduler heartbeat (< 10 min since the last loop tick), the `write_queue_stats().depth` (< 50), and the newest backup age (PERF-009). It returns 503 with failing check names.
2. Add `GET /api/metrics` (owner session or `PROJECTIONIST_METRICS_TOKEN`) in Prometheus text format with:
   - `http_request_duration_seconds` histogram by route group (from a middleware)
   - `sqlite_write_queue_depth`
   - `scheduler_task_last_success_timestamp{task}`
   - `scheduler_task_quarantined{task}`
   - `llm_tokens_total{purpose}`
   - `backup_last_success_timestamp`
3. Run Uptime Kuma (or Gatus) on the host, probing `:8788/api/health/ready` every 60 s and notifying through the owner's Apprise URL.
4. When a scheduler task enters quarantine, raise an owner Inbox notification plus Apprise.

**Rationale:**
- Gets detection time from "whenever someone complains" to under 5 min.
- Rejected: a full Grafana/Prometheus stack, which is too heavy for one household. Expose `/metrics` so it is optional.

**User story:** As the owner, I want to be told when Projectionist is unhealthy before my family notices.

**Acceptance criteria:**
- [ ] Ready returns 503 when the DB file is chmod'ed unreadable on QA
- [ ] Killing the scheduler thread on QA produces an alert within 10 min
- [ ] `/api/metrics` exposes the six series above

**Success metric:** mean time to detect < 5 min in a QA game-day.

**Validation:** QA game-day: stop Plex, lock DB, block the loop; confirm alerts fire.

### PERF-013: Snapshot before migrations and refuse to boot on a newer schema

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Admin |
| Persona(s) | Owner-operator |
| Category | Deployment / data safety |
| Severity | Medium |
| Impact | 4 |
| Effort | S |
| Confidence | Likely |
| Priority score | **3.2** (4×2×0.8÷2) |
| Verdict | Fix |
| Dependencies | PERF-009, PERF-004 |
| Labels | migrations, rollback, schema |

**Evidence:**
- `projectionist/library/db/migrations.py:320-331`: `run_migrations` applies every unapplied migration on `Database()` open and records the versions. There is no check for `max(applied) > CURRENT_SCHEMA_VERSION` (`:317`), so an older image silently runs against a newer schema.
- `scripts/unraid-rollout.sh:283-320` takes no snapshot before starting the new image.
- Releases ship at about two per day (1.37.63 → 1.37.72 between 10-25 and 10-28).

**Current state:** Rolling back after a bad migration means either running old code on a new schema (undefined behaviour) or restoring the weekly backup (up to 7 days lost).

**Root cause:** Migrations are treated as always-forward, with rollback never designed.

**Recommendation:**
1. In `run_migrations`, if `max(applied) > CURRENT_SCHEMA_VERSION`, log an error and raise `SchemaTooNewError`. The container then fails health with a clear message, and the rollout aborts.
2. In `unraid-rollout.sh`, before `stop_rm_container`, run `docker exec "$CONTAINER_NAME" python -c "<sqlite backup to /config/backups/pre-<old>-to-<new>.db>"` and keep the last 5.
3. Add `scripts/rollback.sh X.Y.Z`: restore the matching pre-snapshot, then `rollout.sh X.Y.Z`.

**Rationale:**
- At this release cadence, a bad migration is a matter of time.
- Rejected: down-migrations. They are high effort and rarely correct for SQLite `ALTER` limits.

**User story:** As the owner, I want one command that undoes a bad upgrade without losing today's data.

**Acceptance criteria:**
- [ ] Booting 1.37.71 on a 1.37.72-migrated DB fails fast with `SchemaTooNewError`
- [ ] `rollback.sh` on QA restores and boots the previous tag in ≤ 5 min

**Success metric:** rollback RTO ≤ 5 min, measured on QA.

**Validation:** QA Path B drill: upgrade, rollback, data intact.

### PERF-014: Paginate About release notes instead of rendering 2,745 bullets

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Public |
| Persona(s) | Curious visitor, member, mobile user |
| Category | Front-end performance / DOM size |
| Severity | Medium |
| Impact | 3 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | **3.0** |
| Verdict | Fix |
| Dependencies | PERF-007 |
| Labels | about, changelog, dom-size, handoff-followup |

**Evidence:**
- `frontend/src/pages/AboutPage.tsx:47-53` fetches all releases, and `:130-135` renders `<ReleaseNotesPanel releases={releases} showJumpLinks scrollable …/>`.
- `frontend/src/components/ReleaseNotesPanel.tsx:116,132,141,145` uses nested `releases.map → highlights.map / sections.map → bullets.map`, with no virtualization or slicing.
- `projectionist/web/spa_routes.py:163-172` sends `Cache-Control: public, max-age=60`.
- Measured:
  - 270 releases, **2,745 `<li>`, 6,988 elements in the panel, 7,048 on the page, about 15,700 CDP nodes**.
  - Style recalc 362–443 ms; long tasks 67–143 ms (LAN) and 411 ms total at 4× CPU.
  - CLS 0.065–0.069.
  - Payload 613,415 B raw / 175,471 B gzip.
  - Release list usable at **16.7 s** cold on slow 4G.
- `CHANGELOG.md` at `94fcd3f` is 504,167 B / 5,604 lines and grows every release.

**Current state:** The page cost grows linearly forever. Lighthouse's "excessive DOM size" threshold is 1,400 elements; About is at 5×.

**Root cause:** Its "full history" product choice has no paging. The JSON is generated whole.

**Recommendation:**
1. Generate `release-notes.json` with the newest 10 releases plus an index `[{version, date}]` of all releases, and per-minor archives `release-notes/1.37.json` etc.
2. About renders the 10 newest. The version jump combobox loads the archive for the selected minor on demand.
3. Wrap older releases in `<details>` (collapsed) so they don't lay out until opened.
4. Set `Cache-Control: public, max-age=300, stale-while-revalidate=86400` (content changes only on release).

**Rationale:**
- Cuts About's DOM by about 95% and its JSON by about 95% without losing history.
- Rejected: list virtualization. It breaks in-page anchor jumps and find-in-page.

**User story:** As a member tapping "What's new", I want to see recent changes instantly.

**Acceptance criteria:**
- [ ] About initial DOM ≤ 1,000 elements
- [ ] Initial release JSON ≤ 40 KB raw
- [ ] Jump to `1.20.0` still works (loads its archive)

**Success metric:** About slow-4G cold "release list visible" ≤ 5 s (with PERF-007 and PERF-011).

**Validation:** re-run the About rows of Scope & method step 3.

### PERF-015: Trim the 24-call chat boot and stop syncing the Plex watchlist on every load

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Consumer |
| Persona(s) | Every member opening chat |
| Category | Front-end / back-end efficiency |
| Severity | Medium |
| Impact | 3 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | **3.0** |
| Verdict | Fix |
| Dependencies | PERF-017 |
| Labels | api-fanout, plex, chat, waterfall |

**Evidence:**
- Playwright network log for owner `/chat`: **24 `/api/` calls**. They include `GET /api/features` ×3, `GET /api/auth/me` ×2, `POST /api/watchlist/sync` ×1, plus personas, persona, saved-library, setup/status, library/stats, reviews, reviews/prompts, anniversaries, system-config, jobs, notifications, watchlist, whispers, and messages for **two** threads plus feedback.
- In-browser durations for the slowest calls: features 521/485 ms, notifications 484 ms, auth/me 474 ms, watchlist/sync 453 ms (they queue behind each other).
- `frontend/src/App.tsx:251-252` `refreshWatchlist` → `runWatchlistSync({ direction: "pull" })`. The server side is `projectionist/web/app.py:3335-3345` (`sync_watchlist_with_plex`).
- Chat LCP 1,208 ms on LAN warm, vs 860 ms for Explore.

**Current state:** Every app boot makes a Plex round trip and a DB write, and duplicate bootstrap reads compete for the same threadpool and writer.

**Root cause:** Independent components each fetch their own bootstrap data, and there is no shared session/bootstrap query.

**Recommendation:**
1. Add `GET /api/bootstrap` returning `{me, features, setup_status, system_config, persona, unread_count}` in one call, used by `App.tsx` and shared via context.
2. Run watchlist pull-sync only on login, on Watchlist page open, and from a scheduler task every 30 min per user with sync enabled. Remove it from the app-boot effect.
3. Load only the active thread's messages, and defer reviews/prompts, anniversaries, whispers, and jobs until idle (`requestIdleCallback`).

**Rationale:**
- Fewer requests means less queueing in a single process, and it removes an external dependency from first paint.
- Rejected: HTTP/2 multiplexing. It doesn't reduce server work, and uvicorn serves h11.

**User story:** As a member, I want chat ready the moment I open the app.

**Acceptance criteria:**
- [ ] `/chat` cold boot ≤ 10 `/api/` calls
- [ ] No `POST /api/watchlist/sync` on a plain `/chat` load
- [ ] `/api/features` requested once per load

**Success metric:** Chat LCP ≤ 800 ms on LAN warm.

**Validation:** Playwright network-count assertion in `e2e/chat.spec.ts`.

### PERF-016: Self-host and subset fonts; replace the Material Symbols web font

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Cross-cutting |
| Persona(s) | Mobile member, privacy-minded member |
| Category | Front-end performance / third-party |
| Severity | Medium |
| Impact | 3 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | **3.0** |
| Verdict | Fix |
| Dependencies | — (also relevant to Trust batch) |
| Labels | fonts, third-party, render-blocking |

**Evidence:**
- `frontend/index.html:13` (DM Sans + Fraunces) and `:17` (Material Symbols Outlined) are render-blocking `<link rel="stylesheet">` tags to `fonts.googleapis.com`.
- Measured: brand CSS 8,361 B with 19 `@font-face` rules (7 WOFF2s); the Material Symbols WOFF2 is **323,576 B**.
- CSP has to allow `fonts.googleapis.com`/`fonts.gstatic.com` (response header).

**Current state:** First paint waits on a third-party DNS, TLS, and CSS round trip. Icons show as ligature text until a 316 KB font arrives, which is a CLS and FOUT risk.

**Root cause:** It was the convenient default during early design.

**Recommendation:**
1. Self-host DM Sans and Fraunces as Latin-subset WOFF2 (`fontsource` packages or `glyphhanger`), with `font-display: swap` and `<link rel="preload">` for the two body weights only.
2. Replace Material Symbols with inline SVG components for the icons actually used (about 60 or fewer; grep `material-symbols` class usage), or a subsetted icon font (≤ 20 KB).
3. Drop Google hosts from the CSP.

**Rationale:**
- Saves about 300 KB and one third-party origin, and removes a privacy leak.
- Rejected: keeping Google with `preconnect`, which is what happens today.

**User story:** As a member, I want icons to appear correctly on first paint.

**Acceptance criteria:**
- [ ] No requests to `fonts.googleapis.com`/`fonts.gstatic.com`
- [ ] Total font bytes on `/login` ≤ 80 KB

**Success metric:** `thirdPartyHosts` empty in the Playwright measurement.

**Validation:** Playwright resource list.

### PERF-017: Cache merged settings and cut the ~55 ms authenticated request floor

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Cross-cutting |
| Persona(s) | All signed-in users |
| Category | Back-end performance |
| Severity | Medium |
| Impact | 3 |
| Effort | S |
| Confidence | Likely |
| Priority score | **2.4** (3×2×0.8÷2) |
| Verdict | Fix |
| Dependencies | PERF-008, PERF-015 |
| Labels | settings, latency-floor, auth |

**Evidence:**
- `projectionist/web/app.py:936-937` and `projectionist/web/auth.py:88-89`: `_settings()` → `load_merged_settings(DATA_DIR)`, which reads `settings.json`, decrypts secrets, and normalises on **every** call (`projectionist/config_store.py:856-865, 882-926`). There is no cache (no `lru_cache` or mtime check in `config_store.py`).
- 183 `_settings()` call sites in `projectionist/web` (`git grep -n "_settings()" 94fcd3f -- projectionist/web | wc -l`). Per request it runs in the middleware (`auth.py:497`) plus each dependency (`require_role` `:545`, `get_current_user` `:517`).
- Measured: health 15 ms, anonymous `/api/features` 30–36 ms, owner `/api/features` 71–75 ms, `/api/auth/me` 73–84 ms, Live guide (Off) 73–80 ms.
- Locally at `94fcd3f` *without* a settings file, `load_merged_settings` costs 0.08 ms/call. The remaining cost is therefore file read, decrypt, and session lookup. Not profiled on QA, hence *Likely*.

**Current state:** Every authenticated API call pays about 55 ms of fixed overhead, and the chat boot pays it 24 times.

**Root cause:** Settings are treated as always-fresh to avoid stale-config bugs, at the cost of per-call I/O.

**Recommendation:**
1. Profile one owner `/api/features` on QA with `py-spy record --pid` (host) to confirm the split.
2. Cache `load_merged_settings` keyed on `(settings.json st_mtime_ns, st_size, env fingerprint)`, invalidated on `save_settings`. Return a frozen copy.
3. Cache the session → user lookup for 5 s, keyed by the session token hash, and invalidate it on logout and role change.

**Rationale:**
- Halves latency on every signed-in call.
- Rejected: caching settings for a fixed TTL, which makes config saves appear not to work.

**User story:** As a member, I want every tap to feel instant.

**Acceptance criteria:**
- [ ] Owner `/api/features` p50 ≤ 35 ms on QA
- [ ] Saving settings is reflected on the next request (test)

**Success metric:** authenticated p50 floor within 2× of health.

**Validation:** Scope & method step 7 table re-run.

### PERF-018: Stream the admin backup snapshot instead of building it in RAM

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Owner |
| Persona(s) | Owner |
| Category | Reliability / memory |
| Severity | Medium |
| Impact | 3 |
| Effort | S |
| Confidence | Likely |
| Priority score | **2.4** |
| Verdict | Fix |
| Dependencies | PERF-009 |
| Labels | backup, memory, streaming |

**Evidence:**
- `projectionist/web/backup.py:35` `buf = io.BytesIO()`; `:42-59` writes the sqlite backup copy to a temp file, then `zf.write` into the in-memory zip; `:76` `return buf.getvalue()` (a second copy).
- `projectionist/web/app.py:2859-2867` returns `Response(content=body)` from a sync handler.
- Prod DB is 227,655,680 B.

**Current state:** One click allocates roughly the compressed DB size twice in RAM. It writes a full temp copy into `DATA_DIR` and holds a threadpool worker for the whole backup and compression. *Likely* several hundred MB peak on prod; not measured, to avoid load on prod.

**Root cause:** Written for small DBs.

**Recommendation:**
1. Write the zip to `DATA_DIR/backups/admin-<stamp>.zip` on disk (or reuse the nightly backup from PERF-009) and return `FileResponse` with background cleanup.
2. Use `ZIP_DEFLATED` with `compresslevel=1`, or `ZIP_STORED` with gzip of the DB.
3. Rate-limit to one concurrent snapshot.

**Rationale:** Avoids OOM pressure and loop stalls on larger households. Rejected: chunked streaming zip, which is more complex for little gain once the nightly file exists.

**User story:** As an owner, I want to download a backup without slowing the app for everyone.

**Acceptance criteria:**
- [ ] Peak RSS increase during a snapshot ≤ 50 MB on QA
- [ ] A second concurrent request gets 429

**Success metric:** no RSS spikes > 100 MB in metrics during a snapshot.

**Validation:** `docker stats` while downloading on QA.

### PERF-019: Cache Plex on-deck for Continue Watching

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Consumer |
| Persona(s) | Members on Explore |
| Category | Back-end performance / dependency |
| Severity | Medium |
| Impact | 3 |
| Effort | S |
| Confidence | Likely |
| Priority score | **2.4** |
| Verdict | Fix |
| Dependencies | PERF-008, PERF-010 |
| Labels | plex, caching, explore |

**Evidence:**
- `projectionist/web/library_routes.py:981-997` constructs `PlexClient(...)` per request and calls `feed_continue_watching(_db(), limit=limit, plex_client=plex_client)`.
- Measured: 754–1,045 ms by curl, and **1,613 ms** in-browser on Explore load. It is the slowest Explore call; the hub takes 287 ms.
- The failing CI spec is `e2e/explore.spec.ts:10` (PERF-010).

**Current state:** Explore's first rail waits on a live Plex round trip every visit. If Plex is slow, the rail is slow; if Plex is down, the breaker opens after 3 failures (PERF-002).

**Root cause:** No SWR cache on this feed, unlike the hub (`projectionist/library/explore_hub.py:52`, which keeps entries for SWR).

**Recommendation:** Wrap `feed_continue_watching` in the existing `projectionist/swr_cache.py` with key `(user_id, limit)`, TTL 60 s, and stale-while-revalidate 10 min. Invalidate on playback stop or scrobble webhooks.

**Rationale:** On-deck changes only when someone watches. Rejected: dropping the rail, which is a valued member feature.

**User story:** As a member, I want "Continue watching" to appear with the rest of Explore.

**Acceptance criteria:**
- [ ] Warm p95 ≤ 100 ms
- [ ] After finishing an episode, the rail updates within 60 s

**Success metric:** Explore SLO server p95 < 400 ms for all rails.

**Validation:** curl timings and the Explore e2e spec.

### PERF-020: Tighten the perf budget: bytes, throttled cold runs, real content marks

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Cross-cutting |
| Persona(s) | Maintainer |
| Category | Performance governance |
| Severity | Medium |
| Impact | 2 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | **2.0** |
| Verdict | Fix |
| Dependencies | PERF-003, PERF-007, PERF-011 |
| Labels | perf-budget, cls, playwright |

**Evidence:**
- `e2e/release-perf.spec.ts:44-50`: About "content" is `heading "The story"` with JSON needle `/release-notes.json`, which measures the heading, not the 7,000-node list.
- `frontend/perf/baseline.json` `tolerance`: "content/LCP budget = max(1500ms, …)". Explore median CLS 0.1604, with the note "CLS 0.1604 is over 0.1; kept as the baseline".
- Measured live on Explore: CLS 0.096.
- The harness has no transfer-size or compression assertion and no throttled profile.

**Current state:** The harness passed at `94fcd3f` while cold `/login` on slow 4G took 12.6 s.

**Root cause:** It runs only on localhost with a mocked server, and the budget was framed around time alone.

**Recommendation:**
1. Add a `bytes` budget per page: `/login` JS+CSS ≤ 250 KB compressed (after PERF-011), fail at +10%.
2. Add one cold run with `Network.emulateNetworkConditions` (150 ms, 1.6 Mbps) and `setCPUThrottlingRate: 4`, with a budget of `FCP ≤ 4,000 ms` on `/login`.
3. Change About's content mark to `[data-testid='about-release-notes'] li` visible.
4. Set the CLS budget to 0.1 hard and fix Explore (reserve rail heights).

**Rationale:** Measures what users feel. Rejected: Lighthouse CI, which is heavier and needs Chrome flags in CI. Playwright is already there.

**User story:** As the maintainer, I want the budget to fail when the bundle doubles.

**Acceptance criteria:**
- [ ] Budget fails on a PR that adds 100 KB gzip to `/login`
- [ ] Explore CLS ≤ 0.1 in the baseline

**Success metric:** zero byte-budget regressions merged.

**Validation:** deliberately add a large import in a test PR.

### PERF-021: Pin Python dependencies and clear the react-router advisory

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Cross-cutting |
| Persona(s) | Maintainer |
| Category | Supply chain / reproducibility |
| Severity | Medium |
| Impact | 2 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | **2.0** |
| Verdict | Fix |
| Dependencies | — |
| Labels | dependencies, lockfile, audit |

**Evidence:**
- No Python lockfile at `94fcd3f`. Lockfiles listed: only `package-lock.json` and `frontend/package-lock.json`.
- `ci.yml:30` `pip install ".[web,dev,mcp]"`, and `Dockerfile:62-63` `pip install ".[web,mcp]"`, both on ranges.
- `npm audit --omit=dev` (frontend): 2 moderate (`react-router`/`react-router-dom` ≤ 7.17.0: GHSA-wrjc-x8rr-h8h6, GHSA-337j-9hxr-rhxg).
- Dev only: `vite` ≤ 6.4.3 (high) and `esbuild` ≤ 0.24.2 (moderate).
- Root lockfile: 0.

**Current state:** Two images built a day apart can contain different Python wheels. A transitive break (e.g. `httpx`, `starlette`) appears in prod without a code change and cannot be bisected.

**Root cause:** No lock step in the release scripts.

**Recommendation:**
1. Add `uv pip compile pyproject.toml --extra web --extra mcp -o requirements.lock` (and `--extra dev` → `requirements-dev.lock`). Install with `--require-hashes` in the Dockerfile and CI.
2. Run `pip-audit -r requirements.lock` in CI.
3. Upgrade `react-router-dom` to the patched 6.x line if one exists; otherwise plan the v7 move. The SSR advisory does not apply, but the open-redirect one may.
4. Bump `vite` to ≥ 6.4.4 for dev hygiene.

**Rationale:** Reproducible builds make perf and reliability regressions bisectable.

**User story:** As the maintainer, I want the image I tested to be the image I ship.

**Acceptance criteria:**
- [ ] `requirements.lock` exists and Docker uses it
- [ ] `pip-audit` runs in CI

**Success metric:** zero unexplained dependency drifts between tags.

**Validation:** diff `pip freeze` across two builds.

### PERF-022: Add an LLM spend cap, a shared HTTP client, and provider timeouts/fallback

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Owner |
| Persona(s) | Owner (pays), members (chat) |
| Category | Cost / reliability |
| Severity | Medium |
| Impact | 3 |
| Effort | M |
| Confidence | Likely |
| Priority score | **1.6** (3×2×0.8÷3) |
| Verdict | Fix |
| Dependencies | PERF-005, PERF-025 |
| Labels | llm, cost, timeouts, budget |

**Evidence:**
- `projectionist/agent/providers/__init__.py:243,274,315,390,420`: `async with httpx.AsyncClient(timeout=120.0) as client:`, a new client (new TCP/TLS) per call with a flat 120 s timeout.
- `:373` `"max_tokens": 4096`.
- No budget or cap symbols (`git grep -i "budget\|daily_cap\|spend_limit"` in telemetry and providers returned nothing).
- The tool-loop cap exists (`projectionist/agent/curator.py:283`).
- Chat first-token is **not measurable** on QA (LLM unset).

**Current state:** A runaway loop, a misconfigured expensive model, or an owner enabling a large enrichment batch has no hard stop. A hung provider holds a chat for 120 s before failing, and no fallback provider is used.

**Root cause:** Cost was handled through visibility (accounting) rather than control.

**Recommendation:**
1. Add a setting `llm.daily_budget_usd` (default 2.00 when the model has a known price; 0 = unlimited) and `llm.daily_token_cap` for unknown models. Enforce it before each call using `llm_usage` sums. When exceeded, background tasks stop, chat returns a friendly "daily budget reached", and the owner is notified.
2. Use one module-level `httpx.AsyncClient` per provider with `httpx.Timeout(connect=5, read=60, write=10, pool=5)` and `limits=httpx.Limits(max_connections=10)`.
3. Retry once on connect errors and 429 with `Retry-After`, using the same policy as PERF-002, and wire providers into `host_circuits`.
4. Emit time-to-first-token into metrics (PERF-025).

**Rationale:** Caps turn an unbounded financial risk into a bounded one. Rejected: relying on provider-side spend limits, which are not available for all providers or for local gateways.

**User story:** As an owner, I want a monthly LLM bill I can predict.

**Acceptance criteria:**
- [ ] With the budget set to $0.01 on QA, background enrichment halts and an owner notification appears
- [ ] Provider connect failure surfaces in ≤ 5 s, not 120 s

**Success metric:** zero days over budget; chat p90 TTFT tracked.

**Validation:** QA with a stub provider (`LLM_BASE_URL` pointing at a slow mock).

### PERF-023: Enforce the async boundary and isolate background work from request serving

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Cross-cutting |
| Persona(s) | All |
| Category | Architecture / reliability |
| Severity | Medium |
| Impact | 3 |
| Effort | L |
| Confidence | Likely |
| Priority score | **0.96** (3×2×0.8÷5) |
| Verdict | Rethink |
| Dependencies | PERF-008, PERF-012 |
| Labels | single-process, scheduler, isolation |

**Evidence:**
- `projectionist/web/__main__.py:124-152`: theater and main share one process and loop.
- `projectionist/scheduler/engine.py:108` runs tasks on worker threads with private loops in the same process.
- `projectionist/scheduler/tasks/data_retention.py:34,111-115` VACUUMs in-process (PERF-024).
- 33 scheduler task modules.
- Both containers run without memory or CPU limits.

**Current state:** One process is the failure domain for request serving, theater, the scheduler, Plex sync, and enrichment. A GIL-heavy task (embedding, taxonomy) or a memory leak in background work degrades every user, and a crash takes everything down.

**Root cause:** Simplicity-first packaging, which was correct early on.

**Recommendation:**
1. Do PERF-008 first, then measure with PERF-025 metrics for 4 weeks.
2. If loop p99 or Explore p95 still burns budget during scheduled tasks, add `python -m projectionist.worker` as a second process in the same container (supervised by the entrypoint). It owns the scheduler and enrichment, shares SQLite, and keeps its own write serializer; SQLite handles cross-process locking with busy timeout.
3. Set container `--memory=1.5g` to bound runaway growth.

**Rationale:** Keeps one container and one image, and buys fault isolation. Rejected: a multi-container split or a queue broker, which is too heavy.

**User story:** As a member, I want nightly maintenance not to slow my evening.

**Acceptance criteria:**
- [ ] Decision record after 4 weeks of metrics
- [ ] If split: killing the worker does not affect `/api/health/ready` request serving

**Success metric:** request p95 unchanged during scheduler runs.

**Validation:** metrics overlay of task runs vs latency.

### PERF-024: Move VACUUM out of the serving process or make it incremental

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Cross-cutting |
| Persona(s) | Members active at maintenance time |
| Category | Back-end / database |
| Severity | Low |
| Impact | 2 |
| Effort | S |
| Confidence | Suspected |
| Priority score | **0.5** (2×1×0.5÷2) |
| Verdict | Fix |
| Dependencies | PERF-023 |
| Labels | sqlite, vacuum, maintenance |

**Evidence:**
- `projectionist/library/db/_telemetry.py:786-795` runs a raw `VACUUM` connection.
- `projectionist/scheduler/tasks/data_retention.py:34` `VACUUM_THRESHOLD = 1000`, and `:111-115` VACUUMs after pruning at least 1,000 rows.
- Prod DB is 218 MB. A full VACUUM rewrites the file and blocks writers. Writers wait up to `SQLITE_BUSY_TIMEOUT_MS = 30_000`.

**Current state:** On large prune days, writes (ratings, playback progress) can stall for seconds. This was not observed, hence *Suspected*. Validate by timing `VACUUM` on a copy of the prod DB on QA.

**Root cause:** Space reclamation treated as routine maintenance.

**Recommendation:** Switch to `PRAGMA auto_vacuum=INCREMENTAL` (one-time VACUUM during a maintenance window) and run `PRAGMA incremental_vacuum(2000)` nightly. Alternatively, VACUUM only when the freelist exceeds 20% of pages, and only between 04:00 and 05:00.

**Rationale:** Avoids long exclusive locks.

**User story:** As a member, I want my rating to save instantly at any hour.

**Acceptance criteria:**
- [ ] No single maintenance lock > 1 s (log timing)

**Success metric:** write-queue max wait < 1 s daily.

**Validation:** time VACUUM on a QA copy; check write-queue stats.

---

## 15. Opportunities

### PERF-025: Publish SLOs with live indicators and burn alerts

| Field | Value |
|---|---|
| Type | Opportunity |
| Surface | Cross-cutting |
| Persona(s) | Owner-operator, maintainer |
| Category | Observability / SRE |
| Severity | Medium |
| Impact | 4 |
| Effort | M |
| Confidence | Confirmed |
| Priority score | **2.67** (4×2×1.0÷3) |
| Verdict | Add |
| Dependencies | PERF-012, PERF-008, PERF-009 |
| Labels | slo, metrics, alerting |

**Evidence:** No SLO or metrics exist (PERF-012). The SLO table in Part A §10 lists the indicators and today's measured values.

**Current state:** "Fast" and "up" are undefined, so no trade-off can be made with data.

**Root cause:** No metrics substrate.

**Recommendation:**
1. Implement the middleware histogram (route groups: `chat_stream`, `explore_hub`, `library_query`, `feeds_other`, `auth`, `admin`, `static`).
2. Add a first-SSE-frame timer in `chat_routes.chat_stream`.
3. Add the backup gauge.
4. Adopt the seven SLOs in §10. Review monthly in the release notes ("SLO report").

**Rationale:** Gives the team a shared definition of good, which is cheap at this scale.

**User story:** As the maintainer, I want to know whether a release made things slower for real users.

**Acceptance criteria:**
- [ ] All seven SLIs visible at `/api/metrics`
- [ ] Two alert rules wired to Apprise

**Success metric:** monthly SLO report published 3 months in a row.

**Validation:** QA game-day triggers each alert.

### PERF-026: Add a privacy-safe Web Vitals beacon to existing telemetry

| Field | Value |
|---|---|
| Type | Opportunity |
| Surface | Consumer, Public |
| Persona(s) | Mobile/remote members |
| Category | Observability / front-end |
| Severity | Medium |
| Impact | 3 |
| Effort | S |
| Confidence | Likely |
| Priority score | **2.4** |
| Verdict | Add |
| Dependencies | PERF-025 |
| Labels | rum, web-vitals, telemetry |

**Evidence:** Lab measurements only. The project already has `projectionist/telemetry/ingestion.py` (`telemetry_events` upsert). The VIP/CDN path cannot be measured from the LAN.

**Current state:** We don't know what remote members actually experience, including whether the public proxy compresses.

**Root cause:** No client-side performance telemetry.

**Recommendation:** On `pagehide`, send `{route_group, lcp, inp, cls, ttfb, effectiveType}` (no user id, no URL params) via `navigator.sendBeacon('/api/telemetry/vitals')`. Store p75 by route group per day and show it on Admin → Health.

**Rationale:** Real-user data replaces guesses. Rejected: third-party RUM, which is a privacy and CSP cost.

**User story:** As the maintainer, I want to see p75 LCP for members off the LAN.

**Acceptance criteria:**
- [ ] Beacon payload contains no identifiers
- [ ] Admin Health shows p75 LCP/INP/CLS per route group

**Success metric:** p75 LCP ≤ 2.5 s on Explore and Chat.

**Validation:** beacon unit test plus QA dashboard.

### PERF-027: Prune retained images and keep a rollback window of three

| Field | Value |
|---|---|
| Type | Opportunity |
| Surface | Admin |
| Persona(s) | Owner-operator |
| Category | Cost / host hygiene |
| Severity | Low |
| Impact | 1 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | **1.0** |
| Verdict | Add |
| Dependencies | PERF-004, PERF-013 |
| Labels | docker, disk, cost |

**Evidence:** `docker image ls` shows 11 `romwil/projectionist` tags at about 750 MB each, plus `projectionist-qa:wip`. `docker system df` shows Images 37.28 GB, 17.76 GB reclaimable (47%).

**Current state:** Disk is spent on stale tags. Shared layers make the real per-tag cost smaller than 750 MB.

**Root cause:** `rollout.sh` never prunes.

**Recommendation:** At the end of `scripts/unraid-rollout.sh`, keep the current tag plus two previous `romwil/projectionist` tags and remove the rest. Do not prune other images on the host.

**Rationale:** Keeps a rollback window while bounding disk use.

**User story:** As an owner, I want upgrades not to slowly fill my cache drive.

**Acceptance criteria:**
- [ ] After rollout, ≤ 3 `romwil/projectionist` tags present

**Success metric:** reclaimable images from this repo ≈ 0.

**Validation:** `docker image ls` after the next rollout.

### PERF-028: Run a small concurrency smoke on QA per release

| Field | Value |
|---|---|
| Type | Opportunity |
| Surface | Cross-cutting |
| Persona(s) | Maintainer; households > 3 users |
| Category | Performance testing |
| Severity | Medium |
| Impact | 3 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | **3.0** |
| Verdict | Add |
| Dependencies | PERF-008 |
| Labels | load-test, qa, concurrency |

**Evidence:** The 5-parallel probe in Scope & method step 7 found PERF-008 in seconds. No such check exists in CI or `docs/RELEASE.md`.

**Current state:** Concurrency bugs are invisible to single-user e2e.

**Root cause:** Tests model one user.

**Recommendation:** Add `scripts/qa/concurrency-smoke.sh` (curl only, ≤ 30 requests total, QA `:8792` only, never prod). It signs in as qa-member, fires 5 parallel `/api/library/query?media_type=movie` plus `/api/library/feeds/hub`, and probes `/api/health` during the run. Fail if health > 250 ms or any query > 1.5 s. Add it to the Path B CA-proof checklist.

**Rationale:** About 5 minutes per release to catch the class of bug most likely to hurt households.

**User story:** As the maintainer, I want to know a release still holds up with a busy household.

**Acceptance criteria:**
- [ ] Script exits non-zero on the current `94fcd3f` behaviour
- [ ] Script exits zero after PERF-008

**Success metric:** zero loop-blocking regressions shipped.

**Validation:** run on QA before and after the fix.

---

## 16. Remediation plan

### Now (0–2 weeks)

| ID | Title | Effort | Owner role | Dependencies |
|---|---|---|---|---|
| PERF-007 | Compress responses; immutable asset caching | XS | Backend | — |
| PERF-008 | Unblock the event loop in `async` handlers + guard | S | Backend | — |
| PERF-009 | Nightly verified backups + restore drill | S | Backend + operator | — |
| PERF-010 | Green main; CI as release gate | S | Maintainer | — |
| PERF-013 | Pre-migration snapshot + schema-too-new guard | S | Backend + operator | PERF-009 |
| PERF-014 | Paginate About release notes | S | Frontend | — |
| PERF-028 | QA concurrency smoke | S | QA | PERF-008 |

### Next (2–6 weeks)

| ID | Title | Effort | Owner role | Dependencies |
|---|---|---|---|---|
| PERF-011 | Route/role code splitting | M | Frontend | PERF-007 |
| PERF-012 | Readiness, metrics, external probe, alerts | M | Backend + operator | PERF-009 |
| PERF-025 | SLOs with indicators | M | SRE/maintainer | PERF-012 |
| PERF-015 | Trim chat boot fan-out | S | Frontend + backend | PERF-017 |
| PERF-017 | Settings + session cache | S | Backend | — |
| PERF-019 | Cache Plex on-deck | S | Backend | — |
| PERF-016 | Self-host fonts; SVG icons | S | Frontend/design | — |
| PERF-020 | Byte + throttled perf budget | S | Frontend/QA | PERF-007, PERF-011 |
| PERF-018 | Stream admin snapshot | S | Backend | PERF-009 |
| PERF-021 | Python lockfile + audit | S | Maintainer | — |
| PERF-022 | LLM budget, shared client, timeouts | M | Backend | PERF-025 |

### Later (6+ weeks)

| ID | Title | Effort | Owner role | Dependencies |
|---|---|---|---|---|
| PERF-023 | Worker-process split (if SLOs burn) | L | Backend/architect | PERF-008, PERF-025 |
| PERF-024 | Incremental vacuum | S | Backend | PERF-023 |
| PERF-026 | Web Vitals beacon | S | Frontend | PERF-025 |
| PERF-027 | Prune retained images | XS | Operator | PERF-013 |

**Sequencing rationale:**
- Fix what multiplies everything else first. Compression (XS) and loop unblocking (S) improve every user and every page immediately.
- Backups and migration guards come next because they bound the worst-case loss before more releases ship.
- Green CI restores the gate that protects all later work.
- Splitting and metrics are M-sized and benefit from the gate being trustworthy.
- The worker split is deliberately deferred until metrics prove it is needed.

## 17. Quick wins (high impact, XS–S)

| ID | Win | Expected effect |
|---|---|---|
| PERF-007 | `GZipMiddleware` + immutable `/assets` | Cold bytes 2.53 MB → about 0.7 MB; slow-4G `/login` FCP about 12.6 s → about 4 s (estimate) |
| PERF-008 | `run_in_threadpool(query_library, …)` | Health under concurrency 646–2,155 ms → < 100 ms target |
| PERF-009 | Nightly `sqlite3 .backup` + `integrity_check` | RPO 7 days → 1 day |
| PERF-014 | About: 10 newest + on-demand archives | DOM 7,048 → < 1,000; JSON 613 KB → < 40 KB |
| PERF-015 | Drop watchlist sync from boot; dedupe features/me | 24 → about 15 calls immediately |
| PERF-027 | Keep 3 image tags | Reclaim most of 17.8 GB |

## 18. Open questions needing product/business input

1. **Is the public hostname (and therefore remote and mobile use) a supported primary path?** If yes, PERF-007 and PERF-011 are High as written. If LAN-only, they drop to Medium. Also: does the public proxy compress today? It was not measurable under this run's rules.
2. **What RPO and RTO does the household accept?** The proposal is 24 h / 30 min. If "no lost ratings ever" matters, consider Litestream (RPO about 1 s) at the cost of a sidecar.
3. **Should About keep full release history in-app at all,** or link to GitHub Releases after the newest 10?
4. **What daily or monthly LLM budget is acceptable by default** for a fresh install with a cloud provider?
5. **May the maintainer enable branch protection that blocks the owner's own merges on red?** Or is an explicit override flag preferred?
6. **Is an external monitor container (Uptime Kuma or Gatus) acceptable on the Automat host,** or should alerting stay inside the app via Apprise only?

---

## Changelog

- 2026-10-30 (Chief Skeptic, Phase 4 red team): Unit fix. The JS bundle is 2,178,954 B, which is 2,128 KiB (as the Scope table already says), or **2.08 MiB** (2.18 MB decimal). Four places said "2.13 MiB", which mixed binary and decimal units. Changed them to 2.08 MiB, including the PERF-011 title. No measurement, severity, or grade changed. `_status.md` still says "2.13 MiB". This review does not edit `_status.md`, so that line is flagged for Synthesis.
