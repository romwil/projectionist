"""Human-readable scheduled-task outcome text for admin logs and API payloads."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

# Machine reason codes returned by task run_fn implementations.
SKIP_REASON_LABELS: Dict[str, str] = {
    "no_llm_api_key": "OpenAI/LLM API key not configured",
    "stub_pending": "Theme tagging is not implemented yet (stub task)",
    "no_tmdb_api_key": "TMDB API key not configured",
    "task_disabled": "Task is disabled",
    "already_running": "Another run is already in progress",
    "quarantined": "Task is quarantined after repeated failures",
    "need_at_least_two_embeddings": "Need at least two plot embeddings",
    "TMDB not configured": "TMDB API key not configured",
}

# Keys on task result dicts that are not surfaced as counters.
_RESERVED_RESULT_KEYS = frozenset(
    {
        "status",
        "reason",
        "note",
        "error",
        "date",
        "cursor",
        "batch_size",
        "has_more",
        "vacuumed",
        "pruned",
    }
)

# Preferred display order for known metric keys (others follow alphabetically).
_METRIC_ORDER: Tuple[str, ...] = (
    "enriched",
    "embedded",
    "processed",
    "tagged",
    "motifs",
    "caches_built",
    "collection",
    "neighbor",
    "shared_crew",
    "total",
    "found",
    "gaps_found",
    "directors_analyzed",
    "clusters_updated",
    "count",
    "total_pruned",
    "unique_items",
    "seeds",
    "errors",
    "skipped",
    "remaining",
    "library_size",
)

def _is_error_status(status: str) -> bool:
    """True when a run status represents failure (e.g. ``error``, ``error_timeout``)."""
    return str(status).startswith("error")


METRIC_LABELS: Dict[str, str] = {
    "enriched": "enriched",
    "errors": "errors",
    "embedded": "embedded",
    "skipped": "skipped",
    "total": "relations",
    "caches_built": "caches warmed",
    "library_size": "library items",
    "processed": "neighbor rows",
    "seeds": "seeds",
    "tagged": "tagged",
    "motifs": "motifs",
    "unique_items": "titles",
    "found": "matches",
    "gaps_found": "gaps",
    "directors_analyzed": "directors",
    "clusters_updated": "clusters",
    "count": "candidates",
    "total_pruned": "rows pruned",
    "collection": "collection links",
    "neighbor": "neighbor links",
    "shared_crew": "crew links",
    "remaining": "remaining",
}


def humanize_skip_reason(
    reason: Optional[str] = None,
    *,
    note: Optional[str] = None,
) -> str:
    """Turn a skip reason code (and optional note) into admin-facing text."""
    if note and str(note).strip():
        return str(note).strip()
    if not reason:
        return "Nothing to do or a precondition was not met"
    text = str(reason).strip()
    if text in SKIP_REASON_LABELS:
        return SKIP_REASON_LABELS[text]
    if " " in text:
        return text
    return text.replace("_", " ").strip().capitalize()


def _metric_label(key: str) -> str:
    if key in METRIC_LABELS:
        return METRIC_LABELS[key]
    return key.replace("_", " ")


def _format_metric_pair(key: str, value: Any) -> Optional[str]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return f"{value:,} {_metric_label(key)}"
    if isinstance(value, float) and value.is_integer():
        return f"{int(value):,} {_metric_label(key)}"
    return None


def extract_metrics(result: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Pull numeric counters from a task result dict."""
    if not isinstance(result, dict):
        return {}
    metrics: Dict[str, Any] = {}
    for key, value in result.items():
        if key in _RESERVED_RESULT_KEYS:
            continue
        formatted = _format_metric_pair(key, value)
        if formatted is not None:
            metrics[key] = value
    if isinstance(result.get("pruned"), dict):
        total_pruned = result.get("total_pruned")
        if isinstance(total_pruned, int):
            metrics["total_pruned"] = total_pruned
    return metrics


def format_metrics_line(metrics: Dict[str, Any]) -> str:
    """Compact human-readable counter string, e.g. ``enriched 5 · 0 errors``."""
    if not metrics:
        return ""
    ordered_keys: List[str] = [key for key in _METRIC_ORDER if key in metrics]
    for key in sorted(metrics):
        if key not in ordered_keys:
            ordered_keys.append(key)
    parts: List[str] = []
    for key in ordered_keys:
        formatted = _format_metric_pair(key, metrics[key])
        if formatted:
            parts.append(formatted)
    return " · ".join(parts)


def build_run_summary(
    status: str,
    *,
    error: Optional[str] = None,
    result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Structured last-run summary for admin list + monitor panels."""
    detail = extract_outcome_detail(status, error=error, result=result)
    metrics = extract_metrics(result)
    outcome_reason = detail.get("outcome_reason")

    if status == "skipped":
        summary_line = outcome_reason or humanize_skip_reason()
    elif _is_error_status(status) or error:
        summary_line = error or str((result or {}).get("error") or "Task failed")
    elif status == "interrupted":
        metric_line = format_metrics_line(metrics)
        summary_line = (
            f"Stopped early · {metric_line}" if metric_line else "Stopped before completion"
        )
    elif metrics:
        summary_line = format_metrics_line(metrics)
    elif status == "completed":
        summary_line = "Completed successfully"
    else:
        summary_line = outcome_reason or ""

    return {
        "summary_line": summary_line,
        "metrics": metrics,
        "outcome_reason": outcome_reason,
        "status": status,
    }


def extract_outcome_detail(
    status: str,
    *,
    error: Optional[str] = None,
    result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Normalize outcome metadata for run logs and task list payloads."""
    detail: Dict[str, Any] = {"status": status}
    if error:
        detail["error"] = error
    if not isinstance(result, dict):
        return detail

    reason = result.get("reason")
    note = result.get("note")
    if reason is not None:
        detail["reason"] = reason
    if note is not None:
        detail["note"] = note

    if status == "skipped":
        detail["outcome_reason"] = humanize_skip_reason(
            str(reason) if reason is not None else None,
            note=str(note) if note is not None else None,
        )
    elif _is_error_status(status) or error:
        detail["outcome_reason"] = error or str(result.get("error") or "Task failed")
    elif status == "interrupted":
        detail["outcome_reason"] = "Stopped before completion"
    elif status == "completed":
        detail["outcome_reason"] = "Completed successfully"

    metrics = extract_metrics(result)
    if metrics:
        detail["metrics"] = metrics
        metric_line = format_metrics_line(metrics)
        if metric_line:
            detail["summary_line"] = metric_line

    if status == "skipped" and detail.get("outcome_reason"):
        detail["summary_line"] = detail["outcome_reason"]

    return detail


def format_run_outcome_message(
    status: str,
    *,
    error: Optional[str] = None,
    result: Optional[Dict[str, Any]] = None,
) -> str:
    """Single-line admin log message for a finished run."""
    summary = build_run_summary(status, error=error, result=result)
    summary_line = summary.get("summary_line") or ""

    if _is_error_status(status) or error:
        return f"Failed — {summary_line or error or 'Unknown error'}"
    if status == "skipped":
        return f"Skipped — {summary_line or humanize_skip_reason()}"
    if status == "interrupted":
        return f"Interrupted — {summary_line or 'stopped before completion'}"
    if status == "completed":
        if summary_line and summary_line != "Completed successfully":
            return f"Finished — succeeded · {summary_line}"
        return "Finished — succeeded"
    if summary_line:
        return f"Finished — {status} · {summary_line}"
    return f"Finished — {status}"
