"""Agent-driven seasonal shelf curation (professor / staff-pick voice).

The owner asks for a theme and a balanced shelf. Candidates are scored from
holiday keywords, the plot, and earlier seasons in this household. Weak terms
such as "winter" or "family" count only beside a strong signal. Nothing is
written until the owner applies the preview.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence

from projectionist.config_store import Settings, validate_llm_settings
from projectionist.library.db import Database
from projectionist.library.holidays import SEASONAL_FALLBACKS, window_for

logger = logging.getLogger(__name__)

DEFAULT_PICK_LIMIT = 10
MAX_PICK_LIMIT = 16
MAX_CANDIDATES = 60
_MAX_NOTE_CHARS = 280
_MAX_THEME_CHARS = 180
_MAX_BECAUSE_CHARS = 180

SHELF_ROLES: tuple[str, ...] = (
    "Classic",
    "Family",
    "New this year",
    "Deep cut",
    "After bedtime",
)
AFTER_BEDTIME_ROLE = "After bedtime"
DEFAULT_ROLE_MIX: Dict[str, int] = {
    "Classic": 3,
    "Family": 3,
    "New this year": 1,
    "Deep cut": 2,
    "After bedtime": 1,
}

# Broad words that must not carry a title onto the shelf by themselves.
GLOBAL_WEAK_TERMS = frozenset(
    {
        "autumn",
        "beach",
        "celebration",
        "earth",
        "environment",
        "fall",
        "family",
        "festival",
        "flower",
        "food",
        "fresh start",
        "garden",
        "green",
        "holiday",
        "home",
        "love",
        "nature",
        "party",
        "road trip",
        "romance",
        "small town",
        "snow",
        "spring",
        "summer",
        "vacation",
        "wildlife",
        "winter",
        "work",
    }
)

# Strong keyword defaults that ship with the server, including terms an owner
# has not typed yet (Santa, Christmas Eve). Owner additions join this set.
BUILTIN_STRONG_TERMS: Dict[str, tuple[str, ...]] = {
    "christmas": ("christmas", "santa claus", "christmas eve", "santa", "nativity", "xmas"),
    "halloween": ("halloween", "horror", "haunted", "ghost", "witch", "monster"),
    "dia-de-los-muertos": (
        "dia de los muertos",
        "día de los muertos",
        "ofrenda",
        "afterlife",
        "spirit",
        "mexico",
    ),
    "thanksgiving": ("thanksgiving",),
    "new-years-day": ("new year", "new year's eve", "new years"),
    "valentines-day": ("valentine", "valentines"),
    "independence-day": ("independence day", "fourth of july", "4th of july"),
    "halloween-adjacent": (),
}

_SYSTEM_PROMPT = """\
You are __CURATOR_VOICE__ curating a seasonal shelf for Explore.

Pick a deliberate mix — not an alphabetical or newest-first dump. Blend a few
well-known titles people expect for the season with lesser-known gems that
introduce the household to the occasion. Prefer variety in era and tone.

Return one theme: a single line that ties this year's shelf together.

Each pick has a role. Use these exact words:
- Classic
- Family
- New this year
- Deep cut
- After bedtime (adult-rated; Youth members do not see this role)

Balance for __PICK_LIMIT__ picks: __ROLE_MIX__.

For each pick write a short staff-pick note (1–2 sentences). Use only facts from
the candidate lines and the household history in this prompt.
Do not invent trivia, cast facts, or quotes. No spoilers beyond the premise.

Reply with JSON only (no markdown fences):
{"theme":"…","picks":[{"library_item_id":123,"role":"Classic","note":"…","matched_because":"…"}]}

Use only library_item_id values from the candidate list. Order = shelf order.
matched_because names the signal you used (keyword, plot, or a past season).
Aim for __PICK_LIMIT__ picks (at least 6 if candidates allow; never invent ids).
"""


def _system_prompt(
    limit: int,
    *,
    voice: str = "the household film professor",
    role_mix: Optional[Mapping[str, int]] = None,
) -> str:
    """Fill the pick count without ``str.format``.

    The example JSON contains braces. ``str.format`` treats those braces as
    placeholders and raises ``KeyError`` before any model call.
    """
    mix = mix_for_limit(role_mix or DEFAULT_ROLE_MIX, int(limit))
    text = _SYSTEM_PROMPT.replace("__PICK_LIMIT__", str(int(limit)))
    text = text.replace("__CURATOR_VOICE__", voice.strip() or "the household film professor")
    return text.replace("__ROLE_MIX__", role_mix_line(mix))


def role_mix_line(mix: Mapping[str, int]) -> str:
    parts = [f"{int(mix.get(role) or 0)} {role}" for role in SHELF_ROLES if int(mix.get(role) or 0)]
    return ", ".join(parts)


def mix_for_limit(mix: Optional[Mapping[str, int]], limit: int) -> Dict[str, int]:
    """Scale a role mix so the quotas add up to ``limit``."""
    capped = max(1, min(int(limit), MAX_PICK_LIMIT))
    base = {role: max(0, int((mix or DEFAULT_ROLE_MIX).get(role) or 0)) for role in SHELF_ROLES}
    total = sum(base.values())
    if total <= 0:
        base = dict(DEFAULT_ROLE_MIX)
        total = sum(base.values())
    if total == capped:
        return base
    raw = {role: base[role] * capped / total for role in SHELF_ROLES}
    floored = {role: int(raw[role]) for role in SHELF_ROLES}
    leftover = capped - sum(floored.values())
    ranked = sorted(
        SHELF_ROLES,
        key=lambda role: (raw[role] - floored[role], base[role]),
        reverse=True,
    )
    for role in ranked:
        if leftover <= 0:
            break
        floored[role] += 1
        leftover -= 1
    return floored


def canonical_shelf_role(raw: Any) -> Optional[str]:
    text = " ".join(str(raw or "").split()).strip().casefold()
    if not text:
        return None
    for role in SHELF_ROLES:
        if role.casefold() == text:
            return role
    return None


def parse_curator_payload(payload: Mapping[str, Any]) -> Dict[str, Any]:
    """Validate the curator's JSON object before any pick is kept."""
    if not isinstance(payload, Mapping):
        raise ValueError("Curator response must be a JSON object")
    theme = _clean_theme(payload.get("theme"))
    if not theme:
        raise ValueError("The curator did not return a theme.")
    raw_picks = payload.get("picks")
    if not isinstance(raw_picks, list):
        raise ValueError("The curator did not return picks.")
    picks: List[Dict[str, Any]] = []
    for raw in raw_picks:
        if not isinstance(raw, Mapping):
            continue
        role_raw = raw.get("role", raw.get("shelf_role"))
        if role_raw is None or not str(role_raw).strip():
            raise ValueError("Each pick needs a role.")
        role = canonical_shelf_role(role_raw)
        if role is None:
            raise ValueError(f"Unknown shelf role: {role_raw}")
        picks.append({**dict(raw), "role": role})
    return {"theme": theme, "picks": picks}


def apply_role_mix(
    picks: Sequence[Mapping[str, Any]],
    mix: Optional[Mapping[str, int]] = None,
) -> List[Dict[str, Any]]:
    """Keep each role inside its quota. A pick with an empty note never ships."""
    quotas = {role: max(0, int((mix or DEFAULT_ROLE_MIX).get(role) or 0)) for role in SHELF_ROLES}
    counts = {role: 0 for role in SHELF_ROLES}
    kept: List[Dict[str, Any]] = []
    for raw in picks or []:
        if not isinstance(raw, Mapping):
            continue
        role = canonical_shelf_role(raw.get("role") or raw.get("shelf_role"))
        if role is None or counts[role] >= quotas[role]:
            continue
        note = _clean_note(raw.get("curator_note") or raw.get("note") or "")
        if not note:
            continue
        counts[role] += 1
        kept.append(
            {
                "library_item_id": int(raw.get("library_item_id") or raw.get("id") or 0),
                "curator_note": note,
                "role": role,
                "matched_because": _clean_because(raw.get("matched_because")),
            }
        )
    return kept


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


def _clean_theme(raw: Any) -> str:
    text = " ".join(str(raw or "").split()).strip()
    if len(text) > _MAX_THEME_CHARS:
        text = text[: _MAX_THEME_CHARS - 1].rstrip() + "…"
    return text


def _clean_because(raw: Any) -> str:
    text = " ".join(str(raw or "").split()).strip()
    if len(text) > _MAX_BECAUSE_CHARS:
        text = text[: _MAX_BECAUSE_CHARS - 1].rstrip() + "…"
    return text


def _value(row: Any, key: str, default: Any = None) -> Any:
    """Read a column from a dict or a sqlite row.

    On current Python, ``key in sqlite3.Row`` does not test column names.
    """
    try:
        names = row.keys()
    except Exception:  # noqa: BLE001
        return default
    if key not in names:
        return default
    try:
        return row[key]
    except Exception:  # noqa: BLE001
        return default


def _text_list(raw: Any) -> List[str]:
    if isinstance(raw, (list, tuple)):
        return [str(value).strip() for value in raw if str(value).strip()]
    try:
        decoded = json.loads(str(raw or "[]"))
    except (TypeError, ValueError):
        return []
    if not isinstance(decoded, list):
        return []
    return [str(value).strip() for value in decoded if str(value).strip()]


def _fold(text: Any) -> str:
    return " ".join(str(text or "").split()).casefold()


def signal_terms(observance: Mapping[str, Any]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Strong holiday keywords, plus weak terms that only count beside them.

    Built-in strong terms ship with the server. Terms the owner added that are
    not broad ("nutcracker") become strong. Broad terms stay weak.
    """
    scope_id = str(observance.get("id") or "")
    strong: List[str] = []
    seen: set[str] = set()

    def _add(bucket: List[str], term: str) -> None:
        cleaned = " ".join(str(term or "").split()).strip()
        key = cleaned.casefold()
        if not cleaned or key in seen:
            return
        seen.add(key)
        bucket.append(cleaned)

    for term in BUILTIN_STRONG_TERMS.get(scope_id, ()):
        _add(strong, term)
    weak: List[str] = []
    for term in observance.get("search_terms") or ():
        key = " ".join(str(term or "").split()).strip().casefold()
        if not key:
            continue
        if key in GLOBAL_WEAK_TERMS and key not in {item.casefold() for item in strong}:
            _add(weak, str(term))
        else:
            _add(strong, str(term))
    return tuple(strong), tuple(weak)


def _timestamp_date(raw: Any) -> Optional[date]:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    if value > 10_000_000_000:
        value = int(value / 1000)
    try:
        return datetime.fromtimestamp(value, timezone.utc).date()
    except (OverflowError, OSError, ValueError):
        return None


def _calendar_observance(observance: Mapping[str, Any]) -> Mapping[str, Any]:
    """Fill month and shoulders from the built-in seed when a caller only passed terms."""
    if observance.get("month") or observance.get("movable_rule") or observance.get("kind") == "movable":
        return observance
    from projectionist.library.holidays import DEFAULT_OBSERVANCES

    for seed in DEFAULT_OBSERVANCES:
        if str(seed.get("id") or "") != str(observance.get("id") or ""):
            continue
        merged = dict(seed)
        for key, value in observance.items():
            if value is not None:
                merged[key] = value
        return merged
    return observance


def _previous_windows(observance: Mapping[str, Any], today: date) -> List[tuple[int, date, date]]:
    observance = _calendar_observance(observance)
    windows: List[tuple[int, date, date]] = []
    years = list(range(today.year - 3, today.year))
    try:
        _grounding, start, end = window_for(observance, today.year)
    except (TypeError, ValueError):
        start = end = None
    else:
        if end < today:
            years.append(today.year)
    for year in years:
        try:
            _grounding, start, end = window_for(observance, year)
        except (TypeError, ValueError):
            continue
        if start <= today <= end:
            continue
        windows.append((year, start, end))
    return windows


def _in_windows(day: Optional[date], windows: Sequence[tuple[int, date, date]]) -> List[int]:
    if day is None:
        return []
    return [year for year, start, end in windows if start <= day <= end]


def score_seasonal_candidates(
    rows: Sequence[Mapping[str, Any]],
    observance: Mapping[str, Any],
    *,
    today: Optional[date] = None,
) -> List[Dict[str, Any]]:
    """Score library rows. Weak-only matches are left out."""
    selected_day = today or date.today()
    strong_terms, weak_terms = signal_terms(observance)
    windows = _previous_windows(observance, selected_day)
    strong_folded = [(term, term.casefold()) for term in strong_terms]
    weak_folded = [term.casefold() for term in weak_terms]
    scored: List[Dict[str, Any]] = []
    for row in rows:
        try:
            item_id = int(_value(row, "library_item_id", None) or _value(row, "id", 0) or 0)
        except (TypeError, ValueError):
            continue
        if item_id < 1:
            continue
        keywords = _text_list(_value(row, "keywords", []))
        genres = _text_list(_value(row, "genres", []))
        keyword_text = _fold(" ".join(keywords))
        genre_text = _fold(" ".join(genres))
        plot_text = _fold(
            " ".join(
                [
                    str(_value(row, "title", "") or ""),
                    str(_value(row, "summary", "") or ""),
                    str(_value(row, "tmdb_overview", "") or ""),
                    str(_value(row, "tagline", "") or ""),
                ]
            )
        )
        keyword_hits = [term for term, folded in strong_folded if folded and folded in keyword_text]
        plot_hits = [term for term, folded in strong_folded if folded and folded in plot_text]
        watched_years = _in_windows(_timestamp_date(_value(row, "last_viewed_at", None)), windows)
        signals: List[str] = []
        score = 0
        if keyword_hits:
            signals.append("keyword")
            score += 8
        if plot_hits:
            signals.append("plot")
            score += 5
        if watched_years:
            signals.append("household")
            score += 6
        if score <= 0:
            continue
        weak_hit = any(term and term in genre_text for term in weak_folded) or any(
            term and term in f"{plot_text} {keyword_text} {genre_text}" for term in weak_folded
        )
        genre_hit = any(
            folded and folded in genre_text for _term, folded in [*strong_folded, *[(w, w) for w in weak_folded]]
        )
        if weak_hit or genre_hit:
            score += 1
            signals.append("alongside")
        year = _value(row, "year", None)
        try:
            year_int = int(year) if year is not None else None
        except (TypeError, ValueError):
            year_int = None
        scored.append(
            {
                "library_item_id": item_id,
                "score": score,
                "signals": signals,
                "matching_keywords": keyword_hits,
                "plot_terms": plot_hits,
                "previous_seasons": [str(year) for year in watched_years],
                "year": year_int,
                "available_strong_terms": list(strong_terms),
                "row": row,
            }
        )
    scored.sort(key=lambda item: (-int(item["score"]), -(item["year"] or 0), item["library_item_id"]))
    return scored


def _select_with_era_variety(scored: Sequence[Mapping[str, Any]], limit: int) -> List[Mapping[str, Any]]:
    """Top scores, with at least one seat for each decade that scored."""
    capped = max(1, int(limit))
    if len(scored) <= capped:
        return list(scored)
    chosen: List[Mapping[str, Any]] = []
    seen: set[int] = set()
    decades: set[int] = set()
    for item in scored:
        year = item.get("year")
        decade = (int(year) // 10) * 10 if isinstance(year, int) else None
        if decade is None or decade in decades:
            continue
        decades.add(decade)
        seen.add(int(item["library_item_id"]))
        chosen.append(item)
        if len(chosen) >= capped:
            return chosen
    for item in scored:
        item_id = int(item["library_item_id"])
        if item_id in seen:
            continue
        seen.add(item_id)
        chosen.append(item)
        if len(chosen) >= capped:
            break
    return chosen


def _one_line(text: Any, limit: int = 180) -> str:
    cleaned = " ".join(str(text or "").split()).strip()
    if not cleaned:
        return ""
    sentence = re.split(r"(?<=[.!?])\s+", cleaned, maxsplit=1)[0]
    if len(sentence) > limit:
        return sentence[: limit - 1].rstrip() + "…"
    return sentence


def _youth_safe(rating: Any) -> bool:
    from projectionist.youth.rating_gate import (
        DEFAULT_YOUTH_MAX_RATING,
        content_rating_allowed,
    )

    return content_rating_allowed(rating, max_rating=DEFAULT_YOUTH_MAX_RATING)


def _candidate_dossier(scored: Mapping[str, Any]) -> Dict[str, Any]:
    raw_row = scored.get("row")
    row = raw_row if hasattr(raw_row, "keys") else {}
    year = scored.get("year")
    rating = _value(row, "vote_average", None)
    try:
        rating_value = float(rating) if rating is not None else None
    except (TypeError, ValueError):
        rating_value = None
    runtime = _value(row, "runtime_minutes", None)
    try:
        runtime_value = int(runtime) if runtime is not None else None
    except (TypeError, ValueError):
        runtime_value = None
    views = _value(row, "view_count", 0)
    try:
        view_count = int(views or 0)
    except (TypeError, ValueError):
        view_count = 0
    watched = _timestamp_date(_value(row, "last_viewed_at", None))
    synopsis = _one_line(_value(row, "summary", "") or _value(row, "tmdb_overview", ""))
    return {
        "library_item_id": int(scored["library_item_id"]),
        "title": str(_value(row, "title", "") or ""),
        "year": int(year) if isinstance(year, int) else None,
        "media_type": str(_value(row, "media_type", "") or ""),
        "synopsis": synopsis,
        "genres": _text_list(_value(row, "genres", [])),
        "matching_keywords": list(scored.get("matching_keywords") or []),
        "content_rating": str(_value(row, "content_rating", "") or ""),
        "runtime_minutes": runtime_value,
        "rating": rating_value,
        "household_views": view_count,
        "previous_seasons": list(scored.get("previous_seasons") or []),
        "last_watched": watched.isoformat() if watched else None,
        "youth_safe": _youth_safe(_value(row, "content_rating", "")),
        "score": int(scored.get("score") or 0),
        "signals": list(scored.get("signals") or []),
        "available_strong_terms": list(scored.get("available_strong_terms") or []),
    }


def _observance_for_scope(db: Database, scope_id: str) -> Dict[str, Any]:
    obs = None
    try:
        obs = db.get_holiday_observance(scope_id)
    except Exception:  # noqa: BLE001
        obs = None
    if obs is not None:
        return dict(obs)
    if str(scope_id).startswith("season:"):
        for sid, label, _months, terms in SEASONAL_FALLBACKS:
            if sid == scope_id:
                return {"id": sid, "name": label, "search_terms": list(terms)}
        return {"id": scope_id, "name": scope_id, "search_terms": []}
    raise KeyError("Holiday not found")


def candidate_pool(
    db: Database,
    scope_id: str,
    *,
    limit: int = MAX_CANDIDATES,
    today: Optional[date] = None,
) -> Dict[str, Any]:
    """Scored strong matches for a shelf, minus owner excludes."""
    obs = _observance_for_scope(db, scope_id)
    label = str(obs.get("name") or scope_id)
    strong_terms, weak_terms = signal_terms(obs)
    try:
        curation = db.holiday_rail_curation_maps(scope_id)
    except Exception:  # noqa: BLE001
        curation = {"excludes": []}
    exclude_ids = {int(item_id) for item_id in (curation.get("excludes") or [])}
    scored = score_seasonal_candidates(db.all_library_items(), obs, today=today)
    scored = [row for row in scored if int(row["library_item_id"]) not in exclude_ids]
    chosen = _select_with_era_variety(scored, max(1, min(int(limit), MAX_CANDIDATES)))
    candidates = [_candidate_dossier(row) for row in chosen]
    return {
        "scope_id": scope_id,
        "label": label,
        "search_terms": list(obs.get("search_terms") or []),
        "strong_terms": list(strong_terms),
        "weak_terms": list(weak_terms),
        "candidates": candidates,
        "excluded_count": len(exclude_ids),
    }


def normalize_proposal_picks(
    raw_picks: Sequence[Mapping[str, Any]],
    *,
    allowed_ids: Sequence[int],
    limit: int = DEFAULT_PICK_LIMIT,
) -> List[Dict[str, Any]]:
    """Validate LLM/manual picks against the candidate id set.

    A pick with an empty note never ships.
    """
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
        note = _clean_note(raw.get("note") or raw.get("curator_note") or "")
        if not note:
            continue
        seen.add(item_id)
        pick: Dict[str, Any] = {"library_item_id": item_id, "curator_note": note}
        role = canonical_shelf_role(raw.get("role") or raw.get("shelf_role"))
        if role:
            pick["role"] = role
        because = _clean_because(raw.get("matched_because"))
        if because:
            pick["matched_because"] = because
        out.append(pick)
        if len(out) >= capped:
            break
    return out


def enrich_picks(
    db: Database, picks: Sequence[Mapping[str, Any]]
) -> List[Dict[str, Any]]:
    """Attach title/year for the owner preview."""
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
        role = canonical_shelf_role(pick.get("role") or pick.get("shelf_role")) or ""
        enriched.append(
            {
                "library_item_id": item_id,
                "id": item_id,
                "curator_note": str(pick.get("curator_note") or ""),
                "role": role,
                "shelf_role": role,
                "matched_because": str(pick.get("matched_because") or ""),
                "title": title,
                "year": year,
                "media_type": media_type,
            }
        )
    return enriched


def _curator_voice(db: Database) -> str:
    try:
        personas = db.list_persona_templates()
    except Exception:  # noqa: BLE001
        return "the household film professor"
    chosen = None
    for persona in personas or []:
        if isinstance(persona, Mapping) and persona.get("is_default"):
            chosen = persona
            break
    if chosen is None and personas and isinstance(personas[0], Mapping):
        chosen = personas[0]
    name = str((chosen or {}).get("name") or "").strip()
    if not name:
        return "the household film professor"
    return f"{name}, the household curator"


def _stored_role_mix(db: Database, scope_id: str) -> Dict[str, int]:
    try:
        stored = db.holiday_rail_role_mix(scope_id)
    except Exception:  # noqa: BLE001
        stored = None
    if not isinstance(stored, Mapping) or not stored:
        return dict(DEFAULT_ROLE_MIX)
    return {role: max(0, int(stored.get(role) or 0)) for role in SHELF_ROLES}


def _candidate_prompt_line(candidate: Mapping[str, Any]) -> str:
    title = str(candidate.get("title") or "")
    year = f" ({candidate['year']})" if candidate.get("year") else ""
    parts = [f"- id={candidate['library_item_id']}: {title}{year}"]
    if candidate.get("synopsis"):
        parts.append(f"synopsis: {candidate['synopsis']}")
    if candidate.get("genres"):
        parts.append("genres: " + ", ".join(candidate["genres"]))
    if candidate.get("matching_keywords"):
        parts.append("keywords: " + ", ".join(candidate["matching_keywords"]))
    if candidate.get("content_rating"):
        parts.append(f"rating: {candidate['content_rating']}")
    if candidate.get("runtime_minutes"):
        parts.append(f"runtime: {candidate['runtime_minutes']} min")
    if candidate.get("rating") is not None:
        parts.append(f"score: {candidate['rating']}")
    views = int(candidate.get("household_views") or 0)
    seasons = candidate.get("previous_seasons") or []
    if views or seasons:
        season_text = ", ".join(str(item) for item in seasons) or "none"
        parts.append(f"household views: {views}; past seasons: {season_text}")
    if candidate.get("last_watched"):
        parts.append(f"last watched: {candidate['last_watched']}")
    parts.append("youth-safe: " + ("yes" if candidate.get("youth_safe") else "no"))
    return " | ".join(parts)


async def propose_seasonal_shelf(
    db: Database,
    settings: Settings,
    scope_id: str,
    *,
    limit: int = DEFAULT_PICK_LIMIT,
    role_mix: Optional[Mapping[str, int]] = None,
) -> Dict[str, Any]:
    """Ask the configured LLM for a theme and picks. Does not write."""
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
    stored = _stored_role_mix(db, scope_id)
    if role_mix:
        stored = {role: max(0, int(role_mix.get(role) or 0)) for role in SHELF_ROLES}
    mix = mix_for_limit(stored, capped)

    from projectionist.agent.providers import get_chat_provider
    from projectionist.telemetry import PURPOSE_SEASONAL_CURATION
    from projectionist.telemetry.llm_track import tracked_chat

    provider = get_chat_provider(settings)
    candidate_lines = "\n".join(_candidate_prompt_line(candidate) for candidate in candidates)
    terms = ", ".join(pool["strong_terms"]) or "(none)"
    user_prompt = (
        f"Seasonal shelf: {pool['label']} (scope_id={scope_id})\n"
        f"Strong keywords: {terms}\n"
        f"Weak terms only count when a strong signal is already true: "
        f"{', '.join(pool['weak_terms']) or '(none)'}\n"
        f"Pick about {capped} titles. Balance: {role_mix_line(mix)}.\n"
        f"Candidate list:\n{candidate_lines}"
    )
    messages = [
        {
            "role": "system",
            "content": _system_prompt(capped, voice=_curator_voice(db), role_mix=mix),
        },
        {"role": "user", "content": user_prompt},
    ]
    response = await tracked_chat(
        db,
        provider,
        messages,
        purpose=PURPOSE_SEASONAL_CURATION,
        meta={"scope_id": scope_id, "label": pool["label"]},
    )
    parsed = parse_curator_payload(_extract_json_object(_response_text(response)))
    picks = normalize_proposal_picks(
        parsed["picks"],
        allowed_ids=[c["library_item_id"] for c in candidates],
        limit=capped,
    )
    picks = apply_role_mix(picks, mix)
    if len(picks) < min(3, capped):
        raise ValueError(
            "The curator returned too few valid picks. Try again, or reorder the shelf by hand."
        )
    return {
        "scope_id": scope_id,
        "label": pool["label"],
        "theme": parsed["theme"],
        "role_mix": mix,
        "candidate_count": len(candidates),
        "picks": enrich_picks(db, picks),
        "note": (
            "Preview the theme and these staff picks. Apply replaces the shelf. "
            "Redo asks again. Cancel leaves the shelf as it is. "
            "Titles you marked “Not a fit” stay off the shelf."
        ),
    }


def apply_seasonal_shelf_proposal(
    db: Database,
    scope_id: str,
    picks: Sequence[Mapping[str, Any]],
    *,
    theme: Optional[str] = None,
) -> Dict[str, Any]:
    """Persist a confirmed proposal as ordered pins, notes, roles, and a theme."""
    if db.get_holiday_observance(scope_id) is None and not str(scope_id).startswith(
        "season:"
    ):
        raise KeyError("Holiday not found")
    pool = candidate_pool(db, scope_id)
    allowed = [c["library_item_id"] for c in pool["candidates"]]
    for title in db.list_holiday_rail_titles(scope_id):
        if str(title.get("curation") or "") == "exclude":
            continue
        allowed.append(int(title["library_item_id"]))
    normalized = normalize_proposal_picks(
        picks, allowed_ids=allowed, limit=MAX_PICK_LIMIT
    )
    if len(normalized) < 1:
        raise ValueError("No valid picks to apply")
    curation = db.apply_holiday_rail_curation(scope_id, normalized, theme=theme)
    from projectionist.library.explore_hub import invalidate_explore_hub_cache
    from projectionist.library.feeds import preview_holiday_rail

    invalidate_explore_hub_cache()
    preview = preview_holiday_rail(db, scope_id, limit=12)
    return {"curation": curation, "preview": preview, "applied": len(normalized), "theme": preview.get("theme") or ""}
