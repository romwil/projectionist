# Unified Closed-Loop Augmentation Engine

**Status:** Accepted parent architecture — Phases 0–C (P2 pilot) landed; Phase D deferred  
**Date:** 2026-08-01  
**Document ID:** SPEC-2026-AUG-001  
**Audience:** Developers / Cursor agents  
**Locked plan:** Cursor plan `facet_taxonomy_architecture_7186fdb9` (Unified Closed-Loop Knowledge + Facet Hot Path)

**Supersedes / amends:**

| Prior doc | Disposition |
|-----------|-------------|
| [`revised-larger-scope-knowledge-model.md`](../plans/revised-larger-scope-knowledge-model.md) | **Accepted with amendments** (below) |
| [`proposed-plan-for-consideration-in-re-facet-alias-architecture.md`](../plans/proposed-plan-for-consideration-in-re-facet-alias-architecture.md) | **Subsumed** — observe/stage/promote ideas live here; facet-only SQLite + auto-merge JSON retired |
| [`2026-08-01-facet-alias-architecture.md`](../plans/2026-08-01-facet-alias-architecture.md) | Freeze lifted for Phase 0–B; **Phase D remains deferred** (library chips, local-model NL, bulk IdleScheduler migration) |

---

## 1. Purpose

Projectionist grows a fleet of IdleScheduler jobs (enrichment, vectors, motifs, digests). Rather than one-off tables and JSON candidate files per domain, the parent architecture is a single closed loop:

**observe → audit → stage → promote**, with a four-tier severity model governing *when* workers run relative to idle windows.

The live request path stays **zero-latency** and **fail-closed**. Telemetry never blocks API/MCP responses. Facet taxonomy audit is the **first P1 specialization** of this engine — not the whole program.

---

## 2. Locked amendments (bind over the revised draft)

| Revised draft | Locked amendment |
|---------------|------------------|
| `confidence >= 0.90` → `commit_direct` for all tasks | **Taxonomy / P1 never auto-commits** into runtime alias seed. Stage only → Admin approve → `DATA_DIR` overlay. `commit_direct` allowed later only for **P2/P3** item-graph fields that already have safe idempotent writers (and still prefer stage until pilots prove confidence). |
| Flat task list “ready now” | **Phase A hot path first** (layered facets + consumer parity). Telemetry schema can land early; do not scale audit/Admin until resolve contract is unified. |
| Refactor entity_memory + plot_neighbors in same wave | **Pilot after** facet P1 loop is green — not a big-bang rewrite of all `register_all` tasks. |
| P0 “immediate bypass batch windows” | Compose with existing `IdleScheduler` — P0 = high-priority / short-interval `TaskDefinition`, not a second ad-hoc runner. |
| Baked TMDB genre IDs in taxonomy JSON | Seed stores **names/aliases/packs**; discover IDs from **live** genre lists. |

---

## 3. Severity matrix → IdleScheduler

| Tier | Role | Scheduler composition |
|------|------|------------------------|
| **P0** | Critical ID / execution-block repair | Elevated: short `run_interval_seconds` via `severity_task_definition("P0", …)` |
| **P1** | Taxonomy & facet misses | Scheduled audit when aggregated `hit_count` warrants; **stage only** |
| **P2** | Missing item metadata (demand-driven) | Normal idle intervals; prefer stage; `commit_direct` only with explicit opt-in + safe writer |
| **P3** | Cosmetic / deep-idle cleanup | Long interval (deep idle only) |

Helpers live in `projectionist/scheduler/tasks/base_augmentation.py` (`INTERVAL_BY_SEVERITY`, `severity_task_definition`). Existing tasks are **not** rewritten onto the base class in Phase 0.

---

## 4. Schema (library DB)

Migration creates two tables (distinct from the existing interaction stream `system_telemetry_stream`):

### `telemetry_events`

Unified high-throughput miss / demand buffer. Unique on `(event_type, entity_type, entity_key)` with `hit_count` increments on conflict.

### `staged_augmentations`

Candidate enrichments awaiting Admin promote/reject (or future auto-promote for proven P2/P3 writers only).

See migration `closed_loop_augmentation` and `TelemetryConfigMixin` helpers (`upsert_closed_loop_event`, `insert_staged_augmentation`, …).

---

## 5. Ingestion contract

Package entry: `projectionist/telemetry/ingestion.py`.

- Closed-loop upserts are **fire-and-forget** (`asyncio.to_thread` when a loop is running; daemon thread fallback otherwise).
- Never block the request path; never raise into callers on write failure.
- **Never print secrets.** Payloads are scrubbed of credential-like keys before persistence; logs mention event type / entity type only.
- Orthogonal to `TelemetryIngester` → `system_telemetry_stream` (chat/playback/LLM BI). Do not conflate the two tables.

Phase B wiring: `resolve_genre_ids` schedules P1 misses via `facets.closed_loop.schedule_unmapped_facet_tokens` → `schedule_closed_loop_event(…, event_type="unmapped_token", priority_tier="P1", entity_type="facet", …)` (fire-and-forget; Database bound at web startup).

---

## 6. `BaseAugmentationTask` lifecycle

`projectionist/scheduler/tasks/base_augmentation.py`:

1. `fetch_telemetry_signals` — domain query of `telemetry_events`
2. `process_signal` — return candidate payload + `confidence` or `None`
3. Route by confidence **and** tier:
   - `confidence >= 0.90` and `_may_commit_direct()` → `commit_direct` (P2/P3 opt-in only)
   - else `confidence >= 0.60` → `stage_candidate` (includes all high-confidence **P1**)
   - else skip
4. Default: `enable_direct_commit = False`. P1 always stages.

---

## 7. Phased delivery

| Phase | Scope | Owner of this wave |
|-------|--------|--------------------|
| **0** | Schema + ingestion + `BaseAugmentationTask` + unit tests | Landed |
| **A** | Layered facets hot path; unify gaps / explore / motifs; kill dual SoT | Landed |
| **B** | `FacetTaxonomyAudit(BaseAugmentationTask)` + Admin stage → overlay | Landed |
| **C** | Limited P2 pilot (`entity_memory_enrichment` + demand telemetry) | **Landed** (see below) |
| **D** | Library chips, local-model NL, broad task migration | **Deferred** (see below) |

### Phase C — P2 pilot (landed)

Limited scope — **not** a fleet rewrite:

- Emit: `schedule_metadata_demand` (`event_type=metadata_demand`, tier **P2**) from `recall_repo_memory` when a snapshot is missing, sparse, or stale (fire-and-forget; same Database bind as facet closed-loop).
- Consume: `entity_memory_enrichment` composes `EntityMemoryDemandPilot(BaseAugmentationTask)` to **stage** high-hit demand in `staged_augmentations` (`enable_direct_commit=False`), then prioritizes demand-signaled entities before the stale backlog and refreshes via existing idempotent `research_*` writers (not confidence-gated `commit_direct`).
- **Not in this pilot:** `plot_neighbors` rejection → telemetry / edge-penalty rewrite (no clear low-risk rejection hook; deferred with Phase D bulk migration). Taxonomy / P1 auto-commit remains off.

### Phase D — explicitly deferred

These remain out of scope until pilots prove the closed loop:

- **Library / Explore chip synonym** product decision (which chips surface aliases)
- **Optional local-model NL** off the hot path
- **Bulk IdleScheduler migration** of remaining tasks onto `BaseAugmentationTask` (after Phase C pilots)
- **`plot_neighbors` rejection signals** / vector edge-penalty adjustment

**Parallel (not this architecture):** root-cause QA major `gap-history-miniseries-mismatch` on `:8790`.

---

## 8. Facet specialization addendum

Facet taxonomy is the first **P1** closed-loop specialization on a **registry-first hybrid** hot path.

### Hot path (Phase A — sibling)

- Layered seed under `projectionist/facets/`: concepts / aliases / packs
- Fail-closed resolve; live TMDB name→id (no baked genre IDs in seed)
- Consumers before telemetry scale: gaps, `explore_genre` (no soft substring OR), live motifs
- NL intent retained; dual sources of truth deleted

### Cold path (Phase B — landed)

- Misses → `telemetry_events` (`unmapped_token` / `entity_type=facet`) asynchronously from resolve
- `FacetTaxonomyAudit` (`projectionist/scheduler/tasks/facet_taxonomy_audit.py`) inherits `BaseAugmentationTask`; outputs **`staged_augmentations` only** (no auto-promote into seed)
- Admin **Taxonomy** (`/admin/taxonomy`): approve/reject → `$DATA_DIR/taxonomy.json` overlay via `facets.overlay.promote_facet_alias_to_overlay`; boot merge into in-memory registry
- Acceptance: resolve stays fast; 0ms blocking telemetry; overlay persists across upgrades; packaged seed never rewritten

### Explicitly out of Phase 0–C

- Taxonomy auto-merge into packaged / image seed
- Big-bang IdleScheduler rewrite (Phase D)
- `plot_neighbors` rejection / edge-penalty closed loop (deferred)

---

## 9. Ranking (program level)

1. Closed-loop engine (this spec)  
2. Hybrid registry-first hot path  
3. Facet Taxonomy Audit as P1 task  
4. P2/P3 task migration after P1 pilot  
5. Local-model NL (optional, off hot path, deferred)
