# Storage Intelligence TV Implementation Plan

> **For agentic workers:** Execute task-by-task with TDD. Checkbox tracking.

**Goal:** Bring TV shows into Storage Intelligence with durable show size rollups, a 5× paginated candidate buffer with async refill, visible-row freshness enrichment, and honest agent TV progress APIs — then ship as v1.28.0.

**Architecture:** Extend episode rollups to set `library_items.file_size`; expand purge cache to 100 with top-up-after-mutation; enrich visible pages from SQLite (+ *arr size when configured); paginate Dashboard purge table; expose `total_episode_count` in query/tools.

**Tech Stack:** Python 3.12 / FastAPI / SQLite, React dashboard, pytest + frontend node:test.

## Global Constraints

- Page size 20, buffer target 100, refill when buffer &lt; 80.
- Full remove default for purge; acquisition exclusions recorded.
- Do not stage unrelated WIP in the release commit.
- Follow `docs/RELEASE.md` for v1.28.0 ship.

---

### Task 1: Show file_size rollup + backfill

**Files:**
- Modify: `projectionist/library/db/_library_lookup.py` (`_update_show_episode_rollups_on_conn`)
- Modify: `projectionist/library/db/_schema.py` + `migrations.py` (migration 39 backfill)
- Test: `tests/test_library_episodes.py` (or new `tests/test_show_rollups.py`)

- [ ] Failing test: after replace episodes with sizes, show `file_size` equals sum
- [ ] Implement rollup SQL to include `SUM(file_size)`
- [ ] Migration 39: backfill all shows from `library_episodes`
- [ ] Tests pass

### Task 2: Purge buffer, enrich, top-up, shows

**Files:**
- Modify: `projectionist/scheduler/tasks/purge_candidates.py`
- Modify: `projectionist/preferences/purge.py`
- Modify: `projectionist/web/app.py` (enrich + top-up triggers on delete/dismiss)
- Test: `tests/test_purge_candidates_cache.py`, new enrich/top-up tests

- [ ] `DEFAULT_LIMIT = 100`, constants `PAGE_SIZE=20`, `BUFFER_TARGET=100`, `REFILL_THRESHOLD=80`
- [ ] `top_up_purge_candidates(db, settings, *, target=100)` appends excluding existing+dismissed
- [ ] `enrich_purge_candidates(db, settings, items)` refreshes size/last_watched; *arr size for visible
- [ ] delete/dismiss endpoints drop keys then schedule/top-up if &lt; 80
- [ ] GET purge-candidates optionally enriches by `rating_keys` query or body on POST enrich

### Task 3: Paginated Storage Intelligence UI

**Files:**
- Modify: `frontend/src/pages/DashboardPage.jsx` (`PurgeTable`)
- Modify: `frontend/src/api/client.js` if new enrich endpoint
- Test: frontend unit if extractable helpers; otherwise rely on API tests + manual smoke

- [ ] Type column (Movie/Show)
- [ ] Page state; display `slice(page*20, page*20+20)`
- [ ] Enrich visible keys on mount/page change
- [ ] Keep/Dismiss + Purge trigger reload; show refill meta when count climbing

### Task 4: Agent TV honesty

**Files:**
- Modify: `projectionist/library/query.py`, `projectionist/agent/tools/_definitions.py`
- Modify: `projectionist/library/episodes.py` (`summarize_tv_progress`)
- Test: `tests/test_library_query.py`, episode/progress tests

- [ ] Sort + min/max total episode filters
- [ ] Progress payload totals

### Task 5: Docs + release v1.28.0

**Files:** HELP.md (Storage Intelligence), CHANGELOG, version lockstep, release-notes.json

- [ ] Full pytest + frontend unit/lint/build
- [ ] Version bump, CHANGELOG Highlights, generate release notes
- [ ] Commit, tag, `gh release`, `docker-release.sh` per user ship request
