# Live Channels — Deferred & discoveries (living)

**Date seeded:** 2026-07-29  
**Status:** Living log — append freely; do not treat as a shipping checklist  
**Related:** [implementation plan](./2026-07-29-live-channels-tunarr.md) · [product spec](../specs/2026-07-29-live-channels-tunarr.md)

Durable parking lot for product deferrals, engineering gaps, and mid-build discoveries so parallel agents do not lose intelligence. Reconciled **2026-07-29** with [implementation plan Status](./2026-07-29-live-channels-tunarr.md): Phases 1–3 core done (Admin Live Channels enable flow, publish APIs, `CERTIFIED_SERVICES` `tunarr`, household on-now). Remaining: Automat Phase 0 pin/OpenAPI, richer Tunarr program IDs, `schedule-slots`, HELP/CHANGELOG Task 7 (`CONFIGURATION.md` done), e2e `FeatureFlags` + on-now, nudge once-ever, guide shape validation.

---

## How to append

When you discover a gap mid-build (API missing, Tunarr OpenAPI surprise, UX dead-end, host ops finding):

1. Add a dated bullet under the right section below (or **## New discoveries**).
2. Use the item format: **Status**, **Why / note**, **Suggested next phase**, **Owner surface**.
3. Flip status to `done` (leave the bullet; do not delete history) when the gap closes.
4. One-line pointer stays in the implementation plan — keep detail **here**, not scattered in chat.

Statuses: `deferred` | `in_progress` | `blocked` | `done`

---

## Explicitly later (product)

### Full newspaper EPG / remote in Projectionist

- **Status:** `deferred`
- **Why / note:** Spec locks watch surface to Plex Live TV; Projectionist only reads a guide snapshot for “on now,” never a full EPG product.
- **Suggested next phase:** Post–Phase 3 delight (if ever); not v1.
- **Owner surface:** household / product

### Daypart programming beyond shuffle / sequential

- **Status:** `deferred`
- **Why / note:** `ProgrammingMode` today is `sequential` | `shuffle` | `chaos` only (`recipes.py`). Multi-lineup dayparts are explicitly later in the spec.
- **Suggested next phase:** After publish path is solid; needs Tunarr schedule-slots client + recipe model.
- **Owner surface:** backend / recipes

### Docker-less cloud AIO as first-class

- **Status:** `deferred`
- **Why / note:** Without Docker socket, path is BYO Tunarr URL only. Cloud AIO without a sibling container is out of v1 scope.
- **Suggested next phase:** Post-v1 packaging decision.
- **Owner surface:** ops / product

### Replacing Plex Live TV chrome

- **Status:** `deferred`
- **Why / note:** Product intent: Plex remains the watch surface; Projectionist is management + delight only.
- **Suggested next phase:** Never for v1; revisit only if product intent changes.
- **Owner surface:** product

### Coax clone / in-app watch

- **Status:** `deferred`
- **Why / note:** Spec out of scope — Coax is config vocabulary reference only; no Projectionist player.
- **Suggested next phase:** Never for v1.
- **Owner surface:** product

---

## Known engineering gaps (post–Phase 1)

### Guided enable wizard (preflight → pull → wire → Plex attach)

- **Status:** `done` (core path; residual polish OK)
- **Why / note:** Owner Admin Live Channels guided checklist landed 2026-07-29: enable → preflight → lifecycle → publish starters → Plex attach (`POST …/preflight`, `…/lifecycle`, starters propose/publish, `GET …/plex-attach`, status health strip). Plex Pass still owner-confirm (intentional). **Not** first-run `WIZARD_STEPS` setup integration.
- **Suggested next phase:** Residual gaps in **New discoveries** (program IDs, docs, e2e flag type, Automat pilot).
- **Owner surface:** wizard / frontend Config + backend routes

### Publish recipes → Tunarr programming (full path)

- **Status:** `done` (channel create + publish APIs) / `deferred` (full lineup IDs)
- **Why / note:** Orchestrator exists (`live_channels/publish.py`): `POST …/starters/publish`, `POST …/channels/from-collection`, `last_publish_at` / `last_error` persistence, Plex media-source wire best-effort. **Nuance:** `programming_body_for_recipe` still emits empty/minimal `manual` lineup shells (flex hints only) until Tunarr scanned program IDs are available — channels exist; rich programming is not filled yet. `schedule-slots` client method still absent.
- **Suggested next phase:** Richer programming after media-source scan / Automat OpenAPI confirmation.
- **Owner surface:** backend

### Full Docker / Unraid orchestration (exposed pull/start/stop)

- **Status:** `done` (owner API + Engine path) / `deferred` (Automat hardening)
- **Why / note:** `TunarrDockerLifecycle` + `POST /api/admin/live-channels/lifecycle` (`pull` / `start` / `stop` / `ensure_running`) gated by orchestration settings/env; disable keeps volume. Unraid CA template exposes optional **Docker Socket** path (empty Default / `Required="false"` — off by default); owners enable host `/var/run/docker.sock` for managed Tunarr. Unraid CA / compose keep the socket opt-in (empty Default). Automat prod rollout may mount `/var/run/docker.sock` when the owner asks (`MOUNT_DOCKER_SOCK=1` in appdata `.env` / `rollout.sh`). Remaining Unraid volume/network hardening and measured resource numbers still wait on Phase 0.
- **Suggested next phase:** Phase 0 ops pilot before declaring managed Docker “certified” on host.
- **Owner surface:** backend / ops

### Household on-now Dashboard / inbox nudges

- **Status:** `done` (core path; see 2026-07-29 discoveries for residual gaps)
- **Why / note:** Household delight landed 2026-07-29: `GET /api/live-channels/on-now` + `OnNowPanel` on Dashboard/Explore; ready nudge once-ever per user via `related_id=live-channels-ready`. Residual: no e2e for on-now; nudge does not reset on disable/re-enable; Tunarr guide field shapes still best-effort pending Automat pilot. **Do not regress this status** when updating wizard/publish docs.
- **Suggested next phase:** Residual gaps in **New discoveries** (e2e / nudge reset / guide validation); HELP/CHANGELOG with shipping PR.
- **Owner surface:** household / frontend Dashboard + notifications

### OTA / existing Live TV coexistence (multi-tuner)

- **Status:** `done` (attach copy + soft detect) / residual (number collisions)
- **Why / note:** Plex supports multiple tuners. Attach checklist matches real Plex UI: Tuner Setup = discovery + ZIP gate; EPG Location never offers XMLTV (first screen or channel-mapping) — finish wizard with a temporary ZIP-code lineup. Tunarr streams work; guide titles stay wrong until XMLTV is attached via a working path. Automat-verified: Device Settings / DVR Settings / EPG dropdown have no XMLTV paste for HDHomeRun-style devices on this Plex build — do not claim DVR Settings → XMLTV. Soft probe via `/livetv/dvrs` and `/livetv/tuners` surfaces “Existing Live TV setup detected…” when PMS answers; failures stay `unknown`. Residual: channel-number collisions with OTA majors if owners override the 100+ floor. **API attach landed in 1.29.10** (`POST …/plex-attach-guide`).
- **Suggested next phase:** Automat pilot with real OTA + Tunarr; optional smarter channel pick.
- **Owner surface:** Admin → Live Channels → Plex attach

### Reliable Plex Pass / Live TV entitlement detection

- **Status:** `done` (owner confirm in preflight) / `deferred` (auto-detect)
- **Why / note:** Preflight accepts `plex_pass_confirmed` and persists on Tunarr settings; auto-detection still returns `unknown` without a stable Plex signal.
- **Suggested next phase:** Detection if Plex exposes a reliable signal later.
- **Owner surface:** backend / wizard

### Tunarr always-transcodes + ~1GB image / GPU needs

- **Status:** `deferred` (constraint / discovery)
- **Why / note:** Spec + preflight soft-warn: ~1GB amd64 image, always-transcode, soft-transcode OK for one stream; GPU optional soft check only (`preflight.py` gpu check always `ok: true` with messaging). Ops pilot (Automat) still unchecked for measured RAM/CPU.
- **Suggested next phase:** Phase 0 ops pilot numbers → keep preflight copy honest; no hard block for v1.
- **Owner surface:** ops / wizard

### Tunarr no admin auth → keep admin off LAN

- **Status:** `deferred` (constraint)
- **Why / note:** Documented on `TunarrClient`: no Tunarr admin auth — Projectionist must call on the trusted host network; admin UI not published to LAN. Must stay a hard product/ops rule, not a Tunarr UI escape hatch.
- **Suggested next phase:** Enforce in Docker port publishing / docs (Task 7).
- **Owner surface:** ops / backend

### OpenAPI stability / pin `1.3.x` + contract tests

- **Status:** `deferred`
- **Why / note:** Default image tag pinned to `chrisbenincasa/tunarr:1.3.9` (verified on Docker Hub; Automat settings match). Client unit tests exist; **no** OpenAPI contract/snapshot tests. Digest pin + OpenAPI gap list still tied to Automat Phase 0 (still unchecked).
- **Suggested next phase:** Phase 0 pilot → pin exact tag → add contract tests against recorded fixtures.
- **Owner surface:** backend / ops

### Zero-click Plex DVR attach not possible

- **Status:** `done` (wizard helpers) / `deferred` (zero-click — impossible)
- **Why / note:** `GET /api/admin/live-channels/plex-attach` + Config checklist with copy URLs + discovery probe. Zero-click attach remains unavailable via public Plex APIs — product constraint, not a missing wizard step.
- **Suggested next phase:** None for zero-click; keep copy honest in HELP.
- **Owner surface:** wizard

### Automat Unraid ops pilot

- **Status:** `deferred` / `blocked` (host access)
- **Why / note:** Plan Task 0 unchecked: pin Tunarr on Automat, 2 channels → Plex, measure image/RAM/CPU, confirm OpenAPI coverage and HDHR/XMLTV acceptance. Deferred until maintainer runs pilot; host runbooks stay off the product tree.
- **Suggested next phase:** Phase 0 before declaring managed Docker “done.”
- **Owner surface:** ops

### Tunarr certified-service + setup test

- **Status:** `done`
- **Why / note:** `"tunarr"` is in `CERTIFIED_SERVICES`; `test_tunarr` reachability check exists in `setup.py` (version + channel count best-effort).
- **Suggested next phase:** None for v1 core; refresh messages if OpenAPI shapes change post-pilot.
- **Owner surface:** backend / wizard

### Collection → channel API + Admin Live Channels surface

- **Status:** `done` (core path)
- **Why / note:** `POST /api/admin/live-channels/channels/from-collection` + starter pack propose/publish; Admin/Config Live Channels surface with status, preflight, lifecycle, publish, plex-attach. **2026-07-29 craft build:** custom craft form + `POST …/channels/publish`, collection one-tap, manage list with refill/delete, `GET …/craft-options`. Owner “re-run starter pack” additive polish still in Strong candidates.
- **Suggested next phase:** Strong-candidate polish if capacity; otherwise ship docs.
- **Owner surface:** backend / wizard

### Custom craft (name / number / motif / rules) lagged behind starters

- **Status:** `done` (2026-07-29)
- **Why / note:** Starters existed but owner could not craft a custom station or manage/delete from Admin — felt “no way to craft/publish.” Landed: craft vocabulary form, collection publish UI, Your stations refill/delete, HELP owner steps.
- **Suggested next phase:** schedule-slots + richer motif→ID matching (still deferred separately).
- **Owner surface:** Admin → Live Channels

### Strong candidates (same release if capacity)

From the spec — park here so they are not forgotten if capacity allows after core delight:

| Item | Status | Owner surface |
|------|--------|---------------|
| Auto-refresh programming after library sync / arrivals | `deferred` | backend |
| Gap fillers from trailers/extras | `deferred` | backend |
| Channel number ranges (virtual 100+) vs OTA | `done` (copy + 100+ floor) / residual collision risk | attach checklist documents 100+ floor + renumber; true auto-avoid of OTA majors still open |
| Owner “re-run starter pack” (additive; no wipe) | `deferred` | wizard |
| Ephemeral “tonight’s queue” shelf | `deferred` | household |

---

## New discoveries

<!-- Agents: append dated bullets below. Example:

### 2026-07-29 — Example title
- **Status:** `deferred`
- **Why / note:** …
- **Suggested next phase:** …
- **Owner surface:** …
-->

### 2026-07-30 — Cold HLS / deep playhead → Plex “session has ended” (1.29.18)

- **Status:** `done` (Automat evidence + code in **1.29.18**)
- **Why / note:** Guide titles were real (Flight 7500 / Alien³ / Bonhoeffer / Alice) but Plex play failed. From Plex container, cold Chaos `.ts` timed out at **0 bytes**; Tunarr logs showed `Stream not ready yet` / `No master playlist` while ffmpeg used huge mid-program `-ss` (Chaos **267m** into Bonhoeffer — past EOF). Plex: `Session appears to have died from under us`. **Fix:** `prepare_channels_for_playback` start-over when cold+deep or past EOF, aggressive media-playlist + MPEG-TS warm, keepalive scheduler (~3 min), hooked on publish / lifecycle / attach-guide + `POST …/prepare-playback`. After align+warm, all four channels delivered ~2.5 MB/10s from Plex container.
- **Suggested next phase:** Optional XMLTV programme-icon host rewrite (still `127.0.0.1` for posters; channel icons already LAN). Desktop Direct Stream remains Tunarr#718 secondary tip.
- **Owner surface:** Plex Live TV / publish / attach / Admin prepare-playback

### 2026-07-29 — `TunarrClient` schedule-slots gap

- **Status:** `deferred`
- **Why / note:** Module docstring maps shuffle/Chaos to `POST /channels/{id}/schedule-slots`, but no client method exists yet. Chaos/shuffle publish may be blocked until this lands (alongside program IDs).
- **Suggested next phase:** With richer programming / post–Automat OpenAPI confirmation.
- **Owner surface:** backend

### 2026-07-29 — Package docstring lag

- **Status:** `deferred` (docs hygiene)
- **Why / note:** `live_channels/__init__.py` may still describe earlier scaffolding; wizard/publish/on-now have landed. Refresh when exporting public API surface for shipping.
- **Suggested next phase:** Shipping PR / Task 7 hygiene.
- **Owner surface:** backend

### 2026-07-29 — Household delight residuals (post on-now land)

Household on-now / Dashboard / Explore / ready nudge is largely **done** (`GET /api/live-channels/on-now` + `OnNowPanel`; ready nudge once-ever via `related_id=live-channels-ready`). Admin guided wizard + publish is also **done** (core) — do not claim either incomplete when syncing. Residual gaps:

#### No e2e for on-now

- **Status:** `deferred`
- **Why / note:** Unit/API coverage may exist, but there is no Playwright e2e asserting on-now on Dashboard/Explore.
- **Suggested next phase:** With household e2e pass / shipping PR for Live Channels delight.
- **Owner surface:** household / e2e

#### Ready nudge does not reset on disable/re-enable

- **Status:** `deferred`
- **Why / note:** Dedup is once-ever per user via `related_id=live-channels-ready`; disable→re-enable does not clear the related notification, so households never see a second “ready” nudge.
- **Suggested next phase:** If product wants per enable-cycle; clear or version `related_id` on disable.
- **Owner surface:** household / notifications

#### Tunarr guide field shapes best-effort

- **Status:** `deferred` / `blocked` (live Tunarr)
- **Why / note:** On-now parsing is best-effort against assumed guide shapes; needs live Tunarr validation on Automat pilot before treating guide mapping as certified.
- **Suggested next phase:** Phase 0 Automat pilot → adjust parsers / fixtures.
- **Owner surface:** backend / ops

#### HELP / CHANGELOG for Live Channels

- **Status:** `deferred`
- **Why / note:** Owner HELP + CHANGELOG Highlights still deferred to the shipping PR. `CONFIGURATION.md` already documents flag/env/Tunarr nest (Task 7 partial).
- **Suggested next phase:** Shipping PR for the feature (finish Task 7).
- **Owner surface:** docs

### 2026-07-29 — Wizard/publish residuals (post enable-flow land)

Wizard agent completed guided Admin enable + publish APIs. Remaining gaps called out at handoff:

#### Full Tunarr programming still empty/manual until scanned program IDs

- **Status:** `done` (core path in **1.29.11**) / residual (richer taste→ID matching, TV-library wait)
- **Why / note:** Automat root cause: wired Plex media source left libraries `enabled: false` → empty lineups → Plex “session has ended” + empty guide. **1.29.11** enables Movies/TV, kicks scan, fills `content` lineup rows from scanned program IDs (keyword/name fallback), defaults `fill_programming=true`, and surfaces `guide_index` in Admin status. Residual: TV scan may still be queued at first publish; taste/motif matching is keyword-heuristic not full Tunarr schedule-slots.
- **Suggested next phase:** schedule-slots client + tighter motif/genre filters; wait-for-scan UX.
- **Owner surface:** backend / publish / Admin status

#### HELP / CONFIGURATION / CHANGELOG Task 7 not fully shipped

- **Status:** `deferred` (HELP + CHANGELOG) / `done` (CONFIGURATION)
- **Why / note:** `CONFIGURATION.md` nest/flag/env is in. Owner HELP (enable flow, Plex attach, what Live Channels will not do) and CHANGELOG `### Highlights` are still open — plan Task 7 incomplete.
- **Suggested next phase:** Same PR as shipping / release coupling (finish Task 7).
- **Owner surface:** docs

#### Exact Tunarr 1.3.x pin + OpenAPI gap list tied to Automat Phase 0

- **Status:** `deferred` / `blocked` (host access)
- **Why / note:** Default image tag is now `chrisbenincasa/tunarr:1.3.9` (Hub-verified; Automat pinned the same). Digest pin, measured RAM/CPU, HDHR/XMLTV acceptance, and durable OpenAPI gap backlog still require Automat Phase 0 pilot (Task 0) for full closure.
- **Suggested next phase:** Phase 0 Automat ops pilot → pin + contract fixtures.
- **Owner surface:** ops / backend

#### e2e `FeatureFlags` type lacks `live_channels_enabled`

- **Status:** `deferred`
- **Why / note:** `e2e/fixtures/api-mocks.ts` `FeatureFlags` still only types `multi_user_enabled` / `seerr_enabled` / `plex_collections_enabled`. Backend/frontend flag exists; mocked e2e helpers cannot type-safely default or override Live Channels without extending the type (+ defaults in `mockFeatures`).
- **Suggested next phase:** When adding Live Channels e2e (on-now or wizard) or any shipping e2e touch.
- **Owner surface:** e2e / frontend

### 2026-07-29 — Plex UI has no XMLTV paste for HDHomeRun/Tunarr (Automat)

- **Status:** `open` / `in progress` (API path sibling research)
- **Why / note:** Owner screenshots on Automat confirm Device Settings, DVR Settings, and Tuner Setup EPG Location have **no** XMLTV URL field for the Tunarr HDHomeRun-style device — only commercial ZIP lineups in the wizard. 1.29.9 owner tip (“DVR Settings → add/switch XMLTV”) was false; 1.29.10 corrects attach/HELP/Config copy. Tunarr streams work; guide titles wrong until XMLTV attaches via a working path. **Landed 1.29.10:** Admin Attach Tunarr guide in Plex via PMS API (separate XMLTV DVR; OTA cloud DVR preserved). Verified on Automat (DVR 8 cloud + DVR 12 XMLTV).
- **Suggested next phase:** Wire Admin “Attach guide” when a safe API path is verified (prefer separate Tunarr DVR / avoid clobbering OTA cloud EPG).
- **Owner surface:** Admin → Live Channels → Plex attach / HELP

### 2026-07-30 — HDHR tune empty despite real guide titles

- **Status:** `done` (Automat hotfix + code in **1.29.14**)
- **Why / note:** Guide/XMLTV showed real titles (Detective Dee / 2001 / etc.) but Plex play failed with “This live TV session has ended.” Root cause: Tunarr container had only `/config` — no `/data/media` mount matching Plex file paths. Cold `.ts` tune returned HTTP 200 with 0 bytes (`No master playlist found` → concat exit → session close) while ffmpeg tried mid-program `-ss` over `http://plex/library/parts/...`. Warm streams worked once HLS segments existed. **Fix:** mount host media at the same path Plex reports (`/mnt/user/data/media:/data/media:ro`); Projectionist `tunarr.media_binds` / `PROJECTIONIST_TUNARR_MEDIA_BINDS` + recreate-on-missing-binds. Residual: Plex **desktop** apps may still hit Tunarr#718 Direct Stream quirk — prefer web client or disable Direct Stream if needed.
- **Suggested next phase:** Optional GPU `/dev/dri` for soft-transcode; document client workaround in HELP.
- **Owner surface:** ops / docker lifecycle / Plex Live TV

### 2026-07-30 — Owner still “session has ended” after media binds (follow-up)

- **Status:** `done` (Automat hotfix + code in **1.29.15**)
- **Why / note:** Post-bind, Tunarr MPEG-TS from Plex container was healthy (~2–5 MB / 18–25s on `:18765`). Owner failures were compounded by (1) Tunarr `plexStream.streamPath` still `network` (now forced `direct` when binds exist), (2) a **dead enabled** leftover grabber at `http://10.10.1.202:7007/api/channels.m3u` (empty deviceId) causing “3 Sources” / duplicate plexomat noise — deleted via `DELETE /media/grabbers/devices/10` (OTA + Tunarr kept), (3) Tunarr 1.3.9 HDHR is on the **HTTP** port (mapped `18765`), not container `5004`/`15004` (nothing listens there), (4) Plex grabber logs still show Tunarr#718-class Direct Stream / matroska AAC extradata deaths on desktop — HELP documents web client or disable Direct Stream.
- **Suggested next phase:** Optional stop publishing unused `5004→15004` remap; GPU soft-transcode.
- **Owner surface:** ops / plex_attach prune / Tunarr plex-settings / HELP

### 2026-07-29 — Tunarr airing / consumption progress

#### Airing progress derived from guide start/stop (landed)

- **Status:** `done`
- **Why / note:** Tunarr `TvGuideProgram` (`GET /channels/{id}/now_playing`, guide lineups) exposes `start` / `stop` / `duration` (ms) and optional `isPaused` / `timeRemaining` — **no** dedicated percent field. Projectionist now derives `started_at` / `ends_at` / `seconds_elapsed` / `seconds_remaining` / `percent` on on-now program objects; Admin status adds `airing[]` + `sessions` (`GET /sessions`) + `guide_status`. Household On now card and Admin health strip surface progress; Plex remains the watch surface.
- **Suggested next phase:** Validate field shapes on Automat pilot (same as guide residuals).
- **Owner surface:** backend / household / Admin Config

#### Media-source library sync/scan progress not on public REST

- **Status:** `done` (basic poll in **1.29.11**)
- **Why / note:** Tunarr exposes `GET /media-sources/{ms}/{lib}/status` with `state` / `percentComplete`. Admin `guide_index.media_libraries` surfaces enabled count + scanning count; not a full progress bar UX yet.
- **Suggested next phase:** Optional richer progress UI while Movies/TV scan.
- **Owner surface:** backend / Admin only

#### Channel lineup-cycle “consumption” (startTime % duration)

- **Status:** `deferred`
- **Why / note:** Channel objects carry schedule anchor `startTime` + cycle `duration` (ms). That is how Tunarr places the playhead in the lineup, but it is not the same as “how far through the current program.” We expose **program** consumption; cycle-level progress was not product-useful for v1 on-now.
- **Suggested next phase:** Only if owners need “how deep into tonight’s loop” diagnostics.
- **Owner surface:** Admin / backend

#### Programming fill progress (how full is the lineup)

- **Status:** `deferred`
- **Why / note:** No first-class “lineup fill %” API. Closest signals are programming/lineup payloads and guide cache (`GET /guide/status` — lastUpdate / guideTimes / channelIds), which we surface on Admin status as `guide_status` but do not invent a fill percent from.
- **Suggested next phase:** After richer program-ID publish; optional heuristic from programming length vs target window.
- **Owner surface:** Admin / backend
