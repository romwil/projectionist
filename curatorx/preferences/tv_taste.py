"""Episode / season-decay weighting for TV taste signals.

Show-level reviews alone over-weight abandoned series: a strong S1 rating
keeps pulling later-season neighbors long after the household stopped watching.
These helpers fold ``library_episodes`` view + star curves into a single
multiplier for taste refresh / preference facts.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Mapping, Optional, Sequence


# Seasons beyond the last meaningfully watched season decay with this half-life.
DEFAULT_SEASON_HALF_LIFE = 1.5
# Viewed fraction below this (among later seasons) counts as abandonment.
ABANDON_VIEW_FRACTION = 0.15
# Multiplier applied to overall show taste when abandoned mid-series.
ABANDON_SHOW_MULTIPLIER = 0.35


def episode_sentiment(stars: Optional[float], view_count: int) -> float:
    """Map episode stars / watch to a signed sentiment contribution.

    - Rated episodes: ``(stars - 3) * 0.5`` (1★ → -1.0, 5★ → +1.0)
    - Watched but unrated: mild positive ``0.15``
    - Unwatched: ``0.0``
    """
    views = int(view_count or 0)
    if stars is not None:
        try:
            rating = float(stars)
        except (TypeError, ValueError):
            rating = None
        else:
            if 1.0 <= rating <= 5.0:
                return (rating - 3.0) * 0.5
    if views > 0:
        return 0.15
    return 0.0


def season_decay(
    season_number: int,
    last_engaged_season: int,
    *,
    half_life: float = DEFAULT_SEASON_HALF_LIFE,
) -> float:
    """Weight for a season relative to the last season the household engaged with.

    Seasons at/before ``last_engaged_season`` keep full weight (1.0). Later
    seasons decay exponentially so abandoned tails do not dominate neighbors.
    """
    season = max(1, int(season_number or 1))
    anchor = max(1, int(last_engaged_season or 1))
    if season <= anchor:
        return 1.0
    distance = float(season - anchor)
    hl = max(0.25, float(half_life or DEFAULT_SEASON_HALF_LIFE))
    return 0.5 ** (distance / hl)


def _season_stats(episodes: Sequence[Mapping[str, Any]]) -> Dict[int, Dict[str, float]]:
    by_season: Dict[int, Dict[str, float]] = defaultdict(
        lambda: {"episodes": 0.0, "viewed": 0.0, "sentiment": 0.0, "weight": 0.0}
    )
    for ep in episodes:
        season = int(ep.get("season_number") or 1)
        if season <= 0:
            season = 1
        views = int(ep.get("view_count") or 0)
        stars = ep.get("plex_user_rating_stars")
        if stars is None:
            stars = ep.get("stars")
        sent = episode_sentiment(stars if stars is not None else None, views)
        by_season[season]["episodes"] += 1.0
        if views > 0 or (stars is not None and float(stars or 0) > 0):
            by_season[season]["viewed"] += 1.0
        by_season[season]["sentiment"] += sent
        by_season[season]["weight"] += 1.0
    return by_season


def last_engaged_season(episodes: Sequence[Mapping[str, Any]]) -> int:
    """Highest season with any watch or rating."""
    last = 1
    for ep in episodes:
        views = int(ep.get("view_count") or 0)
        stars = ep.get("plex_user_rating_stars")
        if stars is None:
            stars = ep.get("stars")
        rated = stars is not None and float(stars or 0) > 0
        if views > 0 or rated:
            season = int(ep.get("season_number") or 1)
            last = max(last, max(1, season))
    return last


def is_abandoned_mid_series(episodes: Sequence[Mapping[str, Any]]) -> bool:
    """True when early seasons were watched but later seasons barely were."""
    if not episodes:
        return False
    stats = _season_stats(episodes)
    if not stats:
        return False
    max_season = max(stats)
    engaged = last_engaged_season(episodes)
    if max_season <= engaged:
        return False
    # Later seasons exist beyond engagement.
    later_eps = 0.0
    later_viewed = 0.0
    for season, row in stats.items():
        if season > engaged:
            later_eps += row["episodes"]
            later_viewed += row["viewed"]
    if later_eps <= 0:
        return False
    return (later_viewed / later_eps) < ABANDON_VIEW_FRACTION


def show_taste_multiplier(
    episodes: Sequence[Mapping[str, Any]],
    *,
    half_life: float = DEFAULT_SEASON_HALF_LIFE,
) -> float:
    """Aggregate episode sentiments with season-decay into a 0..1+ show multiplier.

    - No episode rows → ``1.0`` (caller keeps show-level review weight unchanged)
    - Abandoned mid-series → capped by ``ABANDON_SHOW_MULTIPLIER`` after decay
    - Consistent engagement → near 1.0 when average sentiment is neutral-positive
    """
    if not episodes:
        return 1.0

    engaged = last_engaged_season(episodes)
    stats = _season_stats(episodes)
    weighted_sum = 0.0
    weight_total = 0.0
    for season, row in stats.items():
        decay = season_decay(season, engaged, half_life=half_life)
        # Average sentiment in the season, then apply decay.
        avg = row["sentiment"] / row["weight"] if row["weight"] else 0.0
        # Map signed avg (-1..1) toward positive affinity mass for cluster boosts.
        affinity = max(0.0, (avg + 1.0) / 2.0)
        season_weight = decay * max(row["viewed"], 0.25 * row["episodes"])
        weighted_sum += affinity * season_weight
        weight_total += season_weight

    if weight_total <= 0:
        return 0.0
    base = weighted_sum / weight_total
    if is_abandoned_mid_series(episodes):
        base *= ABANDON_SHOW_MULTIPLIER
    return max(0.0, min(1.5, base))


def preference_fact_weight_for_show(
    episodes: Sequence[Mapping[str, Any]],
    *,
    base_weight: float = 1.0,
) -> float:
    """Scale a preference-fact / review weight for a show using episode curves."""
    return float(base_weight) * show_taste_multiplier(episodes)


def summarize_episode_curve(episodes: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Compact summary for tests / logging."""
    stats = _season_stats(episodes)
    return {
        "seasons": sorted(stats),
        "last_engaged_season": last_engaged_season(episodes),
        "abandoned": is_abandoned_mid_series(episodes),
        "multiplier": show_taste_multiplier(episodes),
        "per_season": {
            season: {
                "episodes": int(row["episodes"]),
                "viewed": int(row["viewed"]),
                "avg_sentiment": (
                    row["sentiment"] / row["weight"] if row["weight"] else 0.0
                ),
                "decay": season_decay(season, last_engaged_season(episodes)),
            }
            for season, row in sorted(stats.items())
        },
    }
