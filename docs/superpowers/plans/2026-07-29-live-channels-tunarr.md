# Live Channels (Tunarr) Implementation Plan

> **For agentic workers:** Execute task-by-task with TDD. Checkbox tracking. Do not treat this as shipped until Phase 2+ delight criteria pass.

**Goal:** Projectionist fully manages a Tunarr sibling (feature flip, zero Tunarr UI) that feeds Plex Live TV, with guided owner onboarding, library-aware starter channels, household “on now,” and youth-safe recipes.

**Architecture:** Optional-off feature flag + Docker-orchestrated Tunarr sidecar (or BYO URL) + OpenAPI client + recipe/publish layer + Config wizard + Dashboard / inbox delight. Plex remains the watch surface.

**Tech stack:** Python 3.12 / FastAPI / SQLite, React Config + Dashboard, Tunarr `1.3.x` OpenAPI, pytest + frontend unit + mocked e2e as needed.

**Spec:** [2026-07-29-live-channels-tunarr.md](../specs/2026-07-29-live-channels-tunarr.md)

**Deferred & discoveries (living):** [2026-07-29-live-channels-deferred.md](./2026-07-29-live-channels-deferred.md) — append gaps mid-build; do not lose intelligence in chat.

**Tracking convention:** This **plan file** = phase/task progress (`[x]` / partial notes). **`deferred.md`** = living gaps, discoveries, and residual quality work — do not duplicate that list here; link out. When closing a gap, flip status in deferred and check the related task here.

**Test bed:** Phase 0 ops pilot and resource numbers on **Automat** (maintainer Unraid). Keep host runbooks out of the product tree.

---

## Status as of 2026-07-29 (refreshed after wizard + publish)

Prefer this section + task checkboxes over older chat claims. Residual gaps live in [`deferred.md`](./2026-07-29-live-channels-deferred.md) — do not duplicate that list here.

| Spec phase | Status | Notes |
|------------|--------|-------|
| Phase 0 — ops pilot | **Remaining** | Automat: exact Tunarr `1.3.x` pin, RAM/CPU, HDHR/XMLTV, OpenAPI gap list |
| Phase 1 — recipes + OpenAPI client | **Done** (core) | Residual: `schedule-slots` client; richer programming IDs (see below) |
| Phase 2 — flag + wizard + Docker | **Done** (owner wizard + publish APIs) | Admin Live Channels: preflight / lifecycle / starters publish / plex-attach / `CERTIFIED_SERVICES` `tunarr`. Not first-run `WIZARD_STEPS`. Unraid hardening waits on Phase 0 |
| Phase 3 — household delight | **Done** (core) | On-now + Dashboard/Explore + ready nudge. Residuals (weekly-rail, e2e, nudge reset) in deferred — do not regress |
| Ship docs | **Partial** | `CONFIGURATION.md` done; HELP + CHANGELOG Highlights still Task 7 |

**Remaining focus (not Phase 2 redo):** Automat Phase 0 pilot · richer Tunarr program IDs (publish still empty/manual shells) · HELP/CHANGELOG Task 7 · e2e `FeatureFlags` + `live_channels_enabled`.

**Owner UX:** Admin guided checklist (enable → preflight → lifecycle → publish starters → Plex attach) is **done**. Full first-run onboarding wizard integration is **not**.

**Route note:** Owner APIs under `/api/admin/live-channels/*` (plus `POST /api/setup/test/tunarr`, household `GET /api/live-channels/on-now`). Sketch table below is conceptual; match `app.py`.

---

## Global constraints

- Watch surface is **Plex Live TV only** — no Projectionist player / Coax clone / full EPG.
- **Zero Tunarr UI** — API gaps are Projectionist work, not a UI escape hatch.
- Disable stops the container and **keeps** `/config/tunarr` volume.
- Pin Tunarr image to `chrisbenincasa/tunarr:1.3.x` (exact tag at implement time after pilot).
- Follow optional-off patterns already used for Seerr / Plex collections.
- User-facing docs (`HELP.md`, `CONFIGURATION.md`, CHANGELOG Highlights) land in the same PR as the shipping code — this plan is contributor-facing only until then.
- Follow [docs/DOCS_STYLE.md](../../DOCS_STYLE.md) for any member/owner copy.

---

## Module sketch (new)

```
projectionist/
  connectors/
    tunarr.py              # TunarrClient — OpenAPI over HTTP (mirror SeerrClient)
  live_channels/
    __init__.py
    recipes.py             # Taste/motif/collection → channel programming payloads
    starter_pack.py        # Propose 2–4 library-aware starters (+ Chaos / youth-safe)
    docker.py              # Docker pull/start/stop/health (gated by orchestration env)
    preflight.py           # Disk, Docker, Plex reachability, Pass honesty, GPU soft warn
    guide.py               # Read-only guide snapshot for “on now”
    plex_attach.py         # HDHR/XMLTV URLs + discovery health helpers
    publish.py             # Recipe → Tunarr channel/programming orchestrator
    status.py              # Broadcast health strip payload
    nudges.py              # Soft “Live Channels is on” inbox nudge
    plex_pass.py           # Pass honesty / owner confirm
```

Settings keys (proposed; nest under `Settings` like `seerr` / `youth`):

```jsonc
// {DATA_DIR}/settings.json
{
  "features": {
    "live_channels_enabled": false
  },
  "tunarr": {
    "url": "",                       // BYO or resolved sibling URL
    "docker_orchestration": false,
    "image_tag": "chrisbenincasa/tunarr:1.3.x",
    "plex_pass_confirmed": false,
    "last_publish_at": null,
    "last_error": ""
  }
}
```

Env (proposed):

| Env | Role |
|-----|------|
| `PROJECTIONIST_DOCKER_ORCHESTRATION=1` | Allow managed pull/start/stop via Docker socket |
| (optional) `PROJECTIONIST_TUNARR_URL` | Override / seed BYO base URL |
| (optional) `PROJECTIONIST_TUNARR_IMAGE` | Override image pin |

---

## API sketch (owner unless noted)

| Method | Path | Purpose | Landed? |
|--------|------|---------|---------|
| `GET` | `/api/features` | Include `live_channels_enabled` | yes |
| `GET` | `/api/admin/live-channels/status` | Health strip: sidecar, channel count, last publish, last error | yes |
| `POST` | `/api/admin/live-channels/preflight` | Run preflight checks | yes |
| `POST` | `/api/setup/test/tunarr` | Certified-service connection test | yes |
| `POST` | `/api/admin/live-channels/lifecycle` | `{action: start\|stop\|pull\|ensure_running}` when orchestration on | yes |
| `GET` | `/api/admin/live-channels/starter-pack` | Propose starter pack from library | yes |
| `POST` | `/api/admin/live-channels/starters/publish` | Publish selected starters to Tunarr (`confirm=true`) | yes |
| `POST` | `/api/admin/live-channels/channels/from-collection` | Collection → channel | yes (API; no dedicated Config UI yet) |
| `GET` | `/api/live-channels/on-now` | Guide snapshot (owner + members when enabled) | yes |
| `GET` | `/api/admin/live-channels/plex-attach` | Plain-language steps + copy URLs + discovery hint | yes |

Exact shapes follow existing setup / features response conventions in `projectionist/web/app.py` and `projectionist/web/setup.py`.

---

### Task 0: Ops pilot + OpenAPI gap check (Automat)

**Files:** none in-repo required (host runbook on Automat); capture findings into the spec’s Phase 0 notes or a short appendix if durable.

- [ ] Pin Tunarr `1.3.x` on Automat; stand up 2 channels → Plex Live TV
- [ ] Measure image size / RAM / CPU under soft-transcode (1 stream)
- [ ] Confirm OpenAPI covers channels, programming, fillers, media sources without Tunarr UI
- [ ] List API gaps → Projectionist backlog (not Tunarr UI fallthrough)
- [ ] Confirm HDHR + XMLTV URLs Plex accepts

---

### Task 1: Tunarr connector

**Files:**
- Create: `projectionist/connectors/tunarr.py` (pattern: `connectors/seerr.py` + `connectors/http.py` `request_json`)
- Test: `tests/test_tunarr_client.py` (httpretty / mocked HTTP)

- [x] Failing tests for health, list/create channel, set programming, media-source wire
- [x] `TunarrClient(base_url, timeout=…)` — no LAN-exposed admin assumption
- [x] Map errors to clear owner-facing strings (mirror Seerr / *arr style)
- [x] Unit tests pass
- [ ] `schedule-slots` client method (documented in module table; still missing — see deferred)

---

### Task 2: Feature flag + settings nest

**Files:**
- Modify: `projectionist/config_store.py` (`FeatureFlags.live_channels_enabled`, `TunarrSettings` nest)
- Modify: `projectionist/web/app.py` (`FeatureFlagsPayload`, `_features_payload`, settings mask/payload)
- Modify: `frontend/src/pages/ConfigPage.jsx` (optional-off toggle + Admin Live Channels section)
- Modify: `e2e/fixtures/api-mocks.ts` (`FeatureFlags` type + `mockFeatures` defaults)
- Modify: `docs/CONFIGURATION.md` (when shipping)
- Test: `tests/test_live_channels.py`, features payload tests

- [x] Default `live_channels_enabled=false`
- [x] `GET /api/features` returns the flag
- [x] Settings round-trip persists `tunarr.*`
- [x] Frontend can read/write the flag (Admin → Live Channels)
- [x] `CONFIGURATION.md` documents flag / env / Tunarr nest
- [ ] e2e `FeatureFlags` type + `mockFeatures` defaults include `live_channels_enabled`

---

### Task 3: Recipes + starter pack (+ youth gate)

**Files:**
- Create: `projectionist/live_channels/recipes.py`
- Create: `projectionist/live_channels/starter_pack.py`
- Reuse: taste clusters; `GET /api/library/motifs` (`app.py`); Plot Lab filters in `projectionist/library/query.py`; curated lists; `connectors/plex_collections.py`
- Youth: `projectionist/youth/apply.py`, `projectionist/youth/rating_gate.py`; `YouthSettings.max_content_rating`
- Test: `tests/test_live_channels.py` (recipes / starter / youth)

- [x] Build programming payloads from taste / motifs / published collections
- [x] Starter pack proposes 2–4 channels from *this* library + Chaos/shuffle + optional youth-safe
- [x] Youth-flagged recipes filter via rating gate (fail-closed for unrated when youth applies)
- [x] Collection → channel path (`POST …/channels/from-collection` + publish helpers)
- [x] Empty-library honesty (no fake demo channels)
- [ ] Rich lineup fill with real Tunarr program IDs (today: flex/title stubs — see deferred)

---

### Task 4: Lifecycle + preflight + certified service

**Files:**
- Create: `projectionist/live_channels/docker.py`, `preflight.py`, `status.py`, `plex_pass.py`
- Modify: `projectionist/web/setup.py` — `"tunarr"` in `CERTIFIED_SERVICES`; `test_tunarr` / connection recording
- Modify: `projectionist/web/app.py` — setup test route + live-channels status / preflight / lifecycle routes
- Frontend: **Admin → Live Channels** guided surface on Config (not first-run `WIZARD_STEPS`)
- Plex Pass gap: owner confirm checkbox in preflight (`plex_pass_confirmed`)
- Test: `tests/test_live_channels.py`, `tests/test_live_channels_api.py`

- [x] Preflight: Docker orchestration?, disk?, Plex reachable?, Pass honesty, GPU soft warning
- [x] Managed mode: pull / start / stop / ensure_running; volume kept on disable (best-effort stop from Config toggle)
- [x] BYO mode when orchestration off
- [x] Admin Live Channels guided surface (preflight → lifecycle → health strip) — **not** first-run setup wizard
- [x] Broadcast health strip data from status endpoint
- [x] `POST /api/setup/test/tunarr` + certification recording
- [ ] First-run onboarding wizard step(s) for Live Channels (if product still wants that)
- [ ] Unraid-specific volume/network hardening + exact image pin after Automat pilot

---

### Task 5: Publish path + Plex attach

**Files:**
- Create: `projectionist/live_channels/publish.py`, `plex_attach.py`
- Modify: `projectionist/web/app.py` (publish + plex-attach routes)
- Frontend: Admin Live Channels — Publish starters + “Add to Plex Live TV” checklist with copy URLs
- Test: publish + attach in `tests/test_live_channels.py` / `tests/test_live_channels_api.py`

- [x] Publish starters → Tunarr OpenAPI (`confirm=true`)
- [x] Plain-language attach steps; copy tuner/guide URLs in Admin UI
- [x] Best-effort tuner discovery green-check
- [x] Persist `last_publish_at` / `last_error` on Tunarr settings / status
- [ ] Dedicated Config UI for collection → channel (API exists)

---

### Task 6: Household delight

**Files:**
- Create: `projectionist/live_channels/guide.py`, `nudges.py`
- Modify: `frontend/src/pages/DashboardPage.jsx` + `OnNowPanel` (also Explore compact)
- Modify: member weekly rail / enthusiast nudge paths (`taste` deliver rails; `notifications/service.py`; `nudge_opt_in` on users)
- Test: on-now + nudge unit coverage in `tests/test_live_channels.py`

- [x] `GET /api/live-channels/on-now` read-only guide snapshot
- [x] Dashboard / Explore “On now” panel; CTA opens Plex (deep link — no in-app playback)
- [ ] Member weekly-rail slot when multi-user + flag on
- [x] Soft inbox ready nudge; respect `nudge_opt_in`; once-ever via `related_id=live-channels-ready`
- [ ] Playwright e2e for on-now; nudge reset on disable/re-enable (see deferred residuals)
- [ ] Live Tunarr guide field-shape validation (Automat)

---

### Task 7: Docs + release coupling

**Files:** `docs/HELP.md` (owner section), `docs/CONFIGURATION.md`, `CHANGELOG.md` Highlights, version lockstep per `docs/RELEASE.md` when shipping

- [ ] Owner HELP: enable wizard, Plex attach, what Live Channels will not do
- [x] CONFIGURATION: flag, env, Tunarr settings nest
- [ ] CHANGELOG `### Highlights` benefit-led copy
- [x] No Tunarr UI instructions as supported path (product constraints + Admin copy)

---

## Suggested phase → task map

| Spec phase | Tasks | Progress (2026-07-29) |
|------------|-------|------------------------|
| Phase 0 — ops pilot | Task 0 | open |
| Phase 1 — recipes + OpenAPI client | Tasks 1, 3 | core done; schedule-slots / rich lineup residual |
| Phase 2 — flag + wizard + Docker | Tasks 2, 4, 5 | Admin guided surface done; first-run wizard + Automat pin open |
| Phase 3 — household delight | Task 6 | on-now + nudge done; weekly-rail slot / e2e open |
| Plex attach (with Phase 2) | Task 5 | done (API + Admin UI) |
| Ship docs | Task 7 | CONFIGURATION done; HELP + CHANGELOG open |

---

## Out of scope (plan)

- Homegrown HDHomeRun emulator
- Embedding Tunarr in the Python image
- Full newspaper guide / remote control
- Multi-lineup dayparts beyond shuffle/sequential
- Docker-less cloud AIO as first-class (BYO only)
- Implementing application code in the docs-only landing PR

---

## Success criteria

- Owner can enable Live Channels through one wizard story and end with channels visible in Plex Live TV.
- Starter pack is library-aware (not empty demos); youth recipes respect the rating gate.
- Disable stops Tunarr; re-enable restores volume/state.
- Households see “on now” with a Plex CTA; no in-app playback.
- Tunarr admin UI is never required for a supported path.
