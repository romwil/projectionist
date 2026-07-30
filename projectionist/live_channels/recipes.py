"""Channel recipe types and youth-safe playlist helpers.

Recipes describe *intent* Projectionist will later publish to Tunarr
(channels + programming + optional filler-lists). Pure data + filters —
no HTTP here.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from projectionist.youth.rating_gate import (
    filter_items_for_youth,
    resolve_youth_max_rating,
)


class ProgrammingMode(str, Enum):
    """How titles are ordered on the station.

    Maps toward Tunarr programming / schedule-slots:
    - sequential → ordered lineup
    - shuffle / chaos → random slot schedule
    """

    SEQUENTIAL = "sequential"
    SHUFFLE = "shuffle"
    CHAOS = "chaos"


class MediaScope(str, Enum):
    """Which library types a station may air."""

    TV = "tv"
    MOVIES = "movies"
    BOTH = "both"


def normalize_media_scope(value: Any, *, default: str = MediaScope.BOTH.value) -> str:
    """Normalize craft/API scope strings to ``tv`` | ``movies`` | ``both``."""
    raw = str(value or "").strip().lower()
    if raw in {MediaScope.TV.value, "shows", "show", "episodes", "episode", "series"}:
        return MediaScope.TV.value
    if raw in {MediaScope.MOVIES.value, "movie", "film", "films"}:
        return MediaScope.MOVIES.value
    if raw in {MediaScope.BOTH.value, "all", "any", "mixed"}:
        return MediaScope.BOTH.value
    return str(default or MediaScope.BOTH.value)


def library_type_matches_scope(media_type: Any, scope: Any) -> bool:
    """True when a Tunarr/Plex library mediaType is allowed for ``scope``."""
    scope_n = normalize_media_scope(scope)
    mt = str(media_type or "").strip().lower()
    if scope_n == MediaScope.BOTH.value:
        return mt in {"movies", "movie", "shows", "show"}
    if scope_n == MediaScope.TV.value:
        return mt in {"shows", "show"}
    if scope_n == MediaScope.MOVIES.value:
        return mt in {"movies", "movie"}
    return True


def program_type_matches_scope(program_type: Any, scope: Any) -> bool:
    """True when a Tunarr program type is allowed for ``scope``."""
    scope_n = normalize_media_scope(scope)
    pt = str(program_type or "").strip().lower()
    if scope_n == MediaScope.BOTH.value:
        return True
    if scope_n == MediaScope.TV.value:
        return pt in {"episode", "show", "season"} or not pt
    if scope_n == MediaScope.MOVIES.value:
        return pt in {"movie"} or not pt
    return True


def collection_media_type_matches_scope(media_type: Any, scope: Any) -> bool:
    """Plex collection media_type uses movie/show; map to scope."""
    scope_n = normalize_media_scope(scope)
    mt = str(media_type or "").strip().lower()
    if not mt or scope_n == MediaScope.BOTH.value:
        return True
    if scope_n == MediaScope.TV.value:
        return mt in {"show", "shows", "episode", "tv"}
    if scope_n == MediaScope.MOVIES.value:
        return mt in {"movie", "movies"}
    return True


@dataclass(frozen=True)
class ChannelRecipe:
    """A proposed or published Live Channel station."""

    name: str
    number: int
    source: str  # taste_cluster | motif | collection | chaos | youth
    programming_mode: ProgrammingMode = ProgrammingMode.SHUFFLE
    media_scope: str = MediaScope.BOTH.value
    cluster_tag: str = ""
    motif: str = ""
    collection_id: str = ""
    collection_title: str = ""
    youth_safe: bool = False
    summary: str = ""
    item_hints: tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["programming_mode"] = self.programming_mode.value
        payload["media_scope"] = normalize_media_scope(self.media_scope)
        payload["item_hints"] = list(self.item_hints)
        return payload


def apply_youth_gate_to_items(
    items: Sequence[Mapping[str, Any]] | Iterable[Mapping[str, Any]],
    *,
    settings: Any = None,
    max_rating: Optional[str] = None,
    rating_key: str = "content_rating",
) -> List[Dict[str, Any]]:
    """Filter playlist candidates with the existing youth rating gate.

    Prefer an explicit ``max_rating``; otherwise resolve from ``settings.youth``.
    """
    ceiling = str(max_rating or "").strip()
    if not ceiling and settings is not None:
        ceiling = resolve_youth_max_rating(settings)
    if not ceiling:
        return [dict(item) for item in items if isinstance(item, Mapping)]
    return filter_items_for_youth(items, max_rating=ceiling, rating_key=rating_key)


def recipe_from_mapping(data: Mapping[str, Any]) -> ChannelRecipe:
    """Build a recipe from a plain dict (API / tests)."""
    mode_raw = str(data.get("programming_mode") or ProgrammingMode.SHUFFLE.value).lower()
    try:
        mode = ProgrammingMode(mode_raw)
    except ValueError:
        mode = ProgrammingMode.SHUFFLE
    hints = data.get("item_hints") or ()
    if isinstance(hints, str):
        hint_tuple = (hints,)
    else:
        hint_tuple = tuple(str(h) for h in hints if str(h).strip())
    return ChannelRecipe(
        name=str(data.get("name") or "Untitled").strip() or "Untitled",
        number=int(data.get("number") or 0),
        source=str(data.get("source") or "chaos").strip() or "chaos",
        programming_mode=mode,
        media_scope=normalize_media_scope(data.get("media_scope")),
        cluster_tag=str(data.get("cluster_tag") or "").strip(),
        motif=str(data.get("motif") or "").strip(),
        collection_id=str(data.get("collection_id") or "").strip(),
        collection_title=str(data.get("collection_title") or "").strip(),
        youth_safe=bool(data.get("youth_safe")),
        summary=str(data.get("summary") or "").strip(),
        item_hints=hint_tuple,
    )
