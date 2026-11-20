# EXP-005: Member-vocabulary sweep

**Status:** Accepted (Lane B)  
**Date:** 2026-11-19  
**Owning item:** [EXP-005](../../EXPERIENCE.md#roadmap-items)  
**Related:** [DOCS_STYLE.md](../../DOCS_STYLE.md) Names glossary · UX-006 / GRO-015

---

## 1. Purpose

Members and Youth never see system internals. Banned on those surfaces: `cosine`, `Scheduled Tasks`, `turnstyle` (as UI jargon), `agent activity`, `CuratorX`. One assistant name via existing `curatorDisplayName` / `curator_display_name` helpers (never a bare “Curator”).

**Done when:** a copy lint passes in CI.

---

## 2. Approach

| Approach | Choice |
|----------|--------|
| A. Manual sweep only | Incomplete without a gate |
| **B. Denylist lint + fix leaks (recommended)** | CI fails on banned phrases in member-facing globs; Admin exempt |
| C. Full string allowlist of every member sentence | Too brittle for this PR |

**Choice: B.** Denylist of forbidden substrings; path allowlist for Admin / owner-only / developer docs.

---

## 3. Design

### 3.1 Forbidden (member / Youth UI + API notes they see)

Case-insensitive unless noted:

- `cosine`
- `Scheduled Tasks`
- `turnstyle view` (code identifiers may keep `turnstyle`)
- `agent activity`
- `CuratorX`

### 3.2 Path allowlist (may still contain those phrases)

- `frontend/src/pages/ScheduledTasksPage.tsx`, Admin pages, owner-only health copy
- `**/*.test.mjs` / `tests/` except when asserting member-facing copy
- Comments in non-UI modules; `docs/` owner/developer guides
- Lint script and this spec/plan

### 3.3 Copy replacements (examples)

| Before | After |
|--------|--------|
| “not a cosine guess… let Scheduled Tasks catch up Named kinship” | “No named link to something you finished yet. Finish a title, or give the household a bit more time to learn links.” |
| “Expand N titles in turnstyle view” | “Expand N titles” |
| “Show agent activity” | “Show thinking details” |
| Bare `{curator_name}` → `Curator` | Resolve via `curator_display_name` → nickname / “Your curator” |

Admin Monday pass / Knowledge coverage owner blurb may keep **Scheduled Tasks** (owner workbench). Explore/member empty notes must not.

### 3.4 Lint

`scripts/lint-member-copy.mjs` — walk member globs, fail on denylist hits outside allowlist. Wired into `.github/workflows/lint.yml` Frontend job and `frontend/package.json` `lint:member-copy`.

### 3.5 Out of scope

- EXP-010 Chat quieter layout
- Renaming CSS/class `turnstyle-*` identifiers
- Release / version bump
