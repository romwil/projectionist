"""Library-aware starter channel proposals (2–4 stations).

Uses taste clusters, motifs, and published collections when available.
Gracefully returns an empty / chaos-only pack when the DB has no signal.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

from projectionist.live_channels.recipes import ChannelRecipe, MediaScope, ProgrammingMode


# Virtual channel numbers — sit above typical OTA HDHomeRun ranges.
_BASE_CHANNEL_NUMBER = 100


def propose_starter_pack(
    *,
    taste_clusters: Optional[Sequence[Mapping[str, Any]]] = None,
    motifs: Optional[Sequence[Mapping[str, Any]]] = None,
    collections: Optional[Sequence[Mapping[str, Any]]] = None,
    include_chaos: bool = True,
    include_youth_safe: bool = True,
    max_channels: int = 4,
    youth_max_rating: str = "PG-13",
) -> Dict[str, Any]:
    """Propose 2–4 starter recipes from library signals.

    All inputs are optional plain mappings so callers (API, tests) stay free of
    DB coupling. Empty inputs → empty proposals (plus optional Chaos).
    """
    capped = max(1, min(int(max_channels), 6))
    recipes: List[ChannelRecipe] = []
    used_names: set[str] = set()

    def _add(recipe: ChannelRecipe) -> None:
        if len(recipes) >= capped:
            return
        key = recipe.name.strip().lower()
        if key in used_names:
            return
        used_names.add(key)
        recipes.append(recipe)

    for cluster in _sorted_clusters(taste_clusters or ()):
        tag = str(cluster.get("cluster_tag") or cluster.get("tag") or "").strip()
        if not tag:
            continue
        weight = float(cluster.get("weight") or 0)
        _add(
            ChannelRecipe(
                name=_station_name(tag),
                number=_BASE_CHANNEL_NUMBER + len(recipes),
                source="taste_cluster",
                programming_mode=ProgrammingMode.SHUFFLE,
                media_scope=MediaScope.BOTH.value,
                cluster_tag=tag,
                summary=f"Shuffle station from your “{tag}” taste cluster"
                + (f" (weight {weight:.2f})" if weight else ""),
            )
        )
        if len(recipes) >= max(1, capped - 2):
            break

    for motif_row in _sorted_motifs(motifs or ()):
        if len(recipes) >= capped - (1 if include_chaos else 0) - (1 if include_youth_safe else 0):
            break
        value = str(motif_row.get("value") or motif_row.get("motif") or "").strip()
        if not value:
            continue
        count = int(motif_row.get("count") or motif_row.get("cnt") or 0)
        _add(
            ChannelRecipe(
                name=_station_name(value),
                number=_BASE_CHANNEL_NUMBER + len(recipes),
                source="motif",
                programming_mode=ProgrammingMode.SHUFFLE,
                media_scope=MediaScope.BOTH.value,
                motif=value,
                summary=f"Motif station for “{value}”"
                + (f" ({count} titles)" if count else ""),
            )
        )

    for collection in collections or ():
        if len(recipes) >= capped - (1 if include_chaos else 0):
            break
        title = str(
            collection.get("title")
            or collection.get("name")
            or collection.get("collection_title")
            or ""
        ).strip()
        if not title:
            continue
        cid = str(collection.get("id") or collection.get("collection_id") or "").strip()
        _add(
            ChannelRecipe(
                name=_station_name(title),
                number=_BASE_CHANNEL_NUMBER + len(recipes),
                source="collection",
                programming_mode=ProgrammingMode.SEQUENTIAL,
                media_scope=MediaScope.BOTH.value,
                collection_id=cid,
                collection_title=title,
                summary=f"Sequential channel from published collection “{title}”",
            )
        )

    if include_chaos and len(recipes) < capped:
        _add(
            ChannelRecipe(
                name="Chaos",
                number=_BASE_CHANNEL_NUMBER + len(recipes),
                source="chaos",
                programming_mode=ProgrammingMode.CHAOS,
                media_scope=MediaScope.BOTH.value,
                summary="Random shuffle across the library — the Chaos channel.",
            )
        )

    if include_youth_safe and len(recipes) < capped:
        _add(
            ChannelRecipe(
                name="Youth Safe",
                number=_BASE_CHANNEL_NUMBER + len(recipes),
                source="youth",
                programming_mode=ProgrammingMode.SHUFFLE,
                media_scope=MediaScope.BOTH.value,
                youth_safe=True,
                summary=(
                    f"Youth-safe shuffle at or below {youth_max_rating} "
                    "(fail-closed for unrated titles)."
                ),
            )
        )

    # Renumber for a clean contiguous block.
    renumbered = [
        ChannelRecipe(
            name=r.name,
            number=_BASE_CHANNEL_NUMBER + idx,
            source=r.source,
            programming_mode=r.programming_mode,
            media_scope=r.media_scope,
            cluster_tag=r.cluster_tag,
            motif=r.motif,
            collection_id=r.collection_id,
            collection_title=r.collection_title,
            youth_safe=r.youth_safe,
            summary=r.summary,
            item_hints=r.item_hints,
        )
        for idx, r in enumerate(recipes)
    ]

    return {
        "proposals": [r.to_dict() for r in renumbered],
        "count": len(renumbered),
        "empty_library": not bool(taste_clusters or motifs or collections),
        "base_channel_number": _BASE_CHANNEL_NUMBER,
    }


def propose_starter_pack_from_db(
    db: Any,
    *,
    settings: Any = None,
    owner_user_id: Optional[str] = None,
    max_channels: int = 4,
) -> Dict[str, Any]:
    """Load taste/motif/collection signals from the DB when methods exist."""
    clusters: List[Mapping[str, Any]] = []
    motifs: List[Mapping[str, Any]] = []
    collections: List[Mapping[str, Any]] = []

    if db is not None and owner_user_id and hasattr(db, "get_user_taste_overrides"):
        try:
            clusters = list(db.get_user_taste_overrides(owner_user_id) or [])
        except Exception:  # noqa: BLE001
            clusters = []

    if db is not None:
        try:
            from projectionist.library.facets import library_facet_catalog

            catalog = library_facet_catalog(db, "motif", limit=12)
            motifs = list(catalog.get("facets") or [])
        except Exception:  # noqa: BLE001
            motifs = []

        if hasattr(db, "list_published_lists"):
            try:
                collections = list(db.list_published_lists() or [])
            except Exception:  # noqa: BLE001
                collections = []

    youth_max = "PG-13"
    if settings is not None:
        try:
            from projectionist.youth.rating_gate import resolve_youth_max_rating

            youth_max = resolve_youth_max_rating(settings)
        except Exception:  # noqa: BLE001
            youth_max = "PG-13"

    return propose_starter_pack(
        taste_clusters=clusters,
        motifs=motifs,
        collections=collections,
        max_channels=max_channels,
        youth_max_rating=youth_max,
    )


def _station_name(raw: str) -> str:
    text = " ".join(str(raw or "").strip().split())
    if not text:
        return "Untitled"
    # Title-case short tags; keep longer titles mostly as-is.
    if len(text) <= 32 and text.islower():
        return text.title()
    return text[:48]


def _sorted_clusters(rows: Sequence[Mapping[str, Any]]) -> List[Mapping[str, Any]]:
    return sorted(
        [r for r in rows if isinstance(r, Mapping)],
        key=lambda r: (-float(r.get("weight") or 0), str(r.get("cluster_tag") or "")),
    )


def _sorted_motifs(rows: Sequence[Mapping[str, Any]]) -> List[Mapping[str, Any]]:
    return sorted(
        [r for r in rows if isinstance(r, Mapping)],
        key=lambda r: (
            -int(r.get("count") or r.get("cnt") or 0),
            str(r.get("value") or r.get("motif") or ""),
        ),
    )
