# EXP-013: Explore is the default home

**Status:** Accepted (board decision 2026-11-18; Lane B)  
**Date:** 2026-11-19  
**Audience:** Developers / Cursor agents  
**Owning item:** [EXP-013](../../EXPERIENCE.md#roadmap-items)  
**Related:** [DESIGN.md](../../DESIGN.md) principle 2 · [HELP.md](../../HELP.md) · accepted drop `2026-11-19-explore-default-home.md`

---

## 1. Purpose

Explore is the front door for every member, Youth, and guest, on every client. Chat stays a primary peer — deep curator loop, not home. This change makes the **server** and **web redirect** match that decision for new accounts and anyone still on the legacy `auto` preference.

Docs (DESIGN principle 2, HELP start-here) already say Explore is home. This item ships the runtime default and migrates `auto`.

---

## 2. Locked decisions (do not re-open)

| Decision | Source |
|----------|--------|
| Explore is default home for every member and every client | Board 2026-11-18 |
| Explicit `default_page = chat` still lands on Chat | EXP-013 Done when |
| `auto` (unset / legacy product default) resolves like Explore | EXP-013 Why + accepted drop |
| No release / version bump in this PR | Lane B constraints |
| No Live / PRD-007 work | Freeze |

---

## 3. Approaches considered

| Approach | Pros | Cons |
|----------|------|------|
| **A. Resolve-only** — leave stored `auto`; change `resolveDefaultHome` + API fallbacks to Explore | Smallest diff | Settings still show “Auto → Chat when LLM”; new inserts keep DEFAULT `'auto'` forever |
| **B. Migrate + resolve + defaults (recommended)** — UPDATE `auto`→`explore`; coerce remaining `auto` on read; frontend `auto`→`/explore`; HELP/Profile copy | Matches Done when; Settings shows Explore after migrate | Slightly more surface area |
| **C. Drop `auto` from the API** | Cleaner long-term | Breaks older clients / Profile radios without a deprecation path |

**Choice: B.** Keep accepting `auto` in PATCH/GET for one release of client compatibility; treat it as Explore everywhere.

---

## 4. Design

### 4.1 Server

1. **Migration** (next schema version):  
   `UPDATE users SET default_page = 'explore' WHERE lower(trim(default_page)) = 'auto';`  
   SQLite cannot cheaply rewrite the column DEFAULT from migration 59 (`DEFAULT 'auto'`). New inserts that omit the column may still land as `'auto'` until an explicit write — therefore also coerce on read.
2. **Read path** (`row_to_current_user`, `_row_to_user`): missing / `auto` → surface `"explore"`.
3. **Write path** (`update_user` / auth me): invalid or empty → `"explore"` (not `"auto"`). Still accept storing `"auto"` if a client sends it; read coercion makes GET return Explore after a later pass, or we normalize writes of `auto`→`explore`. **Normalize writes:** PATCH/update of `auto` stores `explore`.
4. **`CurrentUser.default_page`** dataclass default: `"explore"`.
5. **API pattern** stays `^(auto|chat|explore)$` so older clients do not 422.

### 4.2 Frontend

1. **`resolveDefaultHome`**: `chat` → `/chat`; `explore` → `/explore`; anything else (`auto`, unset, nonsense) → `/explore`. **Stop** branching on `llmConfigured` for the default (LLM honesty on Chat/Explore pages is unchanged).
2. **Profile → Default page**: Auto help text becomes “Explore (product default)” regardless of LLM; lead copy stays “Where Projectionist opens after you sign in.”
3. **authGate** fallbacks may keep or switch to `"explore"`; resolution must land on Explore either way.

### 4.3 Docs / copy

1. **HELP** “Default page, password, and sessions”: Auto = product default (Explore), not Chat-when-LLM.
2. **HELP** “When no chat provider…”: Explore remains the honest landing when unset; explicit Chat still honored — tighten so it does not imply Auto means Chat-with-LLM.
3. DESIGN principle 2 already Explore-first — no change required unless a stray “Chat-first” remains elsewhere in member-facing copy touched by this PR.
4. Board / EXPERIENCE status → `in progress` in the PR, then `done` (no version) after merge — or `shipped` only when a release notes it; for Lane B use **`done`** on the board until a release tags it, matching “merge ≠ release”. Prefer status **`done`** with a note “merged, awaiting release” if the board vocabulary needs a version for `shipped`.

**Board convention used here:** set EXP-013 to **`done`** after merge (implementation complete; not yet in a Hub release).

### 4.4 Out of scope

- Native client capability bump (web + server preference only; natives already assume Explore-home).
- Cinema-first Explore layout (EXP-003).
- Removing the Auto radio from Settings.
- Release rituals.

---

## 5. Testing

| Layer | Proof |
|-------|--------|
| Backend unit | New/owner user `GET /api/auth/me` → `default_page == "explore"`; PATCH `chat` round-trips; PATCH `auto` stores/returns explore; unknown still 422 |
| Frontend unit | `resolveDefaultHome`: unset/auto/nonsense → `/explore` with or without LLM; explicit chat/explore honored |
| Docs | HELP Default page section matches Profile labels |
| E2e | Not required for this preference-only change unless an existing e2e asserts `/` → `/chat` — update that assertion if present |

---

## 6. Done when (acceptance)

- New member / single-owner first paint at `/` redirects to `/explore` (390 and 1440 use the same resolver).
- `default_page = chat` still redirects to `/chat`.
- Accounts that were `auto` behave as Explore after migration.
- Help describes Explore as home; Auto is not described as Chat-when-LLM.
- No release / Hub / Automat rollout in this change.
