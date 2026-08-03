"""Title relation graph builders (Stage 4 v1 — no LLM required).

v1 edges:
- ``collection`` — same ``tmdb_collection_id`` (bidirectional)
- ``neighbor`` — optional mirror of top cosine neighbors from ``item_neighbors``
- ``shared_crew`` — optional top person overlaps (Directing/Writing)

LLM theme tagging is a separate optional idle stub that skips without an API key.
"""

from __future__ import annotations

from collections import defaultdict
import json
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from projectionist.library.db import Database

RelationRow = Tuple[int, int, str, float, str]

COLLECTION_SOURCE = "tmdb_collection"
NEIGHBOR_SOURCE = "item_neighbors"
SHARED_CREW_SOURCE = "credits_overlap"
CREW_DEPARTMENTS = {"Directing", "Writing", "Directors", "Creator"}
MAX_SHARED_CREW_PER_ITEM = 8
MIN_SHARED_CREW = 2


def _json_labels(value: Any) -> List[str]:
    if isinstance(value, list):
        raw = value
    elif isinstance(value, str) and value:
        try:
            raw = json.loads(value)
        except (TypeError, json.JSONDecodeError):
            raw = []
    else:
        raw = []
    return [str(label).strip() for label in raw if str(label).strip()]


def _shared_labels(left: Sequence[str], right: Sequence[str]) -> List[str]:
    right_keys = {label.casefold() for label in right}
    return [label for label in left if label.casefold() in right_keys]


def _plot_kinship_label(score: float) -> str:
    if score >= 0.85:
        return "Very close in plot space"
    if score >= 0.7:
        return "Strong plot kinship"
    if score >= 0.55:
        return "Solid plot kinship"
    if score >= 0.4:
        return "Mild plot kinship"
    return "Loose plot kinship"


def _surprise_flavor(score: float, surprise_score: Optional[float]) -> Optional[str]:
    if surprise_score is None or score <= 0:
        return None
    overlap = max(0.0, min(1.0, 1.0 - (surprise_score / score)))
    if overlap <= 0.15:
        return "Almost no shared genre, keyword, or credit labels"
    if overlap <= 0.35:
        return "Shelf labels barely overlap"
    if overlap <= 0.55:
        return "Only partial shelf overlap"
    return "Some shelf overlap"


def _relation_context(
    db: Database,
    item_id: int,
    rows: Sequence[Any],
) -> Tuple[Mapping[int, Any], Mapping[int, List[str]], Mapping[int, Optional[float]]]:
    ids = {int(item_id)}
    ids.update(int(row["to_id"]) for row in rows)
    placeholders = ",".join("?" for _ in ids)
    metadata: Dict[int, Any] = {}
    crew_by_item: Dict[int, List[str]] = defaultdict(list)
    surprise_by_peer: Dict[int, Optional[float]] = {}
    with db.connect() as conn:
        for row in conn.execute(
            f"""
            SELECT id, rating_key, media_type, title, year, poster_url, backdrop_url,
                   tmdb_id, tvdb_id, genres, collection_name, content_rating
            FROM library_items
            WHERE id IN ({placeholders})
            """,
            tuple(sorted(ids)),
        ).fetchall():
            metadata[int(row["id"])] = row
        for row in conn.execute(
            f"""
            SELECT c.item_id, p.name
            FROM credits c
            JOIN people p ON p.id = c.person_id
            WHERE c.item_id IN ({placeholders})
              AND (
                c.department IN ('Directing', 'Writing')
                OR lower(c.job) IN ('director', 'writer', 'screenplay', 'creator')
              )
            ORDER BY c.billing_order ASC, p.name ASC
            """,
            tuple(sorted(ids)),
        ).fetchall():
            name = str(row["name"] or "").strip()
            if name and name not in crew_by_item[int(row["item_id"])]:
                crew_by_item[int(row["item_id"])].append(name)
        for row in conn.execute(
            """
            SELECT neighbor_id, surprise_score
            FROM item_neighbors
            WHERE item_id = ?
            """,
            (int(item_id),),
        ).fetchall():
            surprise_by_peer[int(row["neighbor_id"])] = (
                float(row["surprise_score"])
                if row["surprise_score"] is not None
                else None
            )
    return metadata, crew_by_item, surprise_by_peer


def _why_payload(
    *,
    relation: str,
    weight: float,
    seed: Any,
    peer: Any,
    shared_people: Sequence[str],
    surprise_score: Optional[float],
) -> Dict[str, Any]:
    seed_genres = _json_labels(seed["genres"]) if seed is not None else []
    peer_genres = _json_labels(peer["genres"]) if peer is not None else []
    shared_genres = _shared_labels(seed_genres, peer_genres)
    collection_name: Optional[str] = None
    plot_kinship: Optional[str] = None
    surprise_flavor: Optional[str] = None

    if relation == "collection":
        for row in (seed, peer):
            if row is not None and str(row["collection_name"] or "").strip():
                collection_name = str(row["collection_name"]).strip()
                break
        label = (
            f"Same collection: {collection_name}"
            if collection_name
            else "Same collection"
        )
    elif relation == "shared_crew":
        names = list(shared_people)
        label = (
            f"Shared director/writer: {', '.join(names[:3])}"
            if names
            else "Shared directors or writers"
        )
    elif relation == "neighbor":
        plot_kinship = _plot_kinship_label(weight)
        surprise_flavor = _surprise_flavor(weight, surprise_score)
        label = plot_kinship
        if shared_genres:
            label += f" · Shared genres: {', '.join(shared_genres[:3])}"
    else:
        label = "Related title"

    return {
        "type": relation,
        "label": label,
        "shared_people": list(shared_people),
        "shared_genres": shared_genres,
        "collection_name": collection_name,
        "plot_kinship": plot_kinship,
        "surprise_flavor": surprise_flavor,
    }


def build_collection_relations(db: Database) -> List[RelationRow]:
    """Bidirectional collection edges from ``tmdb_collection_id``."""
    by_collection: Dict[int, List[int]] = defaultdict(list)
    for row in db.all_library_items():
        keys = row.keys()
        if "tmdb_collection_id" not in keys or row["tmdb_collection_id"] is None:
            continue
        try:
            cid = int(row["tmdb_collection_id"])
        except (TypeError, ValueError):
            continue
        if cid <= 0:
            continue
        by_collection[cid].append(int(row["id"]))

    rows: List[RelationRow] = []
    seen: Set[Tuple[int, int]] = set()
    for members in by_collection.values():
        if len(members) < 2:
            continue
        unique = sorted(set(members))
        for i, from_id in enumerate(unique):
            for to_id in unique[i + 1 :]:
                if (from_id, to_id) in seen:
                    continue
                seen.add((from_id, to_id))
                rows.append((from_id, to_id, "collection", 1.0, COLLECTION_SOURCE))
                rows.append((to_id, from_id, "collection", 1.0, COLLECTION_SOURCE))
    return rows


def build_neighbor_relations(
    db: Database,
    *,
    top_k: int = 10,
) -> List[RelationRow]:
    """Mirror high-cosine neighbors into ``title_relations`` (optional)."""
    rows: List[RelationRow] = []
    with db.connect() as conn:
        # Join both ends so legacy orphan neighbor rows (pre–FK enforcement)
        # cannot produce title_relations inserts that fail FOREIGN KEY checks.
        neighbor_rows = conn.execute(
            """
            SELECT n.item_id, n.neighbor_id, n.score
            FROM item_neighbors n
            JOIN library_items seed ON seed.id = n.item_id
            JOIN library_items peer ON peer.id = n.neighbor_id
            WHERE n.score > 0
            ORDER BY n.item_id ASC, n.score DESC
            """
        ).fetchall()
    per_seed: Dict[int, int] = defaultdict(int)
    for row in neighbor_rows:
        seed = int(row["item_id"])
        if per_seed[seed] >= top_k:
            continue
        per_seed[seed] += 1
        rows.append(
            (
                seed,
                int(row["neighbor_id"]),
                "neighbor",
                float(row["score"] or 0),
                NEIGHBOR_SOURCE,
            )
        )
    return rows


def build_shared_crew_relations(
    db: Database,
    *,
    min_shared: int = MIN_SHARED_CREW,
    max_per_item: int = MAX_SHARED_CREW_PER_ITEM,
) -> List[RelationRow]:
    """Link titles that share multiple top crew (directors/writers)."""
    # person_id → set of item_ids
    person_items: Dict[int, Set[int]] = defaultdict(set)
    with db.connect() as conn:
        credit_rows = conn.execute(
            """
            SELECT c.item_id, c.person_id, c.department, c.job
            FROM credits c
            JOIN library_items li ON li.id = c.item_id
            WHERE c.department IN ('Directing', 'Writing')
               OR lower(c.job) IN ('director', 'writer', 'screenplay', 'creator')
            """
        ).fetchall()
    for row in credit_rows:
        person_items[int(row["person_id"])].add(int(row["item_id"]))

    # Pairwise co-occurrence counts
    pair_counts: Dict[Tuple[int, int], int] = defaultdict(int)
    for items in person_items.values():
        if len(items) < 2:
            continue
        ordered = sorted(items)
        for i, a in enumerate(ordered):
            for b in ordered[i + 1 :]:
                pair_counts[(a, b)] += 1

    scored: List[Tuple[int, int, float]] = []
    for (a, b), count in pair_counts.items():
        if count < min_shared:
            continue
        weight = float(min(1.0, count / 5.0))
        scored.append((a, b, weight))
    scored.sort(key=lambda t: t[2], reverse=True)

    rows: List[RelationRow] = []
    per_item: Dict[int, int] = defaultdict(int)
    for a, b, weight in scored:
        if per_item[a] < max_per_item:
            rows.append((a, b, "shared_crew", weight, SHARED_CREW_SOURCE))
            per_item[a] += 1
        if per_item[b] < max_per_item:
            rows.append((b, a, "shared_crew", weight, SHARED_CREW_SOURCE))
            per_item[b] += 1
    return rows


def refresh_title_relations(
    db: Database,
    *,
    include_neighbors: bool = True,
    include_shared_crew: bool = True,
) -> Dict[str, Any]:
    """Replace graph edges derived from DB (collection + optional mirrors)."""
    collection = build_collection_relations(db)
    neighbor = build_neighbor_relations(db) if include_neighbors else []
    shared = build_shared_crew_relations(db) if include_shared_crew else []

    db.replace_relations_of_types(
        {
            "collection": collection,
            "neighbor": neighbor,
            "shared_crew": shared,
        }
    )
    return {
        "collection": len(collection),
        "neighbor": len(neighbor),
        "shared_crew": len(shared),
        "total": len(collection) + len(neighbor) + len(shared),
    }


def list_relations_for_item(
    db: Database,
    item_id: int,
    *,
    relation: Optional[str] = None,
    limit: int = 25,
) -> Dict[str, Any]:
    """Read enriched outgoing edges for one seed and their peer title cards."""
    rows = db.list_title_relations(int(item_id), relation=relation, limit=limit)
    metadata, crew_by_item, surprise_by_peer = _relation_context(db, item_id, rows)
    seed = metadata.get(int(item_id))
    items: List[Dict[str, Any]] = []
    for row in rows:
        to_id = int(row["to_id"])
        relation_type = str(row["relation"])
        weight = float(row["weight"] or 0)
        peer_row = metadata.get(to_id)
        seed_crew = crew_by_item.get(int(item_id), [])
        peer_crew = crew_by_item.get(to_id, [])
        shared_people = (
            _shared_labels(seed_crew, peer_crew)
            if relation_type == "shared_crew"
            else []
        )
        peer = {
            "library_item_id": to_id,
            "title": str(row["title"] or ""),
            "year": int(row["year"]) if row["year"] is not None else None,
            "media_type": str(row["media_type"] or ""),
            "tmdb_id": (
                int(row["tmdb_id"]) if row["tmdb_id"] is not None else None
            ),
            "tvdb_id": (
                int(row["tvdb_id"]) if row["tvdb_id"] is not None else None
            ),
            "rating_key": str(row["rating_key"] or ""),
            "poster_url": str(row["poster_url"] or ""),
            "backdrop_url": (
                str(peer_row["backdrop_url"] or "") if peer_row is not None else ""
            ),
            "genres": (
                _json_labels(peer_row["genres"]) if peer_row is not None else []
            ),
            "content_rating": (
                str(peer_row["content_rating"] or "")
                if peer_row is not None
                else ""
            ),
            "in_library": True,
        }
        why = _why_payload(
            relation=relation_type,
            weight=weight,
            seed=seed,
            peer=peer_row,
            shared_people=shared_people,
            surprise_score=surprise_by_peer.get(to_id),
        )
        items.append(
            {
                "from_id": int(row["from_id"]),
                "to_id": to_id,
                "relation": relation_type,
                "weight": weight,
                "source": str(row["source"] or ""),
                **{key: value for key, value in peer.items() if key != "library_item_id"},
                "peer": peer,
                "why": why,
            }
        )
    return {
        "item_id": int(item_id),
        "relation": relation,
        "items": items,
        "returned": len(items),
    }


def walk_relations(
    db: Database,
    item_id: int,
    *,
    relation: Optional[str] = None,
    depth: int = 1,
    limit: int = 25,
) -> Dict[str, Any]:
    """Shallow BFS over ``title_relations`` (depth capped at 2 for v1)."""
    capped_depth = min(max(1, int(depth or 1)), 2)
    capped_limit = min(max(1, int(limit or 25)), 50)
    visited: Set[int] = {int(item_id)}
    frontier = [int(item_id)]
    edges: List[Dict[str, Any]] = []

    for _level in range(capped_depth):
        next_frontier: List[int] = []
        for seed in frontier:
            payload = list_relations_for_item(
                db, seed, relation=relation, limit=capped_limit
            )
            for item in payload["items"]:
                edges.append(item)
                to_id = int(item["to_id"])
                if to_id not in visited:
                    visited.add(to_id)
                    next_frontier.append(to_id)
                if len(edges) >= capped_limit:
                    break
            if len(edges) >= capped_limit:
                break
        frontier = next_frontier
        if not frontier or len(edges) >= capped_limit:
            break

    return {
        "item_id": int(item_id),
        "relation": relation,
        "depth": capped_depth,
        "items": edges[:capped_limit],
        "returned": min(len(edges), capped_limit),
        "visited": len(visited),
    }
