# EXP-013 Explore Default Home Implementation Plan

> **For agentic workers:** Implement task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Explore the server and web default home; honor explicit Chat; migrate legacy `auto`.

**Architecture:** One schema migration rewrites stored `auto` → `explore`. Read/write paths and `resolveDefaultHome` treat `auto`/unset as Explore. HELP + Profile copy match.

**Tech Stack:** SQLite migrations, FastAPI auth me, React `defaultHome.ts`, node:test, pytest.

## Global Constraints

- No version bump, Hub publish, or Automat rollout.
- Do not touch Live / PRD-007 frozen surfaces.
- Do not commit `docs/reviews/` or `.cursor/review/`.
- Docs meet `docs/DOCS_STYLE.md`.
- E2e port is **8799**, never 8788.

---

### Task 1: Failing tests for Explore-as-default

**Files:**
- Modify: `tests/test_default_page_preference.py`
- Modify: `frontend/src/lib/defaultHome.test.mjs`

- [x] **Step 1:** Change backend expectation: `GET /api/auth/me` → `default_page == "explore"`; add case that PATCH `auto` returns/stores explore.
- [x] **Step 2:** Change frontend unit: unset/auto/nonsense → `/explore` even when `llmConfigured: true`; keep explicit chat/explore.
- [x] **Step 3:** Run the two suites; confirm failures before implementation.

### Task 2: Server default + migration

**Files:**
- Modify: `projectionist/library/db/migrations.py` (version 67)
- Modify: `projectionist/library/db/_schema.py` (migration method)
- Modify: `projectionist/library/db/_users.py` (read/write coerce)
- Modify: `projectionist/web/auth.py` (`CurrentUser` + `row_to_current_user`)
- Modify: `projectionist/web/app.py` if any `"auto"` fallback on me payload

- [x] **Step 1:** Add `_migrate_explore_default_home`: UPDATE `auto` → `explore`.
- [x] **Step 2:** Register as migration 67.
- [x] **Step 3:** Coerce read `auto`/missing → `explore`; normalize write empty/invalid/`auto` → `explore` (still accept `chat`/`explore`/`auto` on input for validation).
- [x] **Step 4:** Re-run `tests/test_default_page_preference.py`.

### Task 3: Frontend resolver + Profile + HELP

**Files:**
- Modify: `frontend/src/lib/defaultHome.ts`
- Modify: `frontend/src/pages/settings/ProfilePage.tsx`
- Modify: `docs/HELP.md` (Default page section + no-provider blurb if needed)
- Modify: `frontend/src/lib/authGate.ts` fallbacks to `"explore"` where cheap

- [x] **Step 1:** `resolveDefaultHome` → Explore for non-chat preferences; drop LLM branch for default.
- [x] **Step 2:** Profile Auto help = “Explore (product default)”.
- [x] **Step 3:** HELP: Auto = Explore product default; Explore is home.
- [x] **Step 4:** Run `cd frontend && npm run test:unit` (or the defaultHome file) + lint on touched files.

### Task 4: Board status + PR

**Files:**
- Modify: `docs/EXPERIENCE.md`, `docs/roadmap/README.md` (EXP-013 → `done`)

- [x] **Step 1:** Mark EXP-013 `done` in both tables.
- [ ] **Step 2:** Commit, push, open PR, wait for required checks, merge with `--merge --delete-branch`.
- [ ] **Step 3:** `git checkout main && git pull --ff-only`.
