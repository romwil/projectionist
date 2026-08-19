"""Normalized watch-tracker contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, Sequence

MediaType = Literal["movie", "episode"]
Confidence = Literal["certain", "likely", "plex_event_only"]

SOURCE_EVENT_KINDS = frozenset(
    {
        "history_played",
        "session_progress",
        "session_pause",
        "session_stop",
        "plex_scrobble",
        "manual_scrobble",
        "manual_unscrobble",
        "tautulli_history",
    }
)


@dataclass(frozen=True)
class WatchEventInput:
    source: str
    source_event_kind: str
    server_machine_id: str
    source_user_key: str
    rating_key: str
    media_type: MediaType
    occurred_at_ms: int
    source_event_id: Optional[str] = None
    parent_rating_key: Optional[str] = None
    client_key: Optional[str] = None
    session_key: Optional[str] = None
    progress_ms: Optional[int] = None
    duration_ms: Optional[int] = None
    terminal: bool = False
    manual: bool = False


@dataclass
class IngestResult:
    fetched: int = 0
    inserted: int = 0
    deduped: int = 0
    mapped: int = 0
    unmapped: int = 0
    event_ids: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "fetched": self.fetched,
            "inserted": self.inserted,
            "deduped": self.deduped,
            "mapped": self.mapped,
            "unmapped": self.unmapped,
        }


@dataclass(frozen=True)
class TitleRollup:
    rating_key: str
    media_type: MediaType
    parent_rating_key: Optional[str]
    title: str
    year: Optional[int]
    poster_url: Optional[str]
    completions: int
    confidence: Dict[str, int]
    last_completed_at_ms: int
    # Distinct UTC calendar days with a finish — not raw completion rows
    # (pause/restart fragments of one sitting collapse to one day).
    distinct_days: int = 1

    @property
    def is_rewatch(self) -> bool:
        """True only when finishes landed on ≥2 distinct calendar days."""
        return int(self.distinct_days) >= 2


@dataclass(frozen=True)
class YearRollup:
    user_id: str
    year: int
    completion_count: int
    movie_completions: int
    episode_completions: int
    unique_titles: int
    unique_episodes: int
    sittings_observed: int
    confidence: Dict[str, int]
    top_movies: Sequence[TitleRollup]
    top_shows: Sequence[TitleRollup]
    monthly_counts: Dict[int, int]  # 1-12
    peak_month_titles: Sequence[TitleRollup]
    first_completion_at_ms: Optional[int]
    last_completion_at_ms: Optional[int]
    has_enough_data: bool
    unique_movies: int = 0
    unique_shows: int = 0
    catalog_minutes: int = 0
    catalog_minutes_coverage: int = 0
    movie_genre_counts: Dict[str, int] = field(default_factory=dict)
    tv_genre_counts: Dict[str, int] = field(default_factory=dict)
    weekday_counts: Dict[int, int] = field(default_factory=dict)
    director_counts: Dict[str, int] = field(default_factory=dict)
    actor_counts: Dict[str, int] = field(default_factory=dict)
    movie_decade_counts: Dict[int, int] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        def _title(t: TitleRollup) -> Dict[str, Any]:
            return {
                "rating_key": t.rating_key,
                "media_type": t.media_type,
                "parent_rating_key": t.parent_rating_key,
                "title": t.title,
                "year": t.year,
                "poster_url": t.poster_url,
                "completions": t.completions,
                "confidence": dict(t.confidence),
                "last_completed_at_ms": t.last_completed_at_ms,
                "distinct_days": int(t.distinct_days),
                "is_rewatch": t.is_rewatch,
            }

        return {
            "user_id": self.user_id,
            "year": self.year,
            "completion_count": self.completion_count,
            "movie_completions": self.movie_completions,
            "episode_completions": self.episode_completions,
            "unique_titles": self.unique_titles,
            "unique_episodes": self.unique_episodes,
            "sittings_observed": self.sittings_observed,
            "confidence": dict(self.confidence),
            "top_movies": [_title(t) for t in self.top_movies],
            "top_shows": [_title(t) for t in self.top_shows],
            "monthly_counts": {str(k): v for k, v in self.monthly_counts.items()},
            "peak_month_titles": [_title(t) for t in self.peak_month_titles],
            "first_completion_at_ms": self.first_completion_at_ms,
            "last_completion_at_ms": self.last_completion_at_ms,
            "has_enough_data": self.has_enough_data,
            "unique_movies": int(self.unique_movies),
            "unique_shows": int(self.unique_shows),
            "catalog_minutes": int(self.catalog_minutes),
            "catalog_minutes_coverage": int(self.catalog_minutes_coverage),
            "movie_genre_counts": dict(self.movie_genre_counts),
            "tv_genre_counts": dict(self.tv_genre_counts),
            "weekday_counts": {str(k): v for k, v in self.weekday_counts.items()},
            "director_counts": dict(self.director_counts),
            "actor_counts": dict(self.actor_counts),
            "movie_decade_counts": {str(k): v for k, v in self.movie_decade_counts.items()},
        }
