# Facet Alias Architecture — Design Options

> **Status:** Freeze **lifted for Phase 0–A** of the locked closed-loop plan.  
> Parent: [`docs/superpowers/specs/2026-08-01-closed-loop-augmentation.md`](../specs/2026-08-01-closed-loop-augmentation.md) (Cursor plan `facet_taxonomy_architecture_7186fdb9`).  
> Hybrid registry-first remains the ranked hot-path approach. Library chips + local-model NL stay deferred (Phase D).
>
> **Still gated:** Do not expand facets beyond Phase A scope; do not auto-merge taxonomy into image seed; do not big-bang migrate IdleScheduler tasks.
>
> **Ship independence:** **v1.30.2 gap-rail correctness** remains the production baseline and ships independently of the closed-loop platform.

**Related shipped behavior:** `88c9eb1` / release notes **1.30.2** — NL gap asks must not `search_tv` the sentence; discover + structured filters + verified TMDB ids.

**Working-tree WIP (uncommitted as of 2026-08-01):** see §1.

---

## Owner decision (2026-08-01) — updated

**Prior freeze** held WIP until approach selection. **Approach selected:** hybrid registry-first hot path under the Unified Closed-Loop Augmentation Engine (amended).

- **Phase 0–A unlocked** — closed-loop substrate + layered facets / consumer parity per locked plan.
- **1.30.2 gap-rail behavior** remains the production baseline.
- **Still deferred:** library/Explore chip synonym product decision; optional local-model NL; broad IdleScheduler migration onto `BaseAugmentationTask`.

---

## 1. WIP on the tree — honest summary

### What landed (uncommitted)

| Area | State |
|------|--------|
| `projectionist/facets/` | **New package** — `registry.py`, `resolve.py`, `intent.py`, `__init__.py`, packaged seed `data/facet_aliases.json` |
| Seed content | Genre aliases + TV↔movie crosswalk, one facet pack (`history_tv` keyword/theme rules), `tv_types`, NL `intent` rules, `motif_search_aliases` |
| `agent/tools/__init__.py` | **Moved** former `_GENRE_ALIASES` / NL regex / Chernobyl keyword packs / TV-type maps into facets helpers; gaps + `explore_genre` call `resolve_genre_ids` / `augment_gaps_args_from_query` / pack filter |
| `live_channels/publish.py` | Motif name expansions now call `motif_search_expansions` |
| `tests/test_facets_registry.py` | **New** unit coverage for seed resolve, fail-closed ambiguous/unresolved, intent parse, pack filter, DATA_DIR overlay |
| `pyproject.toml` | `package-data` for `projectionist.facets` / `data/*.json` |
| Orthogonal | Extra saved-library sanitize tests + release-notes `generated_at` bump — **not** alias-platform work |

### Verdict: **partial platform / half-move** (not a finished rearchitecture)

- **Not** “just a file move”: there is a real resolver API (fail-closed ids, packs, overlay merge, intent rules).
- **Not** “platform done”: only **gaps path + explore_genre TMDB resolve + live motif search terms** consume it. Library SQL genre filters, explore facet browse, MCP surface, and most motif/tag paths still use **string/substring ownership** of genre/tag tokens with **no** shared synonym layer.
- Seed **grew beyond** the old inlined dicts (extra aliases: anime, rom-com, cyberpunk, expanded motif keys, extra history keywords). That is useful foreshadowing but also **scope creep** relative to “extract what gaps needed.”
- Tools still keep a **hardcoded keyword-query fallback** string if the pack is missing — residual dual source of truth.
- `explore_genre` still has a **legacy substring OR** path when alias resolve returns empty ids — softer than gaps fail-closed.

**Recommendation while paused:** treat the package as a **prototype of Approach 1**, not as committed architecture. Decide keep / trim / revert before adding packs or consumers (see §6).

---

## 2. Problem statement

Hardcoded synonym islands (`_GENRE_ALIASES`, NL regex in the tool file, Chernobyl-shaped keyword/theme tuples, live-channel motif dicts) fail as a **platform** for Projectionist because:

1. **Ontology gaps are real.** TMDB movie genres ≠ TV genres (e.g. History → War & Politics; Sci-Fi ↔ Sci-Fi & Fantasy). Aliases alone are not enough — you need **crosswalk + optional keyword unions + theme filters**.
2. **Call sites multiply.** Gaps, `explore_genre`, MCP `find_collection_gaps`, library browse/facets, Live starter motifs, and curator NL all need the *same* meaning of “sci-fi” / “history miniseries” — copying dicts guarantees drift.
3. **NL intent ≠ ID resolution.** Remote chat models already emit tool args; they still pass sentence-shaped `query`, invent genres, or skip `tv_type` / `without_genres`. Server-side must **normalize and fail closed** on TMDB ids or rails lie (1.30.2 class bugs).
4. **Test-shaped shortcuts rot.** Regex and token packs tuned to one golden ask (“recent history miniseries that aren’t science-focused” / Chernobyl) do not generalize; every new motif becomes another special case in `__init__.py`.
5. **Homelab constraints.** Offline-ish, BYOP/Ollama optional, no cloud synonym service as a hard dependency. Correctness must not require a network model.

---

## 3. Success criteria

Any chosen approach should deliver:

| Criterion | Meaning |
|-----------|---------|
| **Scalable synonyms** | Add a synonym / crosswalk / pack without editing tool registry logic |
| **Fail-closed IDs** | Unresolved or ambiguous genre tokens → empty ids + candidates / clear note; **never** invent TMDB genre ids |
| **Reusable consumers** | Same resolver usable by gaps, MCP (via tools), `explore_genre`, Live motif expansion, and (later) library facet browse — not N private dicts |
| **No test-shaped shortcuts** | Golden chats are regression tests; production rules are data or a validated model schema, not one-off Chernobyl lists in Python |
| **NL honesty** | Descriptive asks clear sentence-as-`search_tv`; structured `genres` / `tv_type` / `without_genres` / `year_from` win |
| **Ship decoupling** | 1.30.2 gap-rail correctness remains shippable if the platform is frozen mid-decision |

---

## 4. Survey — synonym / shortcut sites still outside the WIP

*Inventory only — do not “fix” these as part of this pause.*

| Site | Behavior today | Notes |
|------|----------------|-------|
| **MCP `find_collection_gaps`** | Thin pass-through to agent tool args | Benefits from whatever gaps uses; **no** independent alias layer or NL augment unless tool does it |
| **`explore_genre`** | Uses shared `resolve_genre_ids` + `normalize_tv_type` in WIP; **legacy substring OR** if resolve empty | Owned-library side still filters via `LibraryFilters.genres` substring |
| **Library query / browse** | `lower(genres) LIKE %token%` on JSON genre strings | No TV↔movie crosswalk; “Science” may miss “Science Fiction” depending on stored labels |
| **Library facet catalog** (`library/facets.py`) | Indexed facet values as stored (director/actor/keyword/motif/…) | Synonym expansion would change chip/browse UX — separate product choice |
| **Explore UI facet wall** | Exact genre query param → library filter | Same as library substring semantics |
| **Live channels** | Motif expansions moved to registry in WIP; recipes/starters may still carry free-text hints | Only `_recipe_search_terms` hooked |
| **Taste / persona / presets** | Copy and cluster tags use colloquial “sci-fi” etc. | UX language, not TMDB id resolve — optional later consumer |
| **Youth rating aliases** | Separate safety map | **Out of scope** for facet ontology |
| **Remote chat model tool-calling** | Already maps NL → tool JSON | Insufficient alone for gaps (see §5.5) |

---

## 5. Approaches (options)

### Approach 1 — Packaged facet registry

**Idea:** JSON/YAML packs (aliases, TV↔movie remaps, keyword unions, motif expansions, NL intent rules). Code is a thin resolver against live TMDB genre lists. **Closest to current WIP.**

| Pros | Cons |
|------|------|
| Deterministic, offline, fast, easy to unit-test | Pack maintenance becomes product work; risk of Chernobyl-in-JSON |
| Matches homelab “no cloud required” | Intent regex still brittle for open-ended NL |
| DATA_DIR / env overlay for owner tuning | Incomplete consumer migration leaves dual semantics |
| Clear fail-closed path already sketched | Seed sprawl without curation process |

**Fit:** Strong default for **ontology + id resolve**. Weak alone for open descriptive NL beyond a small rule set.

---

### Approach 2 — TMDB-authoritative + minimal glue

**Idea:** Resolve primarily against live `genre_list_{movies,tv}` (exact + unique substring). Generate/refresh a **minimal alias seed** from TMDB names (and maybe common abbreviations). Packs **only** for true ontology gaps (History on TV, keyword union for Drama-tagged history).

| Pros | Cons |
|------|------|
| Less hand-authored synonym surface | Still needs packs for History/Chernobyl-class gaps |
| Stays honest when TMDB renames genres | Substring ambiguity (“Act”) needs the same fail-closed UX |
| Shrinks WIP seed toward “glue only” | Does not solve descriptive NL intent by itself |

**Fit:** Good **discipline layer** on top of Approach 1 (or a trim of the current seed). Not a full NL platform.

---

### Approach 3 — Local small model (NL → structured discover args)

**Idea:** When a descriptive ask is detected, call Ollama / local BYOP with a **strict JSON schema** → `{genres, without_genres, tv_type, year_from, media_type, query?}`. A **deterministic resolver** still validates every genre token against live TMDB ids (fail closed). Packs optional for keyword unions after structured args exist.

| Topic | Notes |
|-------|--------|
| **Latency** | Extra 200ms–several seconds per gaps call; must not block non-descriptive title needles |
| **Offline** | Works when Ollama is up; must **degrade** to deterministic intent/registry if model unavailable |
| **Prompt schema** | Enumerated allowed genre **names** from the live list for the media type; forbid free ids; require empty query when filters present |
| **Hallucination controls** | Schema validate → `resolve_genre_ids` → drop unresolved; never trust model-emitted numeric genre ids; cap tool rounds already exist |
| **Ops** | Model pin, cold-start, RAM on Unraid — product/support cost |

**Fit:** Best for **open NL phrasing**. Wrong as the sole source of truth for ids. Optional dependency conflicts with “gaps work without LLM” unless carefully gated.

---

### Approach 4 — Hybrid (recommended default lean)

**Idea:**

1. **Registry (Approach 1 trimmed by Approach 2)** owns ontology: aliases, crosswalk, facet packs (keyword/theme), tv_types, motif expansions.
2. **Deterministic intent** (current `intent.py` rules) handles the small high-value NL patterns and descriptive-ask clearing — enough for 1.30.2-class asks.
3. **Optional local model** only when: descriptive-ask heuristic fires **and** structured fields are still incomplete **and** Ollama/BYOP is configured — output still passes through fail-closed resolve.
4. **Remote chat model** continues to choose tools and prose; it must **not** be the only place synonym correctness lives.

| Pros | Cons |
|------|------|
| Correctness offline via registry | Two NL paths (rules + optional model) need clear precedence |
| Room to grow NL without packing every phrase into JSON | Implementation complexity if model path ships too early |
| Aligns with existing BYOP/Ollama story | Needs explicit “model off = rules only” contract |

---

### 5.5 Optional note — remote chat model already emits tool args

**Why that failed for gaps:** models often put the whole user sentence in `query`, omit `tv_type` / `without_genres`, or use colloquial genre labels. `search_tv(query=sentence)` ignores discover constraints and yields **wrong TMDB ids** on rails (the 1.30.2 bug class).

**What must stay server-side regardless of approach:**

- Live TMDB genre-list resolution (fail closed / ambiguous candidates)
- Descriptive-ask clearing of sentence-as-search when structured filters exist
- TV History (and similar) keyword-union + theme filter when genre ontology is insufficient
- Youth / privacy / queue filters on emitted cards

Remote tool-calling remains a **UX accelerator**, not the synonym platform.

---

## 6. Recommendation

**Default: Hybrid, registry-first (Approach 4), with Approach 2 as seed discipline.**

Rationale:

- The WIP already proves a thin resolver + JSON packs can delete hundreds of lines from `agent/tools/__init__.py` without losing fail-closed behavior.
- Homelab reality: many installs have no local model; gaps must stay correct with **rules + packs alone**.
- Local model is a **later optional upgrade** for long-tail NL — not a blocker for freezing 1.30.2 and not a reason to discard the registry.
- Trim the seed toward “TMDB glue + proven ontology gaps” so packs do not become a junk drawer.

**Do not** choose pure Approach 3 as the platform. **Do not** expand packs/consumers until §8 open decisions are answered.

---

## 7. What to keep vs revert from current WIP (while deciding)

### Keep (low regret if Approach 1/4 wins)

- `projectionist/facets/{registry,resolve,intent}.py` shape and fail-closed `resolve_genre_ids`
- Package-data wiring in `pyproject.toml`
- `tests/test_facets_registry.py` as the contract for aliases / packs / intent
- Hooks in gaps + live motif expansion **if** 1.30.2 tests still pass against this tree
- DATA_DIR / `PROJECTIONIST_FACET_ALIASES` overlay concept

### Trim or freeze (do not grow)

- Extra seed aliases not required by shipped gap/explore/live tests (anime, cyberpunk, rom-com, …) — either justify with tests or defer
- New facet packs beyond `history_tv`
- New consumers (library SQL, Explore chips, MCP-side NL) — wait for decision
- Further “helpful” motif_search_aliases expansion

### Revert / peel off if owner wants a clean 1.30.2-only tree

- Entire `projectionist/facets/` + test file + pyproject package-data, **restoring** the previous inlined helpers in `agent/tools/__init__.py` and motif dict in `publish.py`
- Keep unrelated saved-library sanitize tests / release-notes if those are desired independently

### Explicit freeze

- **Ship 1.30.2 gap-rail correctness independently** of finishing the alias platform. If the facets WIP is messy for release, prefer **revert facets + keep gap behavior from `88c9eb1`**, rather than blocking the release on architecture.

---

## 8. Open decisions for the owner

- Keep the uncommitted `facets/` WIP as the Approach 1 prototype, trim the seed, or fully revert to pre-facets helpers for a clean 1.30.2 tree?
- Is **local-model NL parse** in-scope for the next minor, a later experiment, or out until BYOP UX exists?
- Should **library browse / Explore genre chips** share TMDB-style aliases, or stay “as stored on items” forever?
- Who owns pack curation (maintainer seed vs owner DATA_DIR overlay vs both), and what is the bar for adding a new `facet_packs` entry?
- Is MCP allowed to depend only on the agent tool (status quo), or should MCP document/guarantee the same NL augment semantics?
- Acceptance bar: “registry-first hybrid” vs “TMDB-minimal glue only until a second ontology pack is proven”?

---

## 9. Out of scope for this document

- Task-by-task implementation plan, file-level TDD steps, or commits
- Migrating library SQL / Explore / taste clusters
- Deploy, Tunarr, or unrelated Live roadmap work
- Expanding Chernobyl/history packs “while we’re here”

---

## 10. Next step after owner decision

1. Owner answers §8 (especially keep/trim/revert + local-model timing).
2. Write a **short** locked design note under `docs/superpowers/specs/` if the choice is non-obvious.
3. Only then write a **task-by-task** implementation plan (writing-plans style) — or a minimal “trim WIP + freeze” plan if registry-first is accepted without model work.

**Until then: no more facets expansion.**
