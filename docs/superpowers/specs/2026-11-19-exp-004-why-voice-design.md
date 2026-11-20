# EXP-004: Voice pass on *why* sentences

**Status:** Accepted (Lane B)  
**Date:** 2026-11-19  
**Owning item:** [EXP-004](../../EXPERIENCE.md#roadmap-items)  
**Related:** PRD-001 / UX-012 quality gate · PRIV-001 · [PRIVACY.md](../../PRIVACY.md)

---

## 0. Verification on 1.40.1 (required before changing templates)

**Source:** Automat prod container `projectionist` image `romwil/projectionist:1.40.1`, `DATA_DIR=/config`, `feed_for_you(db, limit=50)` against `/config/projectionist.db` (2026-11-19). Browser login was required for HTTP; sampling used in-container Python (read-only).

| Screenshot claim (older reviews) | On 1.40.1 prod sample (n=28 cards) |
|----------------------------------|-------------------------------------|
| `both stories turn on a took place` | **Absent.** PRD-001 gate holds for that template. |
| `brandon Christensen worked on both` (lowercase given name) | **Not seen** in this sample; crew lines were `Francis Lawrence` / `Christopher Nolan`. Keep a capitalization gate anyway. |
| `qa-owner, You watched…` (account handle) | **Not seen** in this sample. Keep a handle refusal on the finished sentence (PRIV-001). |
| — | **Still broken:** many cards use `both are about …` with commercial / reception / format fragments. |

**Live junk examples (must refuse):**

- Box office / franchise: `a million worldwide`, `a grossed million`, `a third installment`, `a fifth highest`
- Awards / reception: `a golden globe`, `a generally positive`, `a received generally`, `a best original`, `modern audiences`, `best shows`
- Format / incomplete: `a science fiction`, `an american dystopian`, `an archival footage`, `a half hour`, `a mid century`, `a covid pandemic`

**Acceptable examples in the same sample:** `both are about a buried treasure`, `both are about a media platform`, properly capitalized `… worked on both`.

Reader-scoped `You watched` / `You finished` for the member’s own seeds remains correct under PRIV-001; do not strip “You” for the reader’s evidence.

---

## 1. Purpose

For you / inbox / newsletter *why* lines read as something a curator would say: named plot nouns, credited people, or a collection — never Wikipedia leftovers or debug fragments.

**Done when:** sampled For you cards show no fragment, no lowercase crew names, no account handles; unit tests encode the 1.40.1 junk corpus.

---

## 2. Approach

| Approach | Choice |
|----------|--------|
| A. Rewrite only outer `You …` template | Leaves inner plot junk |
| B. LLM rewrite every why | Out of scope; nondeterministic |
| **C. Tighten term honesty + `readable_why` + voice templates (recommended)** | Matches PRD-001; refuses empty rather than shipping junk |

**Choice: C.**

---

## 3. Design

### 3.1 Voice templates (server)

| Kind | Before | After |
|------|--------|--------|
| Plot (`checkable_plot_sentence`) | `Both are about {phrase}.` | `They share {phrase}.` |
| Crew (`_inner_link`) | `{Name} worked on both` | `{Name} is behind both` |
| Collection | `both are part of {collection}` | `both belong to {collection}` |
| Outer (`watched_bridge`) | `You {verb} {seed}; {peer} — {clause}` | Unchanged (reader’s own evidence) |

Folding a leading `They` / `Both` into the clause after the emdash follows the existing `Both` → `both` fold.

### 3.2 Quality gate

Extend denylists and `readable_why` so the live 1.40.1 junk corpus fails before a card is built:

- Commercial / reception / award / format unigrams and reject phrases from §0
- `-ly` right-hand words treated as adverbs (not only the small `_ADVERBS` set)
- Adjective-only heads (`positive`, `highest`, `dystopian`, `original`, …)
- Finished sentence refuses account-handle prefixes (`qa-owner,`, bare `user_…,` before `You`)
- Crew display names: if any token starts lowercase, Title-Case before emit; refuse still-broken names

Empty / omit the card is better than a bad why (existing For you behavior).

### 3.3 Tests

- Extend `tests/test_why_sentence_gate.py` with the live junk corpus and new template strings
- Keep household bridge crew tests (they `.lower()` the blob); assert display capitalization where we check raw sentences

### 3.4 Out of scope

- EXP-003 cinema layout
- Re-indexing neighbors / rewriting stored `plot_link_json` offline (read path already rebuilds via honesty)
- Release / version bump / Automat rollout
- Changing PRIV-001 seed scoping
