# Live Channels job rail (approach B) Implementation Plan

> **For agentic workers:** User approved **B**. Design review is done — implement. Do not rewrite into wizard C. Do not Repair Automat prod.

**Goal:** One serialized Live job object + sticky rail, honest Plex map health, and Refresh (never DELETE) vs Rebuild (only delete path) as C-reusable primitives.

**Architecture:** Aggregate existing engine / continuity / publish progress plus a new Plex/refill job store into `{ kind, phase, percent, message, startedAt }`. Stations, Setup, and Overview read that one object. Attach/refresh never DELETE the Tunarr XMLTV DVR; Rebuild (`force_recreate`) is the only delete path.

**Tech Stack:** FastAPI + in-process progress stores, React Admin Live Channels / Overview, pytest + frontend `node --test`.

## Global Constraints

- Semver **1.35.0** (user-visible capability), Hub-first ship after QA.
- QA visual campaign on `:8790` only; never prod `:8788`; never prod Repair / `reloadGuide`.
- Always allowed while busy: Refresh status, copy URLs, tabs, form edits.
- Disable **all** mutating Live buttons while a job runs.
- One Refresh / Rebuild pair (not a fourth Attach/Repair copy).
- Path A host build OK for visual QA only; CA proof is Path B Hub pull.

---

### Task 1: Unified job object

**Files:**
- Create: `projectionist/live_channels/job.py`
- Modify: `projectionist/live_channels/status.py` (include `job`)
- Modify: `projectionist/web/live_channels_routes.py` (serialize starts; 409 if busy)
- Test: `tests/test_live_channels.py`, `tests/test_live_channels_api.py`

**Produces:** `build_live_job()` → `{ kind, phase, percent, message, started_at, startedAt, busy }`. Kinds: `plex_refresh`, `plex_rebuild`, `engine`, `continuity`, `publish`, `refill`.

### Task 2: Honest health + no auto-DELETE

**Files:**
- Modify: `projectionist/live_channels/status.py` — `guide_ok` / Attached = live `mapping_ok`
- Modify: `projectionist/live_channels/plex_attach.py` — kill short-map auto-DELETE in Attach; `refresh_plex_live_tv_channels` never `force_recreate`
- Rebuild = `repair_plex_tunarr_livetv` only (`force_recreate=True`)
- Update attach/refresh error copy to say **Rebuild tuner in Plex**, not Repair

### Task 3: Frontend rail + copy + one pair

**Files:**
- Create: `frontend/src/lib/liveChannelsJob.js` + `.test.mjs`
- Modify: `frontend/src/lib/liveChannelsCopy.js` + tests
- Modify: `frontend/src/pages/admin/LiveChannelsSection.jsx`, `frontend/src/pages/ConfigPage.jsx`
- Modify: `frontend/src/styles/04-config-onboarding.css`
- Modify: `frontend/src/api/client.js` if needed

**Produces:** Sticky `aria-live` rail; Refresh Plex map / Rebuild tuner in Plex; Setup happy path = Projectionist writes tuner/guide; 5-step wizard collapsed under “Plex didn’t see the tuner.”; Overview health line + rail snippet.

### Task 4: Docs + QA IDs

**Files:** CHANGELOG 1.35.0, `docs/HELP.md`, AUTOMAT if it names Repair-as-delete, `.cursor/skills/interactive-ui-qa/reference.md` Live Channels IDs.

### Task 5: Gates → QA `:8790` visual → Hub-first 1.35.0 → prod rollout → tear down QA
