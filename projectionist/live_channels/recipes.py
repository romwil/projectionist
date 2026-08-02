"""Channel recipe types and youth-safe playlist helpers.

Recipes describe *intent* Projectionist will later publish to Tunarr
(channels + programming + optional filler-lists). Pure data + filters —
no HTTP here.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from projectionist.youth.rating_gate import (
    filter_items_for_youth,
    resolve_youth_max_rating,
)


class ProgrammingMode(str, Enum):
    """How titles are ordered on the station.

    - sequential → preserve collection / hint order
    - shuffle → randomize within this station's resolved pool

    ``chaos`` remains a deprecated wire value for one release; callers should
    use :func:`normalize_programming_mode`, which maps it to ``shuffle``.
    """

    SEQUENTIAL = "sequential"
    SHUFFLE = "shuffle"
    CHAOS = "chaos"  # deprecated alias of SHUFFLE


def normalize_programming_mode(value: Any, *, default: ProgrammingMode = ProgrammingMode.SHUFFLE) -> ProgrammingMode:
    """Normalize API / station_meta mode strings; Chaos → Shuffle."""
    if isinstance(value, ProgrammingMode):
        return ProgrammingMode.SHUFFLE if value == ProgrammingMode.CHAOS else value
    if value is None or value == "":
        return default
    raw = str(getattr(value, "value", value) or "").strip().lower()
    # Guard against str(EnumMember) → "ProgrammingMode.SEQUENTIAL".
    if "." in raw:
        raw = raw.rsplit(".", 1)[-1]
    if raw in {ProgrammingMode.CHAOS.value, "chaos"}:
        return ProgrammingMode.SHUFFLE
    if raw in {ProgrammingMode.SEQUENTIAL.value, "sequential", "seq", "ordered"}:
        return ProgrammingMode.SEQUENTIAL
    if raw in {ProgrammingMode.SHUFFLE.value, "shuffle", "random"}:
        return ProgrammingMode.SHUFFLE
    return default


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
    source: str  # taste_cluster | motif | collection | youth | chaos (legacy)
    programming_mode: ProgrammingMode = ProgrammingMode.SHUFFLE
    media_scope: str = MediaScope.BOTH.value
    cluster_tag: str = ""
    motif: str = ""
    collection_id: str = ""
    collection_title: str = ""
    youth_safe: bool = False
    summary: str = ""
    item_hints: tuple[str, ...] = ()
    # Plex ratingKeys for collection children (preferred over title hints).
    item_rating_keys: tuple[str, ...] = ()
    # Additive AND filters (genres ∩ decade ∩ motif/theme ∩ rating).
    craft_filters: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["programming_mode"] = self.programming_mode.value
        payload["media_scope"] = normalize_media_scope(self.media_scope)
        payload["item_hints"] = list(self.item_hints)
        payload["item_rating_keys"] = list(self.item_rating_keys)
        payload["craft_filters"] = dict(self.craft_filters or {})
        return payload


def recipe_is_youth_safe(recipe: Any) -> bool:
    """True when a recipe must fail-closed on content ratings during fill/refill."""
    if recipe is None:
        return False
    if bool(getattr(recipe, "youth_safe", False)):
        return True
    if isinstance(recipe, Mapping) and bool(recipe.get("youth_safe")):
        return True
    source = str(
        getattr(recipe, "source", None)
        if not isinstance(recipe, Mapping)
        else recipe.get("source")
        or ""
    ).strip().lower()
    return source == "youth"


def resolve_recipe_youth_max_rating(
    recipe: Any = None,
    *,
    settings: Any = None,
    max_rating: Optional[str] = None,
) -> str:
    """Ceiling for youth-safe stations (explicit → settings → PG-13 default)."""
    del recipe  # reserved for per-station ceilings later
    ceiling = str(max_rating or "").strip()
    if ceiling:
        return ceiling
    return resolve_youth_max_rating(settings)


def apply_youth_gate_to_items(
    items: Sequence[Mapping[str, Any]] | Iterable[Mapping[str, Any]],
    *,
    settings: Any = None,
    max_rating: Optional[str] = None,
    rating_key: str = "content_rating",
) -> List[Dict[str, Any]]:
    """Filter playlist candidates with the existing youth rating gate.

    Prefer an explicit ``max_rating``; otherwise resolve from ``settings.youth``.
    Live Channels youth-safe fill must pass an explicit ceiling (see
    :func:`resolve_recipe_youth_max_rating`) so this never fails open there.
    """
    ceiling = str(max_rating or "").strip()
    if not ceiling and settings is not None:
        ceiling = resolve_youth_max_rating(settings)
    if not ceiling:
        return [dict(item) for item in items if isinstance(item, Mapping)]
    return filter_items_for_youth(items, max_rating=ceiling, rating_key=rating_key)


def replace_recipe(recipe: "ChannelRecipe", **updates: Any) -> "ChannelRecipe":
    """Return a new recipe with selected fields replaced."""
    payload = recipe.to_dict()
    payload.update(updates)
    return recipe_from_mapping(payload)


def recipe_from_mapping(data: Mapping[str, Any]) -> ChannelRecipe:
    """Build a recipe from a plain dict (API / tests)."""
    mode = normalize_programming_mode(
        data.get("programming_mode"), default=ProgrammingMode.SHUFFLE
    )
    hints = data.get("item_hints") or ()
    if isinstance(hints, str):
        hint_tuple = (hints,)
    else:
        hint_tuple = tuple(str(h) for h in hints if str(h).strip())
    keys = data.get("item_rating_keys") or ()
    if isinstance(keys, str):
        key_tuple = (keys,) if keys.strip() else ()
    else:
        key_tuple = tuple(str(k) for k in keys if str(k).strip())
    from projectionist.live_channels.filters import normalize_craft_filters

    craft_filters = normalize_craft_filters(
        data.get("craft_filters") or data.get("filters")
    ).to_dict()
    # Source motif also feeds the additive motif stack when filters omit it.
    if not craft_filters.get("motifs") and str(data.get("motif") or "").strip():
        craft_filters["motifs"] = [str(data.get("motif")).strip()]
    source = str(data.get("source") or "motif").strip().lower() or "motif"
    # Legacy Chaos stations refill as Shuffle of the media_scope pool.
    if source == "chaos" and mode == ProgrammingMode.CHAOS:
        mode = ProgrammingMode.SHUFFLE
    return ChannelRecipe(
        name=str(data.get("name") or "Untitled").strip() or "Untitled",
        number=int(data.get("number") or 0),
        source=source,
        programming_mode=mode,
        media_scope=normalize_media_scope(data.get("media_scope")),
        cluster_tag=str(data.get("cluster_tag") or "").strip(),
        motif=str(data.get("motif") or "").strip(),
        collection_id=str(data.get("collection_id") or "").strip(),
        collection_title=str(data.get("collection_title") or "").strip(),
        youth_safe=bool(data.get("youth_safe")) or source == "youth",
        summary=str(data.get("summary") or "").strip(),
        item_hints=hint_tuple,
        item_rating_keys=key_tuple,
        craft_filters=craft_filters,
    )
