"""Household holiday calendar — seed defaults, grounding dates, active windows.

Admin CRUD persists observances in SQLite; Explore's seasonal rail reads the
store (asymmetric pre/post shoulders + rail title curation). Built-in seeds
mirror the former hard-coded ``FIXED_HOLIDAYS`` / movable rules in feeds.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

# Season fallback keys (also used as rail-curation scope ids).
SEASONAL_FALLBACKS: Tuple[Tuple[str, str, Tuple[int, ...], Tuple[str, ...]], ...] = (
    ("season:winter-nights", "Winter nights", (12, 1, 2), ("winter", "snow", "holiday", "christmas")),
    ("season:spring-awakenings", "Spring awakenings", (3, 4, 5), ("spring", "nature", "garden", "coming of age")),
    ("season:summer-comfort", "Summer comfort", (6, 7, 8), ("summer", "road trip", "beach", "vacation")),
    ("season:autumn-gothic", "Autumn gothic", (9, 10, 11), ("autumn", "fall", "gothic", "mystery", "horror")),
)

# Legacy symmetric window kept for docs / imports; live matching uses per-row shoulders.
HOLIDAY_WINDOW_DAYS = 7


def _terms(*values: str) -> List[str]:
    return list(values)


# Builtin seeds. ``pre`` / ``post`` are asymmetric by default (owner-overridable).
DEFAULT_OBSERVANCES: Tuple[Dict[str, Any], ...] = (
    {
        "id": "new-years-day",
        "name": "New Year's Day",
        "kind": "fixed",
        "month": 1,
        "day": 1,
        "movable_rule": None,
        "pre_shoulder_days": 3,
        "post_shoulder_days": 5,
        "search_terms": _terms("new year", "party", "celebration", "fresh start"),
        "schedule_publish": True,
    },
    {
        "id": "groundhog-day",
        "name": "Groundhog Day",
        "kind": "fixed",
        "month": 2,
        "day": 2,
        "movable_rule": None,
        "pre_shoulder_days": 5,
        "post_shoulder_days": 2,
        "search_terms": _terms("groundhog", "winter", "repetition", "small town"),
        "schedule_publish": True,
    },
    {
        "id": "valentines-day",
        "name": "Valentine's Day",
        "kind": "fixed",
        "month": 2,
        "day": 14,
        "movable_rule": None,
        "pre_shoulder_days": 7,
        "post_shoulder_days": 2,
        "search_terms": _terms("romance", "love", "dating", "valentine"),
        "schedule_publish": True,
    },
    {
        "id": "pi-day",
        "name": "Pi Day",
        "kind": "fixed",
        "month": 3,
        "day": 14,
        "movable_rule": None,
        "pre_shoulder_days": 3,
        "post_shoulder_days": 1,
        "search_terms": _terms("math", "science", "pie", "genius"),
        "schedule_publish": True,
    },
    {
        "id": "st-patricks-day",
        "name": "St. Patrick's Day",
        "kind": "fixed",
        "month": 3,
        "day": 17,
        "movable_rule": None,
        "pre_shoulder_days": 5,
        "post_shoulder_days": 2,
        "search_terms": _terms("ireland", "irish", "green", "pub"),
        "schedule_publish": True,
    },
    {
        "id": "earth-day",
        "name": "Earth Day",
        "kind": "fixed",
        "month": 4,
        "day": 22,
        "movable_rule": None,
        "pre_shoulder_days": 5,
        "post_shoulder_days": 2,
        "search_terms": _terms("nature", "environment", "earth", "wildlife"),
        "schedule_publish": True,
    },
    {
        "id": "arbor-day",
        "name": "Arbor Day",
        "kind": "movable",
        "month": None,
        "day": None,
        "movable_rule": "arbor_day",
        "pre_shoulder_days": 5,
        "post_shoulder_days": 2,
        "search_terms": _terms("tree", "forest", "nature", "environment", "garden"),
        "schedule_publish": True,
    },
    {
        "id": "may-day",
        "name": "May Day",
        "kind": "fixed",
        "month": 5,
        "day": 1,
        "movable_rule": None,
        "pre_shoulder_days": 5,
        "post_shoulder_days": 2,
        "search_terms": _terms("spring", "garden", "flower", "festival"),
        "schedule_publish": True,
    },
    {
        "id": "independence-day",
        "name": "Independence Day",
        "kind": "fixed",
        "month": 7,
        "day": 4,
        "movable_rule": None,
        "pre_shoulder_days": 5,
        "post_shoulder_days": 2,
        "search_terms": _terms("america", "independence", "summer", "fireworks"),
        "schedule_publish": True,
    },
    {
        "id": "labor-day",
        "name": "Labor Day",
        "kind": "movable",
        "month": None,
        "day": None,
        "movable_rule": "labor_day",
        "pre_shoulder_days": 5,
        "post_shoulder_days": 2,
        "search_terms": _terms("work", "road trip", "summer", "family"),
        "schedule_publish": True,
    },
    {
        "id": "halloween",
        "name": "Halloween",
        "kind": "fixed",
        "month": 10,
        "day": 31,
        "movable_rule": None,
        "pre_shoulder_days": 12,
        "post_shoulder_days": 3,
        "search_terms": _terms("horror", "haunted", "ghost", "witch", "monster"),
        "schedule_publish": True,
    },
    {
        "id": "dia-de-los-muertos",
        "name": "Día de los Muertos",
        "kind": "fixed",
        "month": 11,
        "day": 2,
        "movable_rule": None,
        "pre_shoulder_days": 5,
        "post_shoulder_days": 2,
        "search_terms": _terms("afterlife", "spirit", "family", "mexico"),
        "schedule_publish": True,
    },
    {
        "id": "thanksgiving",
        "name": "Thanksgiving",
        "kind": "movable",
        "month": None,
        "day": None,
        "movable_rule": "thanksgiving",
        "pre_shoulder_days": 7,
        "post_shoulder_days": 2,
        "search_terms": _terms("family", "food", "home", "thanksgiving"),
        "schedule_publish": True,
    },
    {
        "id": "winter-solstice",
        "name": "Winter Solstice",
        "kind": "fixed",
        "month": 12,
        "day": 21,
        "movable_rule": None,
        "pre_shoulder_days": 14,
        "post_shoulder_days": 3,
        "search_terms": _terms("winter", "snow", "holiday", "christmas"),
        "schedule_publish": True,
    },
    {
        "id": "christmas",
        "name": "Christmas",
        "kind": "fixed",
        "month": 12,
        "day": 25,
        "movable_rule": None,
        "pre_shoulder_days": 21,
        "post_shoulder_days": 4,
        "search_terms": _terms("christmas", "holiday", "winter", "family"),
        "schedule_publish": True,
    },
)

# Backward-compatible tuple shape used by older docs/tests: (name, month, day, terms).
FIXED_HOLIDAYS = tuple(
    (row["name"], int(row["month"]), int(row["day"]), tuple(row["search_terms"]))
    for row in DEFAULT_OBSERVANCES
    if row["kind"] == "fixed" and row.get("month") and row.get("day")
)

MOVABLE_RULES = frozenset({"arbor_day", "labor_day", "thanksgiving"})


def movable_grounding(rule: str, year: int) -> date:
    """Compute the grounding date for a movable US-style observance."""
    key = str(rule or "").strip().lower()
    if key == "arbor_day":
        april_first = date(year, 4, 1)
        return date(year, 4, 1 + ((4 - april_first.weekday()) % 7) + 21)
    if key == "labor_day":
        september_first = date(year, 9, 1)
        return date(year, 9, 1 + ((0 - september_first.weekday()) % 7))
    if key == "thanksgiving":
        november_first = date(year, 11, 1)
        return date(year, 11, 1 + ((3 - november_first.weekday()) % 7) + 21)
    raise ValueError(f"Unknown movable rule: {rule}")


def grounding_date_for(observance: Mapping[str, Any], year: int) -> date:
    """Return the day this observance is pinned to in ``year`` (server-local calendar)."""
    kind = str(observance.get("kind") or "fixed").strip().lower()
    if kind == "movable":
        return movable_grounding(str(observance.get("movable_rule") or ""), year)
    month = int(observance["month"])
    day = int(observance["day"])
    return date(year, month, day)


def _safe_shoulder(observance: Mapping[str, Any]) -> Tuple[int, int]:
    try:
        pre = int(observance.get("pre_shoulder_days", 7))
    except (TypeError, ValueError):
        pre = 7
    try:
        post = int(observance.get("post_shoulder_days", 7))
    except (TypeError, ValueError):
        post = 7
    return max(0, min(pre, 90)), max(0, min(post, 90))


def window_for(observance: Mapping[str, Any], year: int) -> Tuple[date, date, date]:
    """Return (grounding, window_start, window_end) for one year."""
    grounding = grounding_date_for(observance, year)
    pre, post = _safe_shoulder(observance)
    return grounding, grounding - timedelta(days=pre), grounding + timedelta(days=post)


def active_grounding(observance: Mapping[str, Any], today: date) -> Optional[date]:
    """If ``today`` falls in an asymmetric shoulder window, return that grounding date."""
    if not bool(observance.get("enabled", True)):
        return None
    best: Optional[date] = None
    best_dist = 10_000
    for year in (today.year - 1, today.year, today.year + 1):
        try:
            grounding, start, end = window_for(observance, year)
        except (TypeError, ValueError):
            continue
        if start <= today <= end:
            dist = abs((grounding - today).days)
            if dist < best_dist:
                best = grounding
                best_dist = dist
    return best


@dataclass(frozen=True)
class SeasonalContext:
    scope_id: str
    label: str
    terms: Tuple[str, ...]
    mode: str  # holiday | season
    grounding_date: Optional[date] = None
    pre_shoulder_days: Optional[int] = None
    post_shoulder_days: Optional[int] = None
    schedule_publish: bool = True


def normalize_search_terms(raw: Any) -> List[str]:
    if isinstance(raw, str):
        parts = [part.strip() for part in raw.replace("\n", ",").split(",")]
        return [part for part in parts if part]
    if isinstance(raw, (list, tuple)):
        return [str(part).strip() for part in raw if str(part).strip()]
    return []


def season_fallback_for(today: date) -> SeasonalContext:
    for scope_id, label, months, terms in SEASONAL_FALLBACKS:
        if today.month in months:
            return SeasonalContext(
                scope_id=scope_id,
                label=label,
                terms=terms,
                mode="season",
                schedule_publish=True,
            )
    return SeasonalContext(
        scope_id="season:picks",
        label="Seasonal picks",
        terms=(),
        mode="season",
        schedule_publish=True,
    )


def resolve_seasonal_context(
    observances: Sequence[Mapping[str, Any]],
    today: date,
    *,
    require_schedule_publish: bool = False,
) -> SeasonalContext:
    """Pick the active holiday (nearest grounding) or a season fallback.

    Disabled observances never drive the rail. When ``require_schedule_publish``
    is true (B2 scheduled rails), skip holidays with schedule_publish=false.
    """
    active: List[Tuple[Mapping[str, Any], date]] = []
    for obs in observances:
        if not bool(obs.get("enabled", True)):
            continue
        if require_schedule_publish and not bool(obs.get("schedule_publish", True)):
            continue
        grounding = active_grounding(obs, today)
        if grounding is not None:
            active.append((obs, grounding))
    if active:
        obs, grounding = min(active, key=lambda entry: abs((entry[1] - today).days))
        pre, post = _safe_shoulder(obs)
        terms = tuple(normalize_search_terms(obs.get("search_terms")))
        return SeasonalContext(
            scope_id=str(obs["id"]),
            label=str(obs.get("name") or "Holiday"),
            terms=terms,
            mode="holiday",
            grounding_date=grounding,
            pre_shoulder_days=pre,
            post_shoulder_days=post,
            schedule_publish=bool(obs.get("schedule_publish", True)),
        )
    return season_fallback_for(today)


def upcoming_windows(
    observances: Sequence[Mapping[str, Any]],
    today: date,
    *,
    horizon_days: int = 60,
) -> List[Dict[str, Any]]:
    """Upcoming (or active) windows for Admin schedule preview."""
    horizon = today + timedelta(days=max(1, min(int(horizon_days), 366)))
    rows: List[Dict[str, Any]] = []
    for obs in observances:
        if not bool(obs.get("enabled", True)):
            continue
        for year in (today.year - 1, today.year, today.year + 1):
            try:
                grounding, start, end = window_for(obs, year)
            except (TypeError, ValueError):
                continue
            if end < today or start > horizon:
                continue
            pre, post = _safe_shoulder(obs)
            rows.append(
                {
                    "id": obs["id"],
                    "name": obs.get("name"),
                    "grounding_date": grounding.isoformat(),
                    "window_start": start.isoformat(),
                    "window_end": end.isoformat(),
                    "pre_shoulder_days": pre,
                    "post_shoulder_days": post,
                    "active_now": start <= today <= end,
                    "schedule_publish": bool(obs.get("schedule_publish", True)),
                    "days_until_grounding": (grounding - today).days,
                }
            )
    rows.sort(key=lambda row: (row["window_start"], row["name"] or ""))
    # De-dupe by id keeping soonest window.
    seen: set[str] = set()
    unique: List[Dict[str, Any]] = []
    for row in rows:
        key = str(row["id"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    return unique


def compose_rail_items(
    *,
    pins: Sequence[Mapping[str, Any]],
    includes: Sequence[Mapping[str, Any]],
    matches: Sequence[Mapping[str, Any]],
    excludes: Iterable[int],
    limit: int,
    feed_item_fn,
    sort_unpinned_fn,
) -> List[Dict[str, Any]]:
    """pins (front) → includes ∪ matches − excludes; year-sort the unpinned tail."""
    exclude_ids = {int(item_id) for item_id in excludes}
    pinned_ids: List[int] = []
    pin_rows: Dict[int, Mapping[str, Any]] = {}
    for row in pins:
        try:
            item_id = int(row["id"])
        except (TypeError, ValueError, KeyError):
            continue
        if item_id in exclude_ids or item_id in pin_rows:
            continue
        pinned_ids.append(item_id)
        pin_rows[item_id] = row

    pool: Dict[int, Mapping[str, Any]] = {}
    for row in list(includes) + list(matches):
        try:
            item_id = int(row["id"])
        except (TypeError, ValueError, KeyError):
            continue
        if item_id in exclude_ids or item_id in pin_rows or item_id in pool:
            continue
        pool[item_id] = row

    include_ids = set()
    for row in includes:
        try:
            include_ids.add(int(row["id"]))
        except (TypeError, ValueError, KeyError):
            continue

    result: List[Dict[str, Any]] = []
    for item_id in pinned_ids:
        if len(result) >= limit:
            break
        result.append(feed_item_fn(pin_rows[item_id], rail_role="pin"))

    remaining = limit - len(result)
    if remaining > 0 and pool:
        sorted_tail = sort_unpinned_fn(list(pool.values()), remaining)
        for item in sorted_tail:
            try:
                iid = int(item.get("id"))
            except (TypeError, ValueError):
                iid = None
            item["rail_role"] = "include" if iid in include_ids else "match"
            result.append(item)
            if len(result) >= limit:
                break
    return result[:limit]
