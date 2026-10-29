"""Idle task: collection gap analysis via TMDB.

Identifies the most-represented directors in the library, queries TMDB for
their complete filmographies, and highlights titles missing from the local
collection.  This helps the owner discover gaps like "you have 4 of Denis
Villeneuve's 10 films."

Results are cached in a ``cached_gap_analysis`` table.

Only runs when ``tmdb_api_key`` is configured.  Default interval: 168 hours
(weekly).
"""

from __future__ import annotations

import json
import logging
import time
from collections import Counter
from typing import Any, Callable, Dict, List, Set

from projectionist.config_store import Settings
from projectionist.library.db import Database
from projectionist.scheduler.engine import IdleScheduler
from projectionist.scheduler.tasks.base_augmentation import register_severity_task
from projectionist.scheduler.tasks.kinship_augmentation import (
    KinshipMissAugmentationTask,
    stage_kinship_demand,
    with_stage_stats,
)
from projectionist.telemetry.kinship_miss import preferred_item_ids

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 604800  # 168 hours / 1 week
TOP_DIRECTORS = 10
MIN_DIRECTOR_TITLES = 2
TASK_NAME = "gap_analysis"


class GapAnalysisAugmentation(KinshipMissAugmentationTask):
    """Consume kinship-miss demand to prioritize directors; do not stage a flood."""

    action = "analyze_director_gaps"
    stage_when_needed = False

    def __init__(self, db: Database) -> None:
        super().__init__(db, task_name=TASK_NAME)


def _ensure_table(db: Database) -> None:
    with db.connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cached_gap_analysis (
                analysis_key TEXT PRIMARY KEY,
                results_json TEXT NOT NULL,
                generated_at TEXT NOT NULL
            )
            """
        )


def _get_tmdb_director_filmography(
    tmdb_api_key: str, person_name: str
) -> List[Dict[str, Any]]:
    """Search TMDB for a director and return their movie filmography."""
    import urllib.request
    import urllib.parse

    base = "https://api.themoviedb.org/3"
    headers = {"Authorization": f"Bearer {tmdb_api_key}"} if tmdb_api_key.startswith("ey") else {}
    query_params = urllib.parse.urlencode({"api_key": tmdb_api_key, "query": person_name})

    try:
        search_url = f"{base}/search/person?{query_params}"
        req = urllib.request.Request(search_url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        results = data.get("results", [])
        if not results:
            return []

        person_id = results[0]["id"]
        credits_url = f"{base}/person/{person_id}/movie_credits?api_key={tmdb_api_key}"
        req = urllib.request.Request(credits_url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            credits = json.loads(resp.read())

        crew = credits.get("crew", [])
        directed = [
            {
                "tmdb_id": int(c["id"]),
                "title": str(c.get("title", "")),
                "year": str(c.get("release_date", ""))[:4] if c.get("release_date") else None,
            }
            for c in crew
            if str(c.get("job", "")).lower() == "director"
        ]
        return directed

    except Exception as exc:
        logger.debug("TMDB filmography lookup for '%s' failed: %s", person_name, exc)
        return []


def _directors_from_row(row: Any) -> List[str]:
    directors_raw = row["directors"] if "directors" in row.keys() else []
    try:
        directors = json.loads(directors_raw) if isinstance(directors_raw, str) else []
    except (json.JSONDecodeError, TypeError):
        directors = []
    if not isinstance(directors, list):
        return []
    return [str(name).strip() for name in directors if str(name).strip()]


async def run(
    db: Database, settings: Settings, should_stop: Callable[[], bool]
) -> Dict[str, Any]:
    augmenter = GapAnalysisAugmentation(db)
    stage_stats, interrupted = await stage_kinship_demand(augmenter, should_stop)
    if interrupted:
        return with_stage_stats({"status": "interrupted", "directors_analyzed": 0}, stage_stats)

    if not settings.tmdb_api_key:
        return with_stage_stats(
            {"status": "skipped", "reason": "TMDB not configured"},
            stage_stats,
        )

    _ensure_table(db)
    rows = list(db.all_library_items())
    if not rows:
        return with_stage_stats(
            {"status": "completed", "directors_analyzed": 0},
            stage_stats,
        )

    # Build director frequency and library TMDB ID sets.
    director_counter: Counter[str] = Counter()
    library_tmdb_ids: Set[int] = set()
    for row in rows:
        if row["tmdb_id"] is not None:
            library_tmdb_ids.add(int(row["tmdb_id"]))
        for name in _directors_from_row(row):
            director_counter[name] += 1

    top_directors = [
        name
        for name, count in director_counter.most_common(TOP_DIRECTORS)
        if count >= MIN_DIRECTOR_TITLES
    ]
    demand_directors: List[str] = []
    seen_directors: Set[str] = set()
    for item_id in preferred_item_ids(db, limit=25):
        item = db.library_item_by_id(int(item_id))
        if item is None:
            continue
        for name in _directors_from_row(item):
            if name in seen_directors or name not in director_counter:
                continue
            seen_directors.add(name)
            demand_directors.append(name)
    ordered_directors: List[str] = []
    seen_order: Set[str] = set()
    for name in [*demand_directors, *top_directors]:
        if name in seen_order:
            continue
        seen_order.add(name)
        ordered_directors.append(name)
        if len(ordered_directors) >= TOP_DIRECTORS:
            break

    if should_stop():
        return with_stage_stats(
            {"status": "interrupted", "directors_analyzed": 0},
            stage_stats,
        )

    gaps: List[Dict[str, Any]] = []
    directors_analyzed = 0

    for director in ordered_directors:
        if should_stop():
            break

        filmography = _get_tmdb_director_filmography(settings.tmdb_api_key, director)
        if not filmography:
            continue

        missing = [
            movie
            for movie in filmography
            if movie["tmdb_id"] not in library_tmdb_ids
        ]

        if missing:
            gaps.append(
                {
                    "director": director,
                    "in_library": len(filmography) - len(missing),
                    "total_films": len(filmography),
                    "missing": missing[:20],
                }
            )
        directors_analyzed += 1

    with db.connect() as conn:
        conn.execute(
            """
            INSERT INTO cached_gap_analysis (analysis_key, results_json, generated_at)
            VALUES ('director_gaps', ?, ?)
            ON CONFLICT(analysis_key) DO UPDATE SET
                results_json = excluded.results_json,
                generated_at = excluded.generated_at
            """,
            (json.dumps(gaps), str(time.time())),
        )

    logger.info(
        "Gap analysis: analyzed %d directors, found %d with gaps",
        directors_analyzed,
        len(gaps),
    )
    return with_stage_stats(
        {
            "status": "completed",
            "directors_analyzed": directors_analyzed,
            "gaps_found": len(gaps),
            "demand_prioritized": len(demand_directors),
        },
        stage_stats,
    )


def register(scheduler: IdleScheduler) -> None:
    register_severity_task(
        scheduler,
        name=TASK_NAME,
        priority="P2",
        run_fn=run,
        run_interval_seconds=INTERVAL_SECONDS,
        enabled=True,
        off_loop=True,
        description=(
            "Looks up TMDB filmographies for your most-represented directors and "
            "caches collection gaps (titles you’re missing). Requires a TMDB API key; "
            "runs weekly by default."
        ),
    )
