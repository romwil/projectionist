"""Owner craft vocabulary — motifs / taste / collections → ChannelRecipe options.

Projectionist is the channel-config plane (Coax vocabulary → Tunarr OpenAPI).
This module only assembles picker options + normalizes a craft payload; publish
lives in ``publish.py``.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

from projectionist.live_channels.recipes import (
    ChannelRecipe,
    ProgrammingMode,
    recipe_from_mapping,
)


_SOURCES = (
    {
        "id": "motif",
        "label": "Plot motif",
        "description": "Shuffle titles that match a Plot Lab motif.",
    },
    {
        "id": "taste_cluster",
        "label": "Taste cluster",
        "description": "Shuffle from one of your taste-cluster tags.",
    },
    {
        "id": "collection",
        "label": "Collection / list",
        "description": "Play a Plex or published Projectionist collection in order.",
    },
    {
        "id": "chaos",
        "label": "Chaos",
        "description": "Random shuffle across the indexed library.",
    },
    {
        "id": "youth",
        "label": "Youth-safe",
        "description": "Shuffle at or below the household youth rating ceiling.",
    },
)

_MODES = (
    {"id": ProgrammingMode.SHUFFLE.value, "label": "Shuffle"},
    {"id": ProgrammingMode.SEQUENTIAL.value, "label": "Sequential"},
    {"id": ProgrammingMode.CHAOS.value, "label": "Chaos"},
)


def next_channel_number(
    existing_numbers: Sequence[int] | None = None,
    *,
    base: int = 100,
) -> int:
    """Pick the next virtual channel number at or above ``base``."""
    floor = max(1, int(base or 100))
    used = [int(n) for n in (existing_numbers or ()) if int(n or 0) > 0]
    if not used:
        return floor
    return max(floor, max(used) + 1)


def _append_collection_row(
    collections: List[Dict[str, Any]],
    *,
    collection_id: str,
    title: str,
    item_count: int = 0,
    source: str,
    media_type: str = "",
) -> None:
    cid = str(collection_id or "").strip()
    name = str(title or "").strip()
    if not name:
        return
    # Prefer first occurrence (published lists before Plex duplicates by title).
    if any(
        str(row.get("id") or "") == cid
        or (
            str(row.get("title") or "").casefold() == name.casefold()
            and str(row.get("source") or "") == source
        )
        for row in collections
    ):
        return
    row: Dict[str, Any] = {
        "id": cid,
        "title": name,
        "item_count": int(item_count or 0),
        "label": name,
        "source": source,
    }
    if media_type:
        row["media_type"] = media_type
    collections.append(row)


def _load_plex_collections(settings: Any) -> tuple[List[Dict[str, Any]], str]:
    """Return (rows, error). Empty error means success (even if zero collections)."""
    plex_url = str(getattr(settings, "plex_url", "") or "").strip()
    plex_token = str(getattr(settings, "plex_token", "") or "").strip()
    if not plex_url or not plex_token:
        return [], "Plex URL/token not configured — showing Projectionist lists only."

    from projectionist.config_store import resolve_plex_section
    from projectionist.connectors.plex import PlexClient
    from projectionist.connectors.plex_collections import (
        is_ephemeral_collection_title,
        list_collections,
    )
    from projectionist.library.db import EPHEMERAL_COLLECTION_PREFIX

    movie_section = resolve_plex_section(settings, "movie")
    tv_section = resolve_plex_section(settings, "show")
    if not movie_section and not tv_section:
        return [], "Plex movie/TV library sections are not mapped."

    client = PlexClient(plex_url, plex_token, timeout=20)
    rows: List[Dict[str, Any]] = []
    try:
        for section_id, media_type in (
            (movie_section, "movie"),
            (tv_section, "show"),
        ):
            if not section_id:
                continue
            for coll in list_collections(client, str(section_id)):
                title = str(coll.title or "").strip()
                if not title:
                    continue
                if is_ephemeral_collection_title(
                    title, prefix=EPHEMERAL_COLLECTION_PREFIX
                ):
                    continue
                _append_collection_row(
                    rows,
                    collection_id=str(coll.rating_key or ""),
                    title=title,
                    item_count=0,
                    source="plex",
                    media_type=str(coll.media_type or media_type),
                )
    except Exception as error:  # noqa: BLE001
        return [], f"Could not load Plex collections: {str(error)[:180]}"
    rows.sort(key=lambda r: str(r.get("title") or "").casefold())
    return rows, ""


def build_craft_options(
    db: Any = None,
    *,
    settings: Any = None,
    owner_user_id: Optional[str] = None,
    existing_channel_numbers: Sequence[int] | None = None,
) -> Dict[str, Any]:
    """Picker payload for Admin → Live Channels → Craft a station."""
    tunarr = getattr(settings, "tunarr", None) if settings is not None else None
    base = int(getattr(tunarr, "channel_number_base", 100) or 100) if tunarr else 100

    clusters: List[Dict[str, Any]] = []
    motifs: List[Dict[str, Any]] = []
    collections: List[Dict[str, Any]] = []
    collections_error = ""
    published_count = 0
    plex_count = 0

    if db is not None and owner_user_id and hasattr(db, "get_user_taste_overrides"):
        try:
            for row in db.get_user_taste_overrides(owner_user_id) or []:
                if not isinstance(row, Mapping):
                    continue
                tag = str(row.get("cluster_tag") or row.get("tag") or "").strip()
                if not tag:
                    continue
                clusters.append(
                    {
                        "cluster_tag": tag,
                        "weight": float(row.get("weight") or 0),
                        "label": tag,
                    }
                )
        except Exception:  # noqa: BLE001
            clusters = []
        clusters.sort(key=lambda r: (-float(r.get("weight") or 0), r["cluster_tag"]))

    if db is not None:
        try:
            from projectionist.library.facets import library_facet_catalog

            catalog = library_facet_catalog(db, "motif", limit=24)
            for row in catalog.get("facets") or []:
                if not isinstance(row, Mapping):
                    continue
                value = str(row.get("value") or row.get("motif") or "").strip()
                if not value:
                    continue
                motifs.append(
                    {
                        "value": value,
                        "count": int(row.get("count") or row.get("cnt") or 0),
                        "label": value,
                    }
                )
        except Exception:  # noqa: BLE001
            motifs = []

        if hasattr(db, "list_published_lists"):
            try:
                for row in db.list_published_lists() or []:
                    if not isinstance(row, Mapping):
                        continue
                    title = str(row.get("title") or row.get("name") or "").strip()
                    if not title:
                        continue
                    _append_collection_row(
                        collections,
                        collection_id=str(row.get("id") or ""),
                        title=title,
                        item_count=int(row.get("item_count") or 0),
                        source="published",
                    )
                    published_count += 1
            except Exception:  # noqa: BLE001
                pass

    if settings is not None:
        plex_rows, plex_error = _load_plex_collections(settings)
        collections_error = plex_error
        for row in plex_rows:
            _append_collection_row(
                collections,
                collection_id=str(row.get("id") or ""),
                title=str(row.get("title") or ""),
                item_count=int(row.get("item_count") or 0),
                source="plex",
                media_type=str(row.get("media_type") or ""),
            )
            plex_count += 1

    youth_max = "PG-13"
    if settings is not None:
        try:
            from projectionist.youth.rating_gate import resolve_youth_max_rating

            youth_max = resolve_youth_max_rating(settings) or "PG-13"
        except Exception:  # noqa: BLE001
            youth_max = "PG-13"

    collections_total = len(collections)
    capped = collections[:40]
    if not collections:
        if collections_error:
            empty_reason = "error"
            empty_hint = collections_error
        else:
            empty_reason = "none"
            empty_hint = (
                "No Plex collections or published Projectionist lists found. "
                "Create a collection in Plex, or publish a list under Collections."
            )
    else:
        empty_reason = ""
        empty_hint = ""

    return {
        "sources": list(_SOURCES),
        "programming_modes": list(_MODES),
        "motifs": motifs[:24],
        "taste_clusters": clusters[:16],
        "collections": capped,
        "collections_total": collections_total,
        "collections_published_count": published_count,
        "collections_plex_count": plex_count,
        "collections_error": collections_error,
        "collections_empty_reason": empty_reason,
        "collections_empty_hint": empty_hint,
        "channel_number_base": base,
        "next_channel_number": next_channel_number(existing_channel_numbers, base=base),
        "youth_max_rating": youth_max,
        "empty_library": not bool(motifs or clusters or collections),
        "hint": (
            "Pick a motif, taste cluster, Plex/Projectionist collection, Chaos, or "
            "youth-safe recipe. Publish creates the station on Tunarr and fills the "
            "lineup from your library."
        ),
    }


def recipe_from_craft_payload(
    data: Mapping[str, Any],
    *,
    default_number: int = 100,
) -> ChannelRecipe:
    """Normalize an Admin craft form into a ``ChannelRecipe``."""
    payload = dict(data or {})
    source = str(payload.get("source") or "chaos").strip().lower() or "chaos"
    if source not in {s["id"] for s in _SOURCES}:
        source = "chaos"

    name = str(payload.get("name") or "").strip()
    motif = str(payload.get("motif") or "").strip()
    cluster = str(payload.get("cluster_tag") or "").strip()
    collection_title = str(
        payload.get("collection_title") or payload.get("collection_name") or ""
    ).strip()
    collection_id = str(payload.get("collection_id") or "").strip()

    if not name:
        if source == "motif" and motif:
            name = motif.title() if motif.islower() else motif
        elif source == "taste_cluster" and cluster:
            name = cluster.title() if cluster.islower() else cluster
        elif source == "collection" and collection_title:
            name = collection_title
        elif source == "youth":
            name = "Youth Safe"
        elif source == "chaos":
            name = "Chaos"
        else:
            name = "Custom Station"
    name = name[:48]

    try:
        number = int(payload.get("number") or 0)
    except (TypeError, ValueError):
        number = 0
    if number <= 0:
        number = int(default_number or 100)

    mode_raw = str(payload.get("programming_mode") or "").strip().lower()
    if not mode_raw:
        if source == "collection":
            mode_raw = ProgrammingMode.SEQUENTIAL.value
        elif source == "chaos":
            mode_raw = ProgrammingMode.CHAOS.value
        else:
            mode_raw = ProgrammingMode.SHUFFLE.value

    youth_safe = bool(payload.get("youth_safe")) or source == "youth"
    summary = str(payload.get("summary") or "").strip()
    if not summary:
        if source == "motif" and motif:
            summary = f"Motif station for “{motif}”"
        elif source == "taste_cluster" and cluster:
            summary = f"Shuffle station from your “{cluster}” taste cluster"
        elif source == "collection" and collection_title:
            summary = f"Sequential channel from collection “{collection_title}”"
        elif source == "youth":
            summary = "Youth-safe shuffle (rating gate applied when filling)."
        else:
            summary = "Custom Live Channels station."

    return recipe_from_mapping(
        {
            "name": name,
            "number": number,
            "source": source,
            "programming_mode": mode_raw,
            "cluster_tag": cluster,
            "motif": motif,
            "collection_id": collection_id,
            "collection_title": collection_title,
            "youth_safe": youth_safe,
            "summary": summary,
            "item_hints": payload.get("item_hints") or (),
        }
    )
