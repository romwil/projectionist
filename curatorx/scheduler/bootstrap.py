"""First-start sequencing for foundational idle knowledge tasks.

Fresh installs should not wait days for motif / theme / synopsis coverage.
On IdleScheduler start, if foundational tasks have never run, enqueue them in a
fixed order and execute one-by-one (not a parallel firehose). Progress is
persisted so restarts resume the queue instead of looping forever.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, Sequence

from curatorx.config_store import Settings, load_merged_settings
from curatorx.library.db import Database
from curatorx.scheduler.engine import IdleScheduler, TaskState
from curatorx.scheduler.tasks.long_synopsis_enrichment import resolve_synopsis_source

logger = logging.getLogger(__name__)

BOOTSTRAP_COMPLETED_KEY = "idle_bootstrap_completed"
BOOTSTRAP_QUEUE_KEY = "idle_bootstrap_queue"
BOOTSTRAP_INTER_TASK_DELAY_SECONDS = 2.0

# Ordered once-through sequence. Conditional skips happen in select_bootstrap_tasks.
FOUNDATIONAL_SEQUENCE: tuple[str, ...] = (
    "metadata_enrichment",
    "summary_motifs",
    "keyword_theme_tagging",
    "long_synopsis_enrichment",
    "semantic_embeddings",
)


def _never_run(states_by_name: Dict[str, TaskState], name: str) -> bool:
    state = states_by_name.get(name)
    return state is None or state.last_run_at is None


def select_bootstrap_tasks(
    db: Database,
    settings: Settings,
    states: Sequence[TaskState],
) -> List[str]:
    """Return foundational tasks that should run once on first boot.

    Selection rules:
    - ``metadata_enrichment`` — never run **and** metadata backlog > 0
    - ``summary_motifs`` — never run (full library motif rebuild)
    - ``keyword_theme_tagging`` — never run
    - ``long_synopsis_enrichment`` — never run **and** synopsis source enabled
    - ``semantic_embeddings`` — never run **and** zero stored embeddings **and**
      at least one title still needs an embedding (avoids stampeding when already warm)
    """
    states_by_name = {s.name: s for s in states}
    selected: List[str] = []

    if _never_run(states_by_name, "metadata_enrichment"):
        try:
            backlog = db.count_items_needing_metadata_enrichment()
        except Exception:  # noqa: BLE001
            backlog = 0
        if backlog > 0:
            selected.append("metadata_enrichment")

    if _never_run(states_by_name, "summary_motifs"):
        selected.append("summary_motifs")

    if _never_run(states_by_name, "keyword_theme_tagging"):
        selected.append("keyword_theme_tagging")

    if _never_run(states_by_name, "long_synopsis_enrichment"):
        source, skip_reason = resolve_synopsis_source(settings)
        if source and not skip_reason:
            selected.append("long_synopsis_enrichment")

    if _never_run(states_by_name, "semantic_embeddings"):
        try:
            has_embeddings = db.count_embeddings() > 0
            needs_embeddings = db.count_items_needing_embeddings() > 0
        except Exception:  # noqa: BLE001
            has_embeddings = True
            needs_embeddings = False
        if not has_embeddings and needs_embeddings:
            selected.append("semantic_embeddings")

    # Preserve canonical order even if callers reorder later.
    order = {name: idx for idx, name in enumerate(FOUNDATIONAL_SEQUENCE)}
    selected.sort(key=lambda name: order.get(name, 999))
    return selected


def _load_queue(db: Database) -> Optional[List[str]]:
    raw = db.get_config(BOOTSTRAP_QUEUE_KEY)
    if raw is None or str(raw).strip() == "":
        return None
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(data, list):
        return None
    return [str(item) for item in data if str(item).strip()]


def _save_queue(db: Database, queue: List[str]) -> None:
    db.set_config(BOOTSTRAP_QUEUE_KEY, json.dumps(queue))


def _mark_completed(db: Database) -> None:
    db.set_config(BOOTSTRAP_COMPLETED_KEY, "1")
    db.set_config(BOOTSTRAP_QUEUE_KEY, "[]")


def is_bootstrap_completed(db: Database) -> bool:
    return str(db.get_config(BOOTSTRAP_COMPLETED_KEY) or "").strip() == "1"


async def run_idle_bootstrap(scheduler: IdleScheduler) -> Dict[str, Any]:
    """Run (or resume) the one-shot first-start idle bootstrap sequence.

    Uses ``force=True`` / trigger ``bootstrap`` so work is not blocked on the
    idle threshold. Tasks still run strictly one at a time.
    """
    db = scheduler._db
    if is_bootstrap_completed(db):
        return {"status": "already_completed", "tasks": []}

    queue = _load_queue(db)
    if queue is None:
        settings = load_merged_settings(scheduler._data_dir)
        states = scheduler._load_all_states()
        queue = select_bootstrap_tasks(db, settings, states)
        if not queue:
            logger.info(
                "bootstrap: nothing to run (foundational tasks already ran or not needed); "
                "marking idle_bootstrap_completed"
            )
            _mark_completed(db)
            return {"status": "completed", "tasks": [], "remaining": []}
        _save_queue(db, queue)
        logger.info("bootstrap: selected sequence %s", queue)

    ran: List[str] = []
    remaining = list(queue)
    for name in list(remaining):
        if scheduler._shutdown:
            logger.info("bootstrap: interrupted; remaining=%s", remaining)
            break

        defn = scheduler._definitions.get(name)
        if defn is None or defn.run_fn is None:
            logger.warning("bootstrap: skipping unknown task %s", name)
            remaining.remove(name)
            _save_queue(db, remaining)
            continue

        while scheduler._busy_task_name() is not None and not scheduler._shutdown:
            await asyncio.sleep(0.25)
        if scheduler._shutdown:
            break

        # Admin history records trigger=bootstrap; logs carry the educational reason.
        logger.info("bootstrap: running %s because never run", name)
        try:
            result = await scheduler._execute_task(defn, force=True, trigger="bootstrap")
        except Exception:  # noqa: BLE001
            logger.exception("bootstrap: task %s failed; continuing sequence", name)
            result = {"status": "error"}

        remaining.remove(name)
        _save_queue(db, remaining)
        ran.append(name)
        logger.info(
            "bootstrap: finished %s status=%s remaining=%s",
            name,
            (result or {}).get("status"),
            remaining,
        )

        if remaining and not scheduler._shutdown:
            await asyncio.sleep(BOOTSTRAP_INTER_TASK_DELAY_SECONDS)

    if not remaining:
        _mark_completed(db)
        logger.info("bootstrap: completed sequence %s", ran)
        return {"status": "completed", "tasks": ran, "remaining": []}

    return {"status": "interrupted", "tasks": ran, "remaining": remaining}
