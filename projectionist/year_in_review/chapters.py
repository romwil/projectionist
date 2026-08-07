"""Chapter builders for the Year in Review cinema reel."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Sequence

from projectionist.watch_tracker.models import TitleRollup, YearRollup
from projectionist.watch_tracker.rollups import month_label, peak_month

ChapterBuilder = Callable[[YearRollup, Dict[str, Any]], Optional[Dict[str, Any]]]

MAX_CHAPTERS = 12
BUSY_MONTH_TITLE_SHOW = 4


def _chapter(
    *,
    id: str,
    kind: str,
    title: str,
    body: str,
    stat_lines: Optional[List[str]] = None,
    posters: Optional[List[Dict[str, Any]]] = None,
    shareable: bool = True,
    duration_ms: int = 5500,
) -> Dict[str, Any]:
    return {
        "id": id,
        "kind": kind,
        "title": title,
        "body": body,
        "stat_lines": list(stat_lines or []),
        "posters": list(posters or []),
        "shareable": shareable,
        "duration_ms": duration_ms,
    }


def _poster_from_title(t: Any) -> Optional[Dict[str, Any]]:
    if not t:
        return None
    url = getattr(t, "poster_url", None) or (t.get("poster_url") if isinstance(t, dict) else None)
    title = getattr(t, "title", None) or (t.get("title") if isinstance(t, dict) else None)
    if not title:
        return None
    return {
        "title": str(title),
        "poster_url": url,
        "year": getattr(t, "year", None) if not isinstance(t, dict) else t.get("year"),
    }


def _join_titles(titles: Sequence[str]) -> str:
    clean = [t for t in titles if t]
    if not clean:
        return ""
    if len(clean) == 1:
        return clean[0]
    if len(clean) == 2:
        return f"{clean[0]} and {clean[1]}"
    return ", ".join(clean[:-1]) + f", and {clean[-1]}"


def build_overture(rollup: YearRollup, ctx: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if rollup.completion_count <= 0:
        return None
    name = str(ctx.get("display_name") or "friend").strip() or "friend"
    year = rollup.year
    return _chapter(
        id="overture",
        kind="overture",
        title=f"{year}, on your screen",
        body=(
            f"Hey {name} — here’s a short walk through the finishes we could "
            f"attribute to you in {year}."
        ),
        duration_ms=6000,
    )


def build_volume(rollup: YearRollup, ctx: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if rollup.completion_count <= 0:
        return None
    n = rollup.completion_count
    movies = rollup.movie_completions
    episodes = rollup.episode_completions
    body = (
        f"You wrapped {n} finish{'es' if n != 1 else ''} this year — "
        f"{movies} movie{'s' if movies != 1 else ''} and {episodes} episode"
        f"{'s' if episodes != 1 else ''}."
    )
    return _chapter(
        id="volume",
        kind="volume",
        title="The tally, gently",
        body=body,
        stat_lines=[
            f"{n} finishes",
            f"{rollup.unique_titles} distinct titles",
        ],
    )


def build_top_movies(rollup: YearRollup, ctx: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not rollup.top_movies:
        return None
    rewatched = [t for t in rollup.top_movies if t.is_rewatch]
    if rewatched:
        top = rewatched[0]
        extras = [t for t in rewatched[1:4]]
        body = (
            f"You finished {top.title} on {top.distinct_days} different days "
            f"this year — a real rewatch, not a pause and resume."
        )
        if extras:
            body += f" Also back more than once: {_join_titles([t.title for t in extras])}."
        posters = [p for p in (_poster_from_title(t) for t in rewatched[:4]) if p]
        return _chapter(
            id="top-movies",
            kind="top_movies",
            title="Movies that stuck",
            body=body,
            posters=posters,
        )

    # No multi-day rewatches — showcase finishes without inventing affection.
    showcase = list(rollup.top_movies[:4])
    names = _join_titles([t.title for t in showcase])
    body = f"Among the movie finishes we tracked: {names}."
    posters = [p for p in (_poster_from_title(t) for t in showcase) if p]
    return _chapter(
        id="top-movies",
        kind="top_movies",
        title="Movies you finished",
        body=body,
        posters=posters,
    )


def build_tv_depth(rollup: YearRollup, ctx: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not rollup.top_shows or rollup.episode_completions <= 0:
        return None
    top = rollup.top_shows[0]
    body = (
        f"On the series side, {top.title} led with {top.completions} episode "
        f"finish{'es' if top.completions != 1 else ''}."
    )
    if rollup.unique_episodes:
        body += f" Across everything, that’s {rollup.unique_episodes} unique episodes."
    posters = [p for p in (_poster_from_title(t) for t in rollup.top_shows[:4]) if p]
    return _chapter(
        id="tv-depth",
        kind="tv_depth",
        title="Series nights",
        body=body,
        posters=posters,
    )


def build_monthly_rhythm(rollup: YearRollup, ctx: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    peak = peak_month(dict(rollup.monthly_counts))
    if not peak:
        return None
    month, count = peak
    if count <= 0:
        return None
    highlights: Sequence[TitleRollup] = list(rollup.peak_month_titles or [])
    shown = list(highlights[:BUSY_MONTH_TITLE_SHOW])
    label = month_label(month)
    body = f"{label} was your busiest stretch — {count} finish{'es' if count != 1 else ''}."
    if shown:
        names = _join_titles([t.title for t in shown])
        body += f" In the mix: {names}."
        remaining = max(0, len(highlights) - len(shown))
        if remaining > 0:
            body += f" And {remaining} more."
    posters = [p for p in (_poster_from_title(t) for t in shown) if p]
    return _chapter(
        id="monthly-rhythm",
        kind="monthly_rhythm",
        title="A busy month",
        body=body,
        posters=posters,
        stat_lines=[f"{label}: {count} finishes"],
    )


def build_ratings(rollup: YearRollup, ctx: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    ratings = ctx.get("ratings") or []
    if not ratings:
        return None
    sources = ctx.get("ratings_sources") or {}
    has_proj = bool(sources.get("projectionist"))
    has_plex = bool(sources.get("plex"))
    plex_available = bool(sources.get("plex_available"))

    top = ratings[0]
    title = str(top.get("title") or "a favorite")
    stars = top.get("stars")
    source = str(top.get("source") or "projectionist")
    if source == "plex":
        body = (
            f"Plex shows a {stars}-star rating on {title}."
            if stars is not None
            else f"Plex has a star rating on {title}."
        )
    else:
        body = (
            f"You left a {stars}-star note on {title} in Projectionist."
            if stars is not None
            else f"You rated {title} in Projectionist."
        )
    extra = len(ratings) - 1
    if extra > 0:
        body += f" Plus {extra} more this year."

    if has_proj and has_plex:
        body += " Mix of Projectionist notes and Plex stars on titles you finished."
    elif has_proj and not has_plex:
        if plex_available:
            body += " Projectionist notes only — Plex stars aren’t dated, so we skip undated ones."
        else:
            body += " Projectionist notes only (no Plex library stars synced yet)."
    elif has_plex and not has_proj:
        body += " Plex library stars on titles you finished (Plex doesn’t date ratings)."

    return _chapter(
        id="ratings",
        kind="ratings",
        title="Stars you meant",
        body=body,
        shareable=True,
    )


def build_shares(rollup: YearRollup, ctx: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    given = int(ctx.get("shares_given") or 0)
    received = int(ctx.get("shares_received") or 0)
    if given <= 0 and received <= 0:
        return None
    parts = []
    if given:
        parts.append(f"you passed along {given} title{'s' if given != 1 else ''}")
    if received:
        parts.append(f"friends sent you {received}")
    return _chapter(
        id="shares",
        kind="shares",
        title="Passed along",
        body="This year " + " and ".join(parts) + " — the household grapevine, quietly working.",
    )


def build_live(rollup: YearRollup, ctx: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    live_sessions = int(ctx.get("live_sessions") or 0)
    if live_sessions <= 0:
        return None
    return _chapter(
        id="live",
        kind="live",
        title="Live nights",
        body=(
            f"You tuned into Live about {live_sessions} time"
            f"{'s' if live_sessions != 1 else ''} — channels as a living room, not a queue."
        ),
    )


def build_honesty(rollup: YearRollup, ctx: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if rollup.completion_count <= 0:
        return None
    c = rollup.confidence
    certain = int(c.get("certain") or 0)
    likely = int(c.get("likely") or 0)
    plex_only = int(c.get("plex_event_only") or 0)

    body = "We counted finishes attributed to you — not everyone else’s Plex plays."
    bits: List[str] = []
    if certain:
        bits.append(f"{certain} with live progress")
    if likely:
        bits.append(f"{likely} reconstructed from progress")
    if plex_only:
        bits.append(f"{plex_only} marked played in Plex without progress data")
    if bits:
        body += " " + "; ".join(bits) + "."
    return _chapter(
        id="honesty",
        kind="honesty",
        title="How we counted",
        body=body,
        shareable=False,
        duration_ms=5500,
    )


def build_closing(rollup: YearRollup, ctx: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if rollup.completion_count <= 0:
        return None
    name = str(ctx.get("display_name") or "friend").strip() or "friend"
    return _chapter(
        id="closing",
        kind="closing",
        title="Lights up",
        body=(
            f"That’s your {rollup.year}, {name}. Whenever you’re ready for the next reel, "
            "the curator’s still in the booth."
        ),
        duration_ms=6500,
    )


CORE_BUILDERS: Sequence[ChapterBuilder] = (
    build_overture,
    build_volume,
    build_top_movies,
    build_tv_depth,
    build_monthly_rhythm,
)

OPTIONAL_BUILDERS: Sequence[ChapterBuilder] = (
    build_ratings,
    build_shares,
    build_live,
)

CLOSING_BUILDERS: Sequence[ChapterBuilder] = (
    build_honesty,
    build_closing,
)


def assemble_chapters(rollup: YearRollup, ctx: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Run the chapter registry; skip empties; cap length."""
    context = dict(ctx or {})
    chapters: List[Dict[str, Any]] = []
    for builder in CORE_BUILDERS:
        ch = builder(rollup, context)
        if ch:
            chapters.append(ch)
    for builder in OPTIONAL_BUILDERS:
        if len(chapters) >= MAX_CHAPTERS - len(CLOSING_BUILDERS):
            break
        ch = builder(rollup, context)
        if ch:
            chapters.append(ch)
    for builder in CLOSING_BUILDERS:
        ch = builder(rollup, context)
        if ch:
            chapters.append(ch)
    return chapters[:MAX_CHAPTERS]
