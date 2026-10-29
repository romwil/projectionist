"""Plot-neighbor scoring over stored embeddings.

Exact cosine (+ surprise) scores candidates; optional sqlite-vec ANN can
prefilter candidate ids before that scoring when the extension is available.
``item_neighbors`` remains the UI/agent read cache either way. Default images
without sqlite-vec keep the full exact scan.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from projectionist.library.db import Database
from projectionist.library.embeddings import COSINE_OFFLOAD_THRESHOLD, cosine_similarity
from projectionist.library.plot_kinship import (
    plot_blob,
    plot_link_json,
    specific_plot_link,
)
from projectionist.library.vec_index import ann_candidate_ids, vec_available

DEFAULT_TOP_K = 25
# How many ANN hits to exact-rescore per seed (top_k × multiplier, capped).
ANN_CANDIDATE_MULTIPLIER = 8
ANN_CANDIDATE_CAP = 400
# Re-export threshold so callers (and tests) can decide when to ``run_db``.
NEIGHBOR_COSINE_OFFLOAD_THRESHOLD = COSINE_OFFLOAD_THRESHOLD


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


def measured_metadata_overlap(
    left: Set[str] | Set[int],
    right: Set[str] | Set[int],
) -> Optional[float]:
    """Shelf Jaccard when both sides actually have labels.

    Empty label sets are unknown overlap. Scoring them as 0 made
    ``surprise_score`` equal the cosine, so missing shelf data ranked as
    maximally surprising.
    """
    if not left or not right:
        return None
    return jaccard(left, right)


def surprise_score(cosine: float, overlap: float) -> float:
    """High cosine with low metadata/credit overlap → higher surprise rank.

    Callers must pass a measured overlap. Unknown (missing) labels are not
    zero overlap — use ``measured_metadata_overlap`` and skip this when it
    returns None.
    """
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
        overlap = measured_metadata_overlap(seed_tokens, tokens)
        surprise = 0.0 if overlap is None else surprise_score(score, overlap)
        scored.append((neighbor_id, score, surprise))
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


def _shelf_label_set(tokens: Set[str]) -> Set[str]:
    """Strip person: tokens so plot-link blocklist stays shelf-shaped."""
    return {
        token
        for token in tokens
        if token and not str(token).startswith("person:")
    }


_CREW_JOBS = ("director", "writer", "screenplay", "creator")


def _director_writer_names(db: Database, item_ids: Sequence[int]) -> Set[str]:
    """Director/writer names for plot-link shelf blocking — not ``person:`` ids."""
    ids = sorted({int(item_id) for item_id in item_ids if int(item_id) > 0})
    if not ids:
        return set()
    placeholders = ",".join("?" for _ in ids)
    jobs = ",".join("?" for _ in _CREW_JOBS)
    names: Set[str] = set()
    try:
        with db.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT p.name AS name
                FROM credits c
                JOIN people p ON p.id = c.person_id
                WHERE c.item_id IN ({placeholders})
                  AND (
                    c.department IN ('Directing', 'Writing', 'Directors', 'Creator')
                    OR lower(COALESCE(c.job, '')) IN ({jobs})
                  )
                """,
                (*ids, *_CREW_JOBS),
            ).fetchall()
    except Exception:  # noqa: BLE001 — partial fixtures / missing credits table
        rows = []
    for row in rows:
        text = str(row["name"] or "").strip().casefold()
        if text:
            names.add(text)
    return names


def _directors_field_names(row: Any) -> Set[str]:
    try:
        raw = row["directors"]
    except (KeyError, IndexError, TypeError):
        return set()
    return _parse_tag_set(raw)


def enrich_neighbors_with_explanations(
    db: Database,
    seed_id: int,
    neighbors: Sequence[Tuple[int, float, float]],
) -> List[Tuple[int, float, float, int, Optional[str]]]:
    """Mark each cosine peer explainable when ``specific_plot_link`` names a subject."""
    seed = db.library_item_by_id(int(seed_id))
    if seed is None:
        return [
            (int(nid), float(score), float(surprise), 0, None)
            for nid, score, surprise in neighbors
        ]
    seed_plot = plot_blob(seed)
    seed_tokens = metadata_overlap_tokens(seed)
    peer_ids = [int(nid) for nid, _s, _u in neighbors]
    peer_rows = {
        int(row["id"]): row
        for row in (db.library_item_by_id(pid) for pid in peer_ids)
        if row is not None
    }
    crew_names = _director_writer_names(db, [int(seed_id), *peer_ids])
    crew_names |= _directors_field_names(seed)
    for peer in peer_rows.values():
        crew_names |= _directors_field_names(peer)
    enriched: List[Tuple[int, float, float, int, Optional[str]]] = []
    for neighbor_id, score, surprise in neighbors:
        peer = peer_rows.get(int(neighbor_id))
        if peer is None:
            enriched.append((int(neighbor_id), float(score), float(surprise), 0, None))
            continue
        peer_tokens = metadata_overlap_tokens(peer)
        link = specific_plot_link(
            seed_text=seed_plot,
            peer_text=plot_blob(peer),
            shelf_labels=_shelf_label_set(seed_tokens | peer_tokens) | crew_names,
        )
        # Non-null JSON (including "{}") marks the row as evaluated so idle
        # annotate does not revisit cosine-only peers forever.
        link_json = plot_link_json(link) or "{}"
        enriched.append(
            (
                int(neighbor_id),
                float(score),
                float(surprise),
                1 if link else 0,
                link_json,
            )
        )
    return enriched


def annotate_explainable_neighbors(
    db: Database,
    seed_ids: Sequence[int],
) -> int:
    """Backfill ``explainable`` / ``plot_link_json`` on existing neighbor rows.

    Cheap idle pass: does not re-run cosine; re-evaluates plot text only.
    Returns the number of seed ids annotated.
    """
    annotated = 0
    for seed_id in seed_ids:
        seed_id = int(seed_id)
        raw = db.get_neighbors(seed_id, mode="similar", limit=100, explainable_only=False)
        if not raw:
            continue
        triples = [
            (
                int(row["neighbor_id"]),
                float(row["score"] or 0),
                float(row["surprise_score"] or 0) if "surprise_score" in row.keys() else 0.0,
            )
            for row in raw
        ]
        db.set_neighbors(seed_id, enrich_neighbors_with_explanations(db, seed_id, triples))
        annotated += 1
    return annotated


def refresh_neighbors_for_items(
    db: Database,
    seed_ids: Sequence[int],
    *,
    top_k: int = DEFAULT_TOP_K,
) -> int:
    """Compute and store neighbors for each seed id. Returns seeds processed."""
    # Exact cosine still needs the candidate corpus. Measured 2026-10-28 on an
    # Automat copy: 5426 × 384-dim JSON TEXT, ``get_embeddings`` 0.87s, 15-seed
    # refresh 4.3s — fine under the 10k gate. Do not switch to BLOBs / sqlite-vec
    # as a required dep until that measurement says otherwise.
    embeddings = db.get_embeddings()
    if not embeddings:
        return 0
    emb_map = {item_id: vector for item_id, vector in embeddings}
    token_map = build_item_token_map(db, emb_map.keys())
    all_candidates = [
        (item_id, vector, token_map.get(item_id, set()))
        for item_id, vector in embeddings
    ]
    use_ann = vec_available()
    ann_limit = max(int(top_k) * ANN_CANDIDATE_MULTIPLIER, 64)
    ann_limit = min(ann_limit, ANN_CANDIDATE_CAP)
    # Rebuild shadow index once per batch when ANN is available.
    if use_ann:
        from projectionist.library.vec_index import ensure_vec_index

        use_ann = ensure_vec_index(db, embeddings)

    processed = 0
    for seed_id in seed_ids:
        seed_id = int(seed_id)
        seed_vector = emb_map.get(seed_id)
        if seed_vector is None:
            continue
        candidates = all_candidates
        if use_ann:
            prefilter = ann_candidate_ids(
                db,
                seed_vector,
                limit=ann_limit,
                exclude_ids={seed_id},
            )
            if prefilter is not None:
                wanted = set(prefilter)
                candidates = [row for row in all_candidates if row[0] in wanted]
        neighbors = compute_neighbors_for_seed(
            seed_id,
            seed_vector,
            token_map.get(seed_id, set()),
            candidates,
            top_k=top_k,
        )
        db.set_neighbors(
            seed_id,
            enrich_neighbors_with_explanations(db, seed_id, neighbors),
        )
        processed += 1
    return processed
