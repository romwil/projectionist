"""Year in Review recap sheet — shareable totals from a year rollup."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from projectionist.watch_tracker.models import TitleRollup, YearRollup
from projectionist.watch_tracker.rollups import month_label, peak_month

WEEKDAY_NAMES = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)
CAST_CAP_PER_TITLE = 4
HERO_HOURS_ROUND_AT = 10


def ranked_names(counts: Mapping[str, int], *, limit: int = 3) -> List[Dict[str, Any]]:
    ranked = sorted(
        ((str(name).strip(), int(n)) for name, n in counts.items() if str(name).strip() and int(n) > 0),
        key=lambda kv: (-kv[1], kv[0].lower()),
    )
    return [{"name": name, "count": n} for name, n in ranked[: max(0, int(limit))]]


def format_catalog_hours(minutes: int) -> str:
    hours = max(0, int(minutes)) / 60.0
    if hours >= HERO_HOURS_ROUND_AT:
        return str(int(round(hours)))
    text = f"{hours:.1f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def decade_phrase(decade: int) -> str:
    return f"the {int(decade)}s"


def personality_line(*, movie_genre: str, tv_genre: str, year: int) -> str:
    movie = str(movie_genre or "").strip()
    tv = str(tv_genre or "").strip()
    if movie and tv:
        if movie.lower() == tv.lower():
            return f"{movie} all the way down. That was your {year}."
        return f"{movie} movies. {tv} TV. That was your year."
    if movie:
        return f"{movie} movies carried {year}."
    if tv:
        return f"{tv} TV carried {year}."
    return f"Your {year} on the screen."


def honesty_footnote(rollup: YearRollup) -> str:
    body = "Finishes attributed to you — not the whole household."
    c = rollup.confidence or {}
    certain = int(c.get("certain") or 0)
    likely = int(c.get("likely") or 0)
    plex_only = int(c.get("plex_event_only") or 0)
    bits: List[str] = []
    if certain:
        bits.append(f"{certain} with live progress")
    if likely:
        bits.append(f"{likely} reconstructed from progress")
    if plex_only:
        bits.append(f"{plex_only} marked played in Plex without progress data")
    if bits:
        body += " " + "; ".join(bits) + "."
    return body


def _poster(t: TitleRollup) -> Dict[str, Any]:
    return {
        "title": t.title,
        "poster_url": t.poster_url,
        "year": t.year,
        "completions": int(t.completions),
        "distinct_days": int(t.distinct_days),
        "is_rewatch": t.is_rewatch,
        "rating_key": t.rating_key,
    }


def _genre_crown(counts: Mapping[str, int]) -> Optional[Dict[str, Any]]:
    ranked = ranked_names(counts, limit=2)
    if not ranked:
        return None
    crown: Dict[str, Any] = {"name": ranked[0]["name"], "count": ranked[0]["count"]}
    if len(ranked) > 1:
        crown["runner_up"] = ranked[1]
    return crown


def _peak_named(counts: Mapping[int, int], labels: Sequence[str]) -> Optional[Tuple[int, int, str]]:
    if not counts:
        return None
    best_key, best_n = max(counts.items(), key=lambda kv: (int(kv[1]), -int(kv[0])))
    if int(best_n) <= 0:
        return None
    idx = int(best_key)
    if idx < 0 or idx >= len(labels):
        return None
    return idx, int(best_n), str(labels[idx])


def build_recap(rollup: YearRollup, ctx: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """First-class linger sheet. Omit beats we cannot honestly compute."""
    del ctx
    movie_crown = _genre_crown(rollup.movie_genre_counts)
    tv_crown = _genre_crown(rollup.tv_genre_counts)
    headline = personality_line(
        movie_genre=str((movie_crown or {}).get("name") or ""),
        tv_genre=str((tv_crown or {}).get("name") or ""),
        year=int(rollup.year),
    )

    hero: List[Dict[str, str]] = [
        {"id": "movies", "value": str(int(rollup.movie_completions)), "label": "movies finished"},
        {
            "id": "episodes",
            "value": str(int(rollup.unique_episodes or rollup.episode_completions)),
            "label": "episodes",
        },
        {
            "id": "shows",
            "value": str(int(rollup.unique_shows)),
            "label": "shows",
        },
    ]
    hours_note = ""
    if rollup.catalog_minutes > 0:
        hero.append(
            {
                "id": "hours",
                "value": format_catalog_hours(rollup.catalog_minutes),
                "label": "hours (catalog runtime)",
            }
        )
        covered = int(rollup.catalog_minutes_coverage)
        total = int(rollup.completion_count)
        hours_note = (
            f"Hours use catalog runtimes for {covered} of {total} finishes — not live progress."
        )

    rewatch = None
    for title in rollup.top_movies:
        if title.is_rewatch:
            rewatch = {
                "title": title.title,
                "days": int(title.distinct_days),
                "poster_url": title.poster_url,
            }
            break

    binge = None
    if rollup.top_shows:
        top_show = rollup.top_shows[0]
        if int(top_show.completions) > 0:
            binge = {
                "title": top_show.title,
                "episodes": int(top_show.completions),
                "poster_url": top_show.poster_url,
            }

    peak = peak_month(dict(rollup.monthly_counts))
    peak_payload = None
    if peak:
        month, count = peak
        peak_payload = {
            "month": month,
            "label": month_label(month),
            "count": int(count),
            "titles": [_poster(t) for t in list(rollup.peak_month_titles or [])[:4]],
        }

    weekday = None
    wd = _peak_named(dict(rollup.weekday_counts), WEEKDAY_NAMES)
    if wd:
        _, count, label = wd
        weekday = {"label": label, "count": count}

    director = None
    directors = ranked_names(rollup.director_counts, limit=1)
    if directors:
        director = directors[0]

    actor = None
    actors = ranked_names(rollup.actor_counts, limit=1)
    if actors:
        actor = actors[0]

    decade = None
    if rollup.movie_decade_counts:
        best_dec, best_n = max(
            rollup.movie_decade_counts.items(),
            key=lambda kv: (int(kv[1]), -int(kv[0])),
        )
        if int(best_n) > 0:
            decade = {"decade": int(best_dec), "label": decade_phrase(int(best_dec)), "count": int(best_n)}

    extras: List[Dict[str, str]] = []
    if weekday:
        extras.append(
            {
                "id": "weekday",
                "label": f"{weekday['label']}s",
                "value": f"{weekday['count']} finishes",
            }
        )
    if director:
        extras.append(
            {
                "id": "director",
                "label": "Most-seen director",
                "value": f"{director['name']} ({director['count']})",
            }
        )
    if actor:
        extras.append(
            {
                "id": "actor",
                "label": "Most-seen actor",
                "value": f"{actor['name']} ({actor['count']})",
            }
        )
    if decade:
        extras.append(
            {
                "id": "decade",
                "label": "Movie decade",
                "value": f"{decade['label']} ({decade['count']})",
            }
        )

    return {
        "headline": headline,
        "hero": hero,
        "movie_genre": movie_crown,
        "tv_genre": tv_crown,
        "top_movies": [_poster(t) for t in list(rollup.top_movies)[:5]],
        "top_shows": [_poster(t) for t in list(rollup.top_shows)[:5]],
        "peak_month": peak_payload,
        "rewatch": rewatch,
        "binge": binge,
        "weekday": weekday,
        "director": director,
        "actor": actor,
        "decade": decade,
        "extras": extras,
        "hours_note": hours_note,
        "honesty_footnote": honesty_footnote(rollup),
        "monthly_counts": {str(k): int(v) for k, v in dict(rollup.monthly_counts).items()},
    }
