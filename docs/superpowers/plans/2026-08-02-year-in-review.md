# Year in Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship an opt-in, auth-gated Year in Review cinema reel fed by per-user watch-tracker rollups (not household Plex aggregates), with tease/drop delivery and owner self-generate.

**Architecture:** Implement watch-tracker foundation (events → sessions/completions → year rollups), then a snapshot program that builds adaptive chapter JSON, stores `year_in_review_snapshots`, and delivers inbox/email deep links. Frontend plays a CSS-only guided reel.

**Tech Stack:** Python 3.12, FastAPI, SQLite/WAL, React, pytest, frontend unit tests. No framer-motion; no LLM for v1 copy.

## Global Constraints

- Never invent per-user history from household `view_count`.
- Honesty vocabulary: `certain` / `likely` / `plex_event_only`.
- Guests skipped; opt-in required for delivery.
- No public secret share URLs in v1.
- Focused packages: `projectionist/watch_tracker/`, `projectionist/year_in_review/`.
- Spec: `docs/superpowers/specs/2026-08-02-year-in-review-design.md`.
- Tracker SoT: `docs/superpowers/plans/2026-08-03-watch-tracker.md`.

---

## File map

### Watch tracker
- Create: `projectionist/watch_tracker/{__init__,models,store,correlate,plex_history,rollups,webhook_adapter}.py`
- Create: `projectionist/scheduler/tasks/watch_history_ingest.py`
- Modify: `projectionist/connectors/plex.py`, `projectionist/web/webhooks.py`
- Modify: `projectionist/library/db/{migrations.py,_schema.py}`
- Modify: `projectionist/scheduler/tasks/__init__.py`, `projectionist/web/app.py`
- Test: `tests/test_watch_tracker.py`, `tests/test_watch_correlation.py`, `tests/fixtures/plex/history_*.xml`

### Year in Review
- Create: `projectionist/year_in_review/{__init__,models,store,rollups_bridge,snapshot,delivery,copy}.py`
- Create: `projectionist/year_in_review/chapters/{__init__,registry,core,social}.py`
- Create: `projectionist/scheduler/tasks/year_in_review.py`
- Modify: notifications kinds, users prefs, HELP, CHANGELOG
- Create: `frontend/src/pages/YearInReviewPage.jsx`, `frontend/src/lib/yearInReview*.js`
- Test: `tests/test_year_in_review.py`, `frontend/src/lib/yearInReview.test.mjs`

---

## Task 1: Watch event ledger + history ingest

- [ ] Migration 44: `watch_ingest_cursors`, `watch_source_identities`, `watch_events` (+ indexes)
- [ ] `WatchEventInput`, fingerprinting, `ingest_watch_events`
- [ ] `PlexClient.history_page` + normalize + scheduler task (15 min)
- [ ] Owner `GET /api/admin/watch-tracker/status`
- [ ] Tests: idempotent ingest, unmapped isolation, cursor behavior

## Task 2: Webhook observations + correlation

- [ ] Migration 45: `watch_sessions`, `watch_session_events`, `watch_completions`
- [ ] Refactor webhook to ingest pause/stop/scrobble below prompt threshold; keep prompt gate
- [ ] `correlate.py` merge/completion rules (algorithm_version=1); rebuild helper
- [ ] Year rollup from completions for `user_id` + calendar year
- [ ] Tests: multi-sitting, duplicate scrobble, two users, year bounds

## Task 3: YIR snapshot + chapters + delivery

- [ ] Migration 46: `year_in_review_snapshots`, `year_in_review_opt_in`, notification kind
- [ ] Chapter registry + poetic templates
- [ ] `build_and_store_reel`, `deliver_year_in_review`
- [ ] Scheduler tease/drop windows; admin self generate
- [ ] Member `GET /api/year-in-review/{year}`
- [ ] Tests: empty skip, guest skip, opt-in gate, snapshot shape

## Task 4: Frontend reel + settings + inbox

- [ ] Route `/year-in-review/:year`, cinema player, share-card helpers
- [ ] Settings opt-in; admin generate button; inbox deep link
- [ ] Unit tests for player helpers
- [ ] HELP + CHANGELOG Highlights

## Task 5: Verify and release

- [ ] `pytest` for new suites; `npm run lint` + `npm run build`
- [ ] Version bump, release notes, tag, `gh release` / docker if feasible

---

## Acceptance

- Fixture-driven tracker rollup → YIR reel with adaptive chapters.
- No household aggregate used as personal completion evidence.
- Owner can generate/send self; members play private reel; guests blocked.
- Release notes Highlights benefit-led and honesty-preserving.
