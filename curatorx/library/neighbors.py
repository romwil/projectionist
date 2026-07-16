"""Plot-neighbor scoring over stored embeddings.

v1 uses pure-Python cosine against all library embeddings.  Homelab libraries
are typically thousands of titles — fine for idle trickle.  Future optional
sqlite-vec ANN can prefilter candidate ids before the same surprise scoring;
``item_neighbors`` remains the read cache either way.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from curatorx.library.db import Database
from curatorx.library.embeddings import cosine_similarity

DEFAULT_TOP_K = 25


def _parse_tag_set(raw: Any) -> Set[str]:
    if not raw:
        return set()
    if isinstance(raw, list):
        return {str(v).strip().lower() for v in raw if str(v).strip()}
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return {raw.strip().lower()} if raw.strip() else set()
        if isinstance(parsed, list):
            return {str(v).strip().lower() for v in parsed if str(v).strip()}
    return set()


def jaccard(a: Set[str] | Set[int], b: Set[str] | Set[int]) -> float:
    if not a and not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def metadata_overlap_tokens(
    row: Mapping[str, Any],
    *,
    person_ids: Optional[Set[int]] = None,
) -> Set[str]:
    """Genre + keyword (+ optional credit person) tokens for surprise Jaccard."""
    tokens = _parse_tag_set(row["genres"] if "genres" in row.keys() else [])
    tokens |= _parse_tag_set(row["keywords"] if "keywords" in row.keys() else [])
    if person_ids:
        tokens |= {f"person:{pid}" for pid in person_ids}
    return tokens


def surprise_score(cosine: float, overlap: float) -> float:
    """High cosine with low metadata/credit overlap → surprising neighbor."""
    cosine = max(0.0, min(1.0, float(cosine)))
    overlap = max(0.0, min(1.0, float(overlap)))
    return cosine * (1.0 - overlap)


def compute_neighbors_for_seed(
    seed_id: int,
    seed_vector: Sequence[float],
    seed_tokens: Set[str],
    candidates: Sequence[Tuple[int, Sequence[float], Set[str]]],
    *,
    top_k: int = DEFAULT_TOP_K,
) -> List[Tuple[int, float, float]]:
    """Return ``(neighbor_id, score, surprise_score)`` sorted by cosine desc."""
    scored: List[Tuple[int, float, float]] = []
    for neighbor_id, vector, tokens in candidates:
        if neighbor_id == seed_id:
            continue
        score = cosine_similarity(seed_vector, vector)
        if score <= 0:
            continue
        overlap = jaccard(seed_tokens, tokens)
        scored.append((neighbor_id, score, surprise_score(score, overlap)))
    scored.sort(key=lambda item: item[1], reverse=True)
    return scored[: max(1, int(top_k))]


def build_item_token_map(
    db: Database,
    item_ids: Optional[Iterable[int]] = None,
) -> Dict[int, Set[str]]:
    """Build metadata/credit token sets for surprise scoring.

    When ``item_ids`` is None, uses the full library.  Prefer this over
    per-id lookups when scoring many seeds.
    """
    wanted = {int(i) for i in item_ids} if item_ids is not None else None
    rows = list(db.all_library_items())
    if wanted is not None:
        rows = [r for r in rows if int(r["id"]) in wanted]
    ids = [int(r["id"]) for r in rows]
    person_map = db.credit_person_ids_by_item(ids)
    out: Dict[int, Set[str]] = {}
    for row in rows:
        item_id = int(row["id"])
        out[item_id] = metadata_overlap_tokens(row, person_ids=person_map.get(item_id))
    return out


def refresh_neighbors_for_items(
    db: Database,
    seed_ids: Sequence[int],
    *,
    top_k: int = DEFAULT_TOP_K,
) -> int:
    """Compute and store neighbors for each seed id. Returns seeds processed."""
    embeddings = db.get_embeddings()
    if not embeddings:
        return 0
    emb_map = {item_id: vector for item_id, vector in embeddings}
    token_map = build_item_token_map(db, emb_map.keys())
    candidates = [
        (item_id, vector, token_map.get(item_id, set()))
        for item_id, vector in embeddings
    ]
    processed = 0
    for seed_id in seed_ids:
        seed_id = int(seed_id)
        seed_vector = emb_map.get(seed_id)
        if seed_vector is None:
            continue
        neighbors = compute_neighbors_for_seed(
            seed_id,
            seed_vector,
            token_map.get(seed_id, set()),
            candidates,
            top_k=top_k,
        )
        db.set_neighbors(seed_id, neighbors)
        processed += 1
    return processed
