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
from projectionist.library.neighbors import measured_metadata_overlap
from projectionist.library.plot_kinship import plot_blob, surprising_plot_link

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


def _row_field(row: Any, name: str) -> Any:
    if row is None:
        return None
    try:
        return row[name]
    except (KeyError, IndexError, TypeError):
        return None


def _positive_id(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _same_library_title(seed: Any, peer: Any) -> bool:
    """True when the peer is the seed title, including a duplicate library row."""
    if seed is None or peer is None:
        return False
    seed_id = _positive_id(_row_field(seed, "id"))
    peer_id = _positive_id(_row_field(peer, "id"))
    if seed_id is not None and peer_id is not None and seed_id == peer_id:
        return True
    for key in ("tmdb_id", "tvdb_id"):
        left = _positive_id(_row_field(seed, key))
        right = _positive_id(_row_field(peer, key))
        if left is not None and right is not None and left == right:
            return True
    left_title = " ".join(str(_row_field(seed, "title") or "").casefold().split())
    right_title = " ".join(str(_row_field(peer, "title") or "").casefold().split())
    if not left_title or left_title != right_title:
        return False
    if str(_row_field(seed, "media_type") or "") != str(_row_field(peer, "media_type") or ""):
        return False
    left_year = _row_field(seed, "year")
    right_year = _row_field(peer, "year")
    if left_year is None or right_year is None:
        return True
    try:
        return int(left_year) == int(right_year)
    except (TypeError, ValueError):
        return True


def _shelf_labels(row: Any, people: Sequence[str]) -> Set[str]:
    labels: Set[str] = set()
    if row is not None:
        labels.update(label.casefold() for label in _json_labels(_row_field(row, "genres")))
        labels.update(label.casefold() for label in _json_labels(_row_field(row, "keywords")))
    for name in people:
        text = str(name or "").strip().casefold()
        if text:
            labels.add(text)
    return labels


def _relation_context(
    db: Database,
    item_id: int,
    rows: Sequence[Any],
) -> Tuple[Mapping[int, Any], Mapping[int, List[str]]]:
    ids = {int(item_id)}
    ids.update(int(row["to_id"]) for row in rows)
    placeholders = ",".join("?" for _ in ids)
    metadata: Dict[int, Any] = {}
    crew_by_item: Dict[int, List[str]] = defaultdict(list)
    with db.connect() as conn:
        for row in conn.execute(
            f"""
            SELECT id, rating_key, media_type, title, year, poster_url, backdrop_url,
                   tmdb_id, tvdb_id, genres, keywords, summary, tmdb_overview, tagline,
                   long_synopsis, llm_logline, collection_name, content_rating
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
    return metadata, crew_by_item


def _why_payload(
    *,
    relation: str,
    weight: float,
    seed: Any,
    peer: Any,
    shared_people: Sequence[str],
    seed_people: Sequence[str] = (),
    peer_people: Sequence[str] = (),
) -> Dict[str, Any]:
    seed_genres = _json_labels(seed["genres"]) if seed is not None else []
    peer_genres = _json_labels(peer["genres"]) if peer is not None else []
    shared_genres = _shared_labels(seed_genres, peer_genres)
    collection_name: Optional[str] = None
    plot_kinship: Optional[str] = None
    surprise_flavor: Optional[str] = None
    plot_link: Optional[str] = None
    shelf_note: Optional[str] = None
    shared_story: List[str] = []

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
        seed_shelf = _shelf_labels(seed, seed_people)
        peer_shelf = _shelf_labels(peer, peer_people)
        link = surprising_plot_link(
            cosine=weight,
            overlap=measured_metadata_overlap(seed_shelf, peer_shelf),
            seed_text=plot_blob(seed),
            peer_text=plot_blob(peer),
            shelf_labels=seed_shelf | peer_shelf,
        )
        if link:
            plot_link = str(link["sentence"])
            shelf_note = str(link["shelf_note"] or "") or None
            shared_story = [str(term) for term in link.get("terms") or []]
            # The flavor is the kinship. Absence of labels is only a secondary note.
            surprise_flavor = plot_link
            label = plot_link
        else:
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
        "plot_link": plot_link,
        "shelf_note": shelf_note,
        "shared_story": shared_story,
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
    metadata, crew_by_item = _relation_context(db, item_id, rows)
    seed = metadata.get(int(item_id))
    items: List[Dict[str, Any]] = []
    for row in rows:
        to_id = int(row["to_id"])
        relation_type = str(row["relation"])
        weight = float(row["weight"] or 0)
        peer_row = metadata.get(to_id)
        if relation_type == "neighbor" and _same_library_title(seed, peer_row):
            continue
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
            seed_people=seed_crew,
            peer_people=peer_crew,
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
