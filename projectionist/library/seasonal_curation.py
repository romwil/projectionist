"""Agent-driven seasonal shelf curation (professor / staff-pick voice).

Admin Live Channels asks the LLM to propose an ordered mix of well-known and
lesser-known library titles for a holiday shelf, each with a short curator note.
The owner click applies that proposal: prior pins and the keyword dump are replaced.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Mapping, Sequence

from projectionist.config_store import Settings, validate_llm_settings
from projectionist.library.db import Database

logger = logging.getLogger(__name__)

DEFAULT_PICK_LIMIT = 10
MAX_PICK_LIMIT = 16
MAX_CANDIDATES = 48
_MAX_NOTE_CHARS = 280

_SYSTEM_PROMPT = """\
You are the household film professor curating a seasonal shelf for Explore.

Pick a deliberate mix — not an alphabetical or newest-first dump. Blend a few
well-known titles people expect for the season with lesser-known gems that
introduce the household to the occasion. Prefer variety in era and tone.

For each pick write a short staff-pick card note (1–2 sentences, under 40 words):
opinionated, human, why this title for this season / this year. No generic AI fluff.
No spoilers beyond the premise.

Reply with JSON only (no markdown fences):
{"picks":[{"library_item_id":123,"note":"…"},…]}

Use only library_item_id values from the candidate list. Order = shelf order.
Aim for {limit} picks (at least 6 if candidates allow; never invent ids).
"""


def _response_text(response: Mapping[str, Any]) -> str:
    if not isinstance(response, Mapping):
        return ""
    content = response.get("content")
    if content:
        return str(content)
    choices = response.get("choices") or []
    if choices and isinstance(choices[0], Mapping):
        message = choices[0].get("message") or {}
        if isinstance(message, Mapping):
            return str(message.get("content") or "")
    return ""


def _extract_json_object(raw: str) -> Dict[str, Any]:
    text = str(raw or "").strip()
    if not text:
        raise ValueError("Empty curator response")
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, flags=re.I)
    if fence:
        text = fence.group(1).strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("Curator response was not JSON") from None
        payload = json.loads(text[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("Curator response must be a JSON object")
    return payload


def _clean_note(raw: Any) -> str:
    text = " ".join(str(raw or "").split()).strip().strip('"').strip("'")
    if len(text) > _MAX_NOTE_CHARS:
        text = text[: _MAX_NOTE_CHARS - 1].rstrip() + "…"
    return text


def candidate_pool(
    db: Database,
    scope_id: str,
    *,
    limit: int = MAX_CANDIDATES,
) -> Dict[str, Any]:
    """Keyword matches for a shelf, minus owner excludes, for the curator prompt."""
    from projectionist.library.feeds import _match_seasonal_rows

    obs = None
    try:
        obs = db.get_holiday_observance(scope_id)
    except Exception:  # noqa: BLE001
        obs = None
    if obs is None and not str(scope_id).startswith("season:"):
        raise KeyError("Holiday not found")

    label = str((obs or {}).get("name") or scope_id)
    terms = tuple((obs or {}).get("search_terms") or ())
    matches = _match_seasonal_rows(db.all_library_items(), terms)
    try:
        curation = db.holiday_rail_curation_maps(scope_id)
    except Exception:  # noqa: BLE001
        curation = {"excludes": []}
    exclude_ids = {int(item_id) for item_id in (curation.get("excludes") or [])}
    candidates: List[Dict[str, Any]] = []
    for row in matches:
        try:
            item_id = int(row["id"])
        except (TypeError, ValueError, KeyError):
            continue
        if item_id in exclude_ids:
            continue
        year = row["year"] if "year" in row.keys() else None
        candidates.append(
            {
                "library_item_id": item_id,
                "title": str(row["title"] or ""),
                "year": int(year) if year is not None else None,
                "media_type": str(row["media_type"] or ""),
            }
        )
        if len(candidates) >= limit:
            break
    return {
        "scope_id": scope_id,
        "label": label,
        "search_terms": list(terms),
        "candidates": candidates,
        "excluded_count": len(exclude_ids),
    }


def normalize_proposal_picks(
    raw_picks: Sequence[Mapping[str, Any]],
    *,
    allowed_ids: Sequence[int],
    limit: int = DEFAULT_PICK_LIMIT,
) -> List[Dict[str, Any]]:
    """Validate LLM/manual picks against the candidate id set."""
    allowed = {int(item_id) for item_id in allowed_ids}
    capped = max(1, min(int(limit), MAX_PICK_LIMIT))
    out: List[Dict[str, Any]] = []
    seen: set[int] = set()
    for raw in raw_picks or []:
        if not isinstance(raw, Mapping):
            continue
        try:
            item_id = int(raw.get("library_item_id") or raw.get("id") or 0)
        except (TypeError, ValueError):
            continue
        if item_id not in allowed or item_id in seen:
            continue
        seen.add(item_id)
        note = _clean_note(raw.get("note") or raw.get("curator_note") or "")
        out.append({"library_item_id": item_id, "curator_note": note})
        if len(out) >= capped:
            break
    return out


def enrich_picks(
    db: Database, picks: Sequence[Mapping[str, Any]]
) -> List[Dict[str, Any]]:
    """Attach title/year for Admin proposal review UI."""
    ids = [int(p["library_item_id"]) for p in picks]
    by_id = db.get_library_items_by_ids(ids)
    enriched: List[Dict[str, Any]] = []
    for pick in picks:
        item_id = int(pick["library_item_id"])
        row = by_id.get(item_id)
        year = None
        title = ""
        media_type = ""
        if row is not None:
            title = str(row["title"] or "")
            media_type = str(row["media_type"] or "")
            if row["year"] is not None:
                year = int(row["year"])
        enriched.append(
            {
                "library_item_id": item_id,
                "id": item_id,
                "curator_note": str(pick.get("curator_note") or ""),
                "title": title,
                "year": year,
                "media_type": media_type,
            }
        )
    return enriched


async def propose_seasonal_shelf(
    db: Database,
    settings: Settings,
    scope_id: str,
    *,
    limit: int = DEFAULT_PICK_LIMIT,
) -> Dict[str, Any]:
    """Ask the configured LLM to propose ordered picks + notes (no write)."""
    config_error = validate_llm_settings(settings)
    if config_error:
        raise ValueError(config_error)

    pool = candidate_pool(db, scope_id)
    candidates = list(pool["candidates"])
    if len(candidates) < 3:
        raise ValueError(
            "Not enough matching titles in the library to curate this shelf yet. "
            "Widen the season keywords or add titles first."
        )

    capped = max(6, min(int(limit or DEFAULT_PICK_LIMIT), MAX_PICK_LIMIT))
    if len(candidates) < capped:
        capped = max(3, len(candidates))

    from projectionist.agent.providers import get_chat_provider
    from projectionist.telemetry import PURPOSE_SEASONAL_CURATION
    from projectionist.telemetry.llm_track import tracked_chat

    provider = get_chat_provider(settings)
    candidate_lines = "\n".join(
        f"- id={c['library_item_id']}: {c['title']}"
        + (f" ({c['year']})" if c.get("year") else "")
        + (f" [{c['media_type']}]" if c.get("media_type") else "")
        for c in candidates
    )
    terms = ", ".join(pool["search_terms"]) or "(none)"
    user_prompt = (
        f"Seasonal shelf: {pool['label']} (scope_id={scope_id})\n"
        f"Keywords: {terms}\n"
        f"Pick about {capped} titles from this candidate list:\n{candidate_lines}"
    )
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT.format(limit=capped)},
        {"role": "user", "content": user_prompt},
    ]
    response = await tracked_chat(
        db,
        provider,
        messages,
        purpose=PURPOSE_SEASONAL_CURATION,
        meta={"scope_id": scope_id, "label": pool["label"]},
    )
    payload = _extract_json_object(_response_text(response))
    picks = normalize_proposal_picks(
        payload.get("picks") or [],
        allowed_ids=[c["library_item_id"] for c in candidates],
        limit=capped,
    )
    if len(picks) < 3:
        raise ValueError(
            "The curator returned too few valid picks. Try again, or reorder the shelf by hand."
        )
    return {
        "scope_id": scope_id,
        "label": pool["label"],
        "candidate_count": len(candidates),
        "picks": enrich_picks(db, picks),
        "note": (
            "Review these staff picks, then confirm to replace the shelf order. "
            "Titles you marked “Not a fit” stay off the shelf."
        ),
    }


def apply_seasonal_shelf_proposal(
    db: Database,
    scope_id: str,
    picks: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Persist a confirmed proposal as ordered pins + curator notes."""
    if db.get_holiday_observance(scope_id) is None and not str(scope_id).startswith(
        "season:"
    ):
        raise KeyError("Holiday not found")
    pool = candidate_pool(db, scope_id)
    allowed = [c["library_item_id"] for c in pool["candidates"]]
    # Also allow ids already on the shelf (manual adds outside keyword match).
    for title in db.list_holiday_rail_titles(scope_id):
        allowed.append(int(title["library_item_id"]))
    normalized = normalize_proposal_picks(
        picks, allowed_ids=allowed, limit=MAX_PICK_LIMIT
    )
    if len(normalized) < 1:
        raise ValueError("No valid picks to apply")
    curation = db.apply_holiday_rail_curation(scope_id, normalized)
    from projectionist.library.explore_hub import invalidate_explore_hub_cache
    from projectionist.library.feeds import preview_holiday_rail

    invalidate_explore_hub_cache()
    preview = preview_holiday_rail(db, scope_id, limit=12)
    return {"curation": curation, "preview": preview, "applied": len(normalized)}
