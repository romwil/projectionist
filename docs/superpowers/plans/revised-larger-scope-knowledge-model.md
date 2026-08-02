
# Technical Specification: Unified Closed-Loop Augmentation Engine

**Document ID:** SPEC-2026-AUG-001

**Target Package:** `projectionist/telemetry/` & `projectionist/scheduler/tasks/`

**Operational Status:** Accepted with amendments — see locked parent spec  
[`docs/superpowers/specs/2026-08-01-closed-loop-augmentation.md`](../specs/2026-08-01-closed-loop-augmentation.md)  
(Cursor plan `facet_taxonomy_architecture_7186fdb9`). Key amendments: P1/taxonomy never auto-commits; Phase A hot path before telemetry scale; IdleScheduler composition for P0; no big-bang task rewrite.

---

## 1. Executive Summary

This specification defines the architecture for Projectionist’s closed-loop, telemetry-driven background knowledge augmentation engine.

By replacing static, open-loop scheduled scripts with a feedback subsystem, Projectionist observes live query misses and user interaction signals, prioritizes knowledge gaps using a strict four-tier severity model, and stages candidate data enrichments for automated or administrative promotion. The live execution path remains zero-latency, deterministic, and strictly fail-closed.

---

## 2. Core Architectural Principles

* **Zero-Latency Execution:** Live API, search, and MCP endpoints execute using in-memory datasets and local indexes. Telemetry events write asynchronously via `asyncio.to_thread` to eliminate request blocking.
* **Fail-Closed Resolution:** Unresolved or ambiguous entity tokens return candidate suggestions and empty ID sets. Unresolved strings are never injected into external search APIs.
* **Strict Prioritization:** Background tasks execute based on a 4-Tier Severity Model, prioritizing critical data corruption and execution blocks over cosmetic metadata additions.
* **Observe $\rightarrow$ Audit $\rightarrow$ Stage $\rightarrow$ Promote:** All background tasks consume events from a unified telemetry queue and output candidates to a staging buffer before committing changes to the primary library graph.

---

## 3. Severity Tiering & Prioritization Matrix

The engine categorizes all metadata gaps and runtime anomalies into four explicit priority tiers to govern worker execution queues:

```
+-----------------------------------------------------------------------+
|                 Augmentation Prioritization Hierarchy                |
|                                                                       |
|  [ P0: CRITICAL KNOWLEDGE GAPS ]  --> Unresolved IDs / Execution Block|
|  [ P1: TAXONOMY & FACET MISSES ]  --> Unmapped Genres / Motif Drift   |
|  [ P2: MISSING ITEM METADATA   ]  --> Missing Posters / Empty Plot    |
|  [ P3: COSMETIC & STYLISTIC    ]  --> Tag casing / Minor Synopses    |
+-----------------------------------------------------------------------+

```

| Tier | Category | Description | Execution Strategy |
| --- | --- | --- | --- |
| **P0** | **Critical Knowledge Gap** | Missing or corrupted structural identifiers required for core filtering or API execution (e.g., missing TMDB ID crosswalks, broken LSC_ID mappings). | Immediate execution block; bypasses batch windows to dispatch background workers immediately. |
| **P1** | **Taxonomy & Facet Miss** | High-frequency natural language search terms or colloquialisms that fail to map to the canonical taxonomy schema. | Aggregated into telemetry buffers; processed during scheduled audit runs when `hit_count >= 5`. |
| **P2** | **Missing Item Metadata** | Library entities with sparse metadata (e.g., missing synopses, un-indexed directors, or missing poster assets). | Demand-driven queue calculated via $\text{Priority} = \text{View Frequency} \times \text{Metadata Sparsity}$. |
| **P3** | **Cosmetic & Stylistic** | Low-impact anomalies such as tag casing inconsistencies, redundant keyword duplicates, or low-confidence motif expansions. | Batch cleanup executed exclusively during deep system idle windows. |

---

## 4. Unified Data Schema

### A. Unified Telemetry Table (`telemetry_events`)

Replaces ad-hoc logging tables with a single, high-throughput SQLite event buffer inside `projectionist.db`.

```sql
CREATE TABLE IF NOT EXISTS telemetry_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,       -- "unmapped_token", "implicit_rejection", "search_miss"
    priority_tier TEXT NOT NULL,    -- "P0", "P1", "P2", "P3"
    entity_type TEXT NOT NULL,      -- "facet", "title", "person", "vector"
    entity_key TEXT NOT NULL,       -- Raw query string or entity identifier
    payload_json TEXT,              -- Serialized JSON context
    hit_count INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_event_entity UNIQUE (event_type, entity_type, entity_key)
);

CREATE INDEX IF NOT EXISTS idx_telemetry_priority ON telemetry_events(priority_tier, hit_count DESC);
CREATE INDEX IF NOT EXISTS idx_telemetry_updated ON telemetry_events(updated_at DESC);

```

### B. Universal Staging Table (`staged_augmentations`)

Holds candidate enrichments generated by background workers prior to promotion.

```sql
CREATE TABLE IF NOT EXISTS staged_augmentations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_name TEXT NOT NULL,
    priority_tier TEXT NOT NULL,
    target_entity_type TEXT NOT NULL,
    target_entity_id TEXT NOT NULL,
    candidate_data_json TEXT NOT NULL,
    confidence_score REAL NOT NULL,
    status TEXT DEFAULT 'pending',   -- "pending", "approved", "rejected", "auto_promoted"
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_staged_status_conf ON staged_augmentations(status, confidence_score DESC);

```

---

## 5. Universal Base Task (`BaseAugmentationTask`)

All background enrichment jobs in `projectionist/scheduler/tasks/` must inherit from `BaseAugmentationTask` to enforce standard signal fetching, processing, and staging behaviors.

```python
# projectionist/scheduler/tasks/base_augmentation.py
import abc
import json
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

class BaseAugmentationTask(abc.ABC):
    """Universal base class for closed-loop scheduled enrichment tasks."""

    def __init__(self, db_conn: Any, task_name: str, target_priority: str):
        self.db = db_conn
        self.task_name = task_name
        self.target_priority = target_priority

    @abc.abstractmethod
    async def fetch_telemetry_signals(self) -> List[Dict[str, Any]]:
        """Query telemetry_events for actionable signals assigned to this task's domain."""
        pass

    @abc.abstractmethod
    async def process_signal(self, signal: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Process an individual telemetry signal.
        
        Returns a dictionary payload containing:
          - target_entity_type: str
          - target_entity_id: str
          - candidate_data: dict
          - confidence: float (0.0 to 1.0)
        """
        pass

    @abc.abstractmethod
    async def commit_direct(self, payload: Dict[str, Any]) -> None:
        """Apply high-confidence updates directly to the primary database graph."""
        pass

    async def stage_candidate(self, payload: Dict[str, Any]) -> None:
        """Persist low-to-mid confidence candidates to staged_augmentations."""
        query = """
        INSERT INTO staged_augmentations 
        (task_name, priority_tier, target_entity_type, target_entity_id, candidate_data_json, confidence_score)
        VALUES (:task_name, :priority, :entity_type, :entity_id, :candidate_json, :confidence)
        """
        params = {
            "task_name": self.task_name,
            "priority": self.target_priority,
            "entity_type": payload["target_entity_type"],
            "entity_id": str(payload["target_entity_id"]),
            "candidate_json": json.dumps(payload["candidate_data"]),
            "confidence": payload["confidence"],
        }
        await self.db.execute(query, params)

    async def execute_run(self) -> Dict[str, int]:
        """Executes the full signal processing lifecycle."""
        signals = await self.fetch_telemetry_signals()
        stats = {"processed": 0, "direct_commits": 0, "staged": 0, "errors": 0}

        for signal in signals:
            stats["processed"] += 1
            try:
                outcome = await self.process_signal(signal)
                if not outcome:
                    continue

                confidence = outcome.get("confidence", 0.0)
                if confidence >= 0.90:
                    await self.commit_direct(outcome)
                    stats["direct_commits"] += 1
                elif confidence >= 0.60:
                    await self.stage_candidate(outcome)
                    stats["staged"] += 1

            except Exception as err:
                stats["errors"] += 1
                logger.error(f"[{self.task_name}] Signal processing failed for ID {signal.get('id')}: {err}")

        return stats

```

---

## 6. Implementation Tasks for Cursor

```
[ ] Task 1: Database Migration & Schema Creation
    - Add telemetry_events and staged_augmentations tables to projectionist/library/db/migrations.py.
    - Add helper functions for fire-and-forget telemetry logging in projectionist/telemetry/ingestion.py.

[ ] Task 2: Base Augmentation Framework
    - Create projectionist/scheduler/tasks/base_augmentation.py implementing BaseAugmentationTask.
    - Write unit tests in tests/test_base_augmentation.py verifying confidence threshold routing.

[ ] Task 3: Refactor Facet Taxonomy Audit
    - Refactor projectionist/scheduler/tasks/facet_taxonomy_audit.py to inherit from BaseAugmentationTask.
    - Wire telemetry logging inside resolve_genre_ids to push P1 misses to telemetry_events.

[ ] Task 4: Refactor Entity Memory & Vector Tasks
    - Update entity_memory_enrichment.py to query telemetry_events for P2 demand signals.
    - Update plot_neighbors.py to adjust vector edge penalties based on rejection events.

```
