"""Chapter builders for the Year in Review cinema reel."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Sequence

from projectionist.watch_tracker.models import YearRollup
from projectionist.watch_tracker.rollups import month_label, peak_month

ChapterBuilder = Callable[[YearRollup, Dict[str, Any]], Optional[Dict[str, Any]]]

MAX_CHAPTERS = 12


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
    return {"title": str(title), "poster_url": url, "year": getattr(t, "year", None) if not isinstance(t, dict) else t.get("year")}


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
            f"Hey {name} — Projectionist kept notes on the finishes we could "
            f"honestly attribute to you. Ready for a short walk through {year}?"
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
        f"You wrapped {n} tracked finish{'es' if n != 1 else ''} this year — "
        f"{movies} movie{'s' if movies != 1 else ''} and {episodes} episode"
        f"{'s' if episodes != 1 else ''}."
    )
    if rollup.sittings_observed > n:
        body += (
            f" Those finishes stretched across about {rollup.sittings_observed} sittings "
            "we could observe."
        )
    return _chapter(
        id="volume",
        kind="volume",
        title="The tally, gently",
        body=body,
        stat_lines=[
            f"{n} tracked completions",
            f"{rollup.unique_titles} distinct titles",
        ],
    )


def build_top_movies(rollup: YearRollup, ctx: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not rollup.top_movies:
        return None
    top = rollup.top_movies[0]
    extras = rollup.top_movies[1:4]
    names = ", ".join(t.title for t in extras) if extras else ""
    body = f"Your most revisited movie finish: {top.title}"
    if top.completions > 1:
        body += f" ({top.completions} tracked completions)"
    body += "."
    if names:
        body += f" Also in the mix: {names}."
    posters = [p for p in (_poster_from_title(t) for t in rollup.top_movies[:4]) if p]
    return _chapter(
        id="top-movies",
        kind="top_movies",
        title="Movies that stuck",
        body=body,
        posters=posters,
    )


def build_tv_depth(rollup: YearRollup, ctx: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not rollup.top_shows or rollup.episode_completions <= 0:
        return None
    top = rollup.top_shows[0]
    body = (
        f"On the series side, {top.title} led with {top.completions} episode "
        f"finish{'es' if top.completions != 1 else ''} we tracked for you."
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
    return _chapter(
        id="monthly-rhythm",
        kind="monthly_rhythm",
        title="A busy month",
        body=(
            f"{month_label(month)} carried the loudest stretch — "
            f"{count} tracked finish{'es' if count != 1 else ''} that month."
        ),
        stat_lines=[f"Peak: {month_label(month)} ({count})"],
    )


def build_ratings(rollup: YearRollup, ctx: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    ratings = ctx.get("ratings") or []
    if not ratings:
        return None
    top = ratings[0]
    title = str(top.get("title") or "a favorite")
    stars = top.get("stars")
    body = f"You left a {stars}-star note on {title}." if stars else f"You rated {title}."
    if len(ratings) > 1:
        body += f" Plus {len(ratings) - 1} more rating{'s' if len(ratings) != 2 else ''} this year."
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
    body = (
        "A word on honesty: these numbers are tracked completions for you — "
        "not household Plex totals, and not proof you sat through every frame uninterrupted."
    )
    bits = []
    if certain:
        bits.append(f"{certain} observed crossing the finish line")
    if likely:
        bits.append(f"{likely} reconstructed as likely finishes")
    if plex_only:
        bits.append(f"{plex_only} Plex played events without enough progress evidence")
    if bits:
        body += " Breakdown: " + "; ".join(bits) + "."
    return _chapter(
        id="honesty",
        kind="honesty",
        title="How we counted",
        body=body,
        shareable=False,
        duration_ms=7000,
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
