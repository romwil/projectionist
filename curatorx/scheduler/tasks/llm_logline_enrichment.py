"""Optional idle trickle: fill ``llm_logline`` when an LLM is configured.

``llm_logline`` is a short narrative one-liner used in layered embedding text.
It stays empty unless ``settings.llm_api_key`` is set — we never invent plot
text from heuristics.  Homelab installs without an LLM skip this task cleanly.

Batch size is intentionally tiny (default 5) to avoid burning API credits.

Default interval: 24 hours.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Callable, Dict

from curatorx.config_store import Settings
from curatorx.library.db import Database
from curatorx.scheduler.engine import IdleScheduler, TaskDefinition

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 86400  # 24 hours
DEFAULT_BATCH_SIZE = 5
REQUEST_PAUSE_SECONDS = 1.0
_MAX_LOGLINE_CHARS = 180


def _clean_logline(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip().strip('"').strip("'")
    if not cleaned:
        return ""
    # Drop leading labels models sometimes emit.
    cleaned = re.sub(r"^(logline|one[- ]liner)\s*:\s*", "", cleaned, flags=re.I).strip()
    if len(cleaned) > _MAX_LOGLINE_CHARS:
        cleaned = cleaned[: _MAX_LOGLINE_CHARS - 1].rstrip() + "…"
    return cleaned


async def _generate_logline(settings: Settings, *, title: str, year: Any, plot: str) -> str:
    from curatorx.agent.providers import get_chat_provider

    provider = get_chat_provider(settings)
    year_bit = f" ({year})" if year else ""
    messages = [
        {
            "role": "system",
            "content": (
                "Write a single vivid logline (one sentence, under 40 words) for the film or "
                "TV show. No spoilers beyond the premise. Reply with the logline only."
            ),
        },
        {
            "role": "user",
            "content": f"Title: {title}{year_bit}\n\nPlot material:\n{plot}",
        },
    ]
    response = await provider.chat(messages)
    content = ""
    if isinstance(response, dict):
        content = str(response.get("content") or "")
        if not content:
            # OpenAI-style fallback shape if a provider returns raw choices.
            choices = response.get("choices") or []
            if choices and isinstance(choices[0], dict):
                msg = choices[0].get("message") or {}
                content = str(msg.get("content") or "")
    return _clean_logline(content)


async def run(
    db: Database, settings: Settings, should_stop: Callable[[], bool]
) -> Dict[str, Any]:
    """Enrich empty ``llm_logline`` rows when an LLM API key is configured.

    Without ``llm_api_key``, returns ``skipped`` and leaves the column empty.
    """
    if should_stop():
        return {"status": "interrupted", "enriched": 0}

    if not (settings.llm_api_key or "").strip():
        return {
            "status": "skipped",
            "reason": "no_llm_api_key",
            "enriched": 0,
            "note": "llm_logline stays empty until an LLM is configured",
        }

    backlog = db.items_needing_llm_logline(limit=DEFAULT_BATCH_SIZE)
    if not backlog:
        return {"status": "completed", "enriched": 0, "remaining": 0}

    enriched = 0
    errors = 0
    for idx, row in enumerate(backlog):
        if should_stop():
            return {"status": "interrupted", "enriched": enriched, "errors": errors}

        plot = "\n".join(
            part
            for part in [
                str(row["summary"] or "").strip(),
                str(row["tmdb_overview"] or "").strip(),
                str(row["tagline"] or "").strip(),
            ]
            if part
        )
        if not plot:
            continue

        try:
            logline = await _generate_logline(
                settings,
                title=str(row["title"] or ""),
                year=row["year"],
                plot=plot,
            )
        except Exception as error:
            errors += 1
            logger.debug(
                "LLM logline failed for id=%s: %s",
                row["id"],
                error,
            )
            await asyncio.sleep(REQUEST_PAUSE_SECONDS)
            continue

        if logline:
            db.set_llm_logline(int(row["id"]), logline)
            enriched += 1

        if idx + 1 < len(backlog):
            await asyncio.sleep(REQUEST_PAUSE_SECONDS)

    remaining = len(db.items_needing_llm_logline(limit=1))
    logger.info(
        "LLM logline trickle: enriched=%s errors=%s remaining_sample=%s",
        enriched,
        errors,
        remaining,
    )
    return {
        "status": "completed",
        "enriched": enriched,
        "errors": errors,
        "batch_size": DEFAULT_BATCH_SIZE,
        "has_more": remaining > 0,
    }


def register(scheduler: IdleScheduler) -> None:
    scheduler.register(
        TaskDefinition(
            name="llm_logline_enrichment",
            run_interval_seconds=INTERVAL_SECONDS,
            enabled=True,
            run_fn=run,
            description=(
                "When an LLM API key is configured, writes short narrative loglines used "
                f"in embedding text. Processes about {DEFAULT_BATCH_SIZE} titles per run; "
                "skips cleanly when no LLM is configured."
            ),
            items_per_cycle=DEFAULT_BATCH_SIZE,
            progress_scope="llm_logline_backlog",
        )
    )
