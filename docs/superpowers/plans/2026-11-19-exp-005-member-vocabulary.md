# EXP-005 Member Vocabulary Implementation Plan

> **For agentic workers:** Implement task-by-task.

**Goal:** Remove system terms from member/Youth surfaces; gate with a CI denylist lint.

**Architecture:** Fix known string leaks; add `scripts/lint-member-copy.mjs`; wire Lint workflow.

**Tech Stack:** Node lint script, React copy, Python feed notes, pytest / node:test updates.

## Global Constraints

- No release / version bump / Hub / Automat.
- Admin may keep “Scheduled Tasks”.
- Do not commit `docs/reviews/`.

---

### Task 1: Fix member-facing leaks + tests

- [ ] For-you empty note in `feeds.py` + agent tool note; update pytest assertions
- [ ] Chat/Beyond expand label; TypingIndicator titles; KnowledgeCoverage member blurb (no Scheduled Tasks on Explore)
- [ ] `substitute_curator_name` treats default `Curator` as generic via display helper

### Task 2: Lint + CI

- [ ] `scripts/lint-member-copy.mjs` + `npm run lint:member-copy` (root or frontend)
- [ ] Wire into `lint.yml`
- [ ] Board EXP-005 → `done`
