"""Title relation graph builders (Stage 4 v1 — no LLM required).

v1 edges:
- ``collection`` — same ``tmdb_collection_id`` (bidirectional)
- ``neighbor`` — optional mirror of top cosine neighbors from ``item_neighbors``
- ``shared_crew`` — optional top person overlaps (Directing/Writing)

LLM theme tagging is a separate optional idle stub that skips without an API key.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from curatorx.library.db import Database

RelationRow = Tuple[int, int, str, float, str]

COLLECTION_SOURCE = "tmdb_collection"
NEIGHBOR_SOURCE = "item_neighbors"
SHARED_CREW_SOURCE = "credits_overlap"
CREW_DEPARTMENTS = {"Directing", "Writing", "Directors", "Creator"}
MAX_SHARED_CREW_PER_ITEM = 8
MIN_SHARED_CREW = 2


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
        neighbor_rows = conn.execute(
            """
            SELECT item_id, neighbor_id, score
            FROM item_neighbors
            WHERE score > 0
            ORDER BY item_id ASC, score DESC
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
            SELECT item_id, person_id, department, job
            FROM credits
            WHERE department IN ('Directing', 'Writing')
               OR lower(job) IN ('director', 'writer', 'screenplay', 'creator')
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
    """Read ``title_relations`` for one seed, joined to related library titles."""
    rows = db.list_title_relations(int(item_id), relation=relation, limit=limit)
    items: List[Dict[str, Any]] = []
    for row in rows:
        items.append(
            {
                "from_id": int(row["from_id"]),
                "to_id": int(row["to_id"]),
                "relation": str(row["relation"]),
                "weight": float(row["weight"] or 0),
                "source": str(row["source"] or ""),
                "title": str(row["title"] or ""),
                "year": int(row["year"]) if row["year"] is not None else None,
                "media_type": str(row["media_type"] or ""),
                "tmdb_id": int(row["tmdb_id"]) if row["tmdb_id"] is not None else None,
                "tvdb_id": int(row["tvdb_id"]) if row["tvdb_id"] is not None else None,
                "rating_key": str(row["rating_key"] or ""),
                "poster_url": str(row["poster_url"] or ""),
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
