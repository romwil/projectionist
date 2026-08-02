"""Fail-closed genre / TV-type / facet-pack resolution against live TMDB lists."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set

from projectionist.facets.registry import FacetPack, FacetRegistry, get_registry


def normalize_tv_type(raw: Any, registry: Optional[FacetRegistry] = None) -> Optional[str]:
    """Map tv_type labels to TMDB discover ``with_type`` ids (data-driven)."""
    reg = registry or get_registry()
    key = str(raw or "").strip().casefold()
    if not key:
        return None
    if key.isdigit():
        return key
    return reg.tv_types.get(key)


def _genre_ids_for_names(
    genre_list: Sequence[Mapping[str, Any]],
    names: Sequence[str],
) -> Set[int]:
    """Resolve genre display names against a live TMDB genre list (exact, casefold)."""
    by_name = {
        str(entry.get("name") or "").strip().casefold(): int(entry["id"])
        for entry in genre_list or []
        if entry.get("id") is not None and str(entry.get("name") or "").strip()
    }
    out: Set[int] = set()
    for name in names:
        gid = by_name.get(str(name or "").strip().casefold())
        if gid is not None:
            out.add(gid)
    return out


def resolve_genre_ids(
    genre_list: Sequence[Mapping[str, Any]],
    genres_text: str,
    registry: Optional[FacetRegistry] = None,
    *,
    emit_telemetry: bool = True,
    context_source: str = "resolve",
    media_type: Optional[str] = None,
) -> Dict[str, Any]:
    """Resolve genre names with aliases + unique substring match.

    Returns resolved ids, unresolved names, and ambiguous queries with candidates
    so callers can clarify instead of inventing ids or falling through unfiltered.

    Unresolved tokens schedule P1 closed-loop ``unmapped_token`` events when a
    Database is bound (``facets.closed_loop.bind_closed_loop_database``). Telemetry
    is fire-and-forget and never blocks this hot path.
    """
    reg = registry or get_registry()
    by_name: Dict[str, Mapping[str, Any]] = {}
    for entry in genre_list or []:
        name = str(entry.get("name") or "").strip()
        if not name or entry.get("id") is None:
            continue
        by_name[name.casefold()] = entry

    resolved: List[Dict[str, Any]] = []
    unresolved: List[str] = []
    ambiguous: List[Dict[str, Any]] = []
    matched_ids: List[str] = []
    seen_ids: Set[int] = set()

    for raw in str(genres_text or "").split(","):
        wanted = raw.strip()
        if not wanted:
            continue
        lookup_names = reg.lookup_names_for(wanted)
        alias = reg.alias_canonical(wanted)

        exact = None
        display_name = wanted
        for candidate_name in lookup_names:
            hit = by_name.get(candidate_name.casefold())
            if hit is not None:
                exact = hit
                display_name = candidate_name
                break
        if exact is not None:
            gid = int(exact["id"])
            if gid not in seen_ids:
                seen_ids.add(gid)
                matched_ids.append(str(gid))
                resolved.append(
                    {"id": gid, "name": str(exact.get("name") or display_name), "query": wanted}
                )
            continue

        lookup = (alias or wanted).casefold()
        subs = [
            entry
            for name_cf, entry in by_name.items()
            if lookup in name_cf or name_cf in lookup
        ]
        uniq: List[Mapping[str, Any]] = []
        seen_sub: Set[int] = set()
        for entry in subs:
            gid = int(entry["id"])
            if gid in seen_sub:
                continue
            seen_sub.add(gid)
            uniq.append(entry)

        if len(uniq) == 1:
            entry = uniq[0]
            gid = int(entry["id"])
            if gid not in seen_ids:
                seen_ids.add(gid)
                matched_ids.append(str(gid))
                resolved.append(
                    {
                        "id": gid,
                        "name": str(entry.get("name") or display_name),
                        "query": wanted,
                    }
                )
            continue
        if len(uniq) > 1:
            ambiguous.append(
                {
                    "query": wanted,
                    "candidates": [
                        {"id": int(e["id"]), "name": str(e.get("name") or "")} for e in uniq
                    ],
                }
            )
            continue
        unresolved.append(wanted)

    candidates_flat: List[Dict[str, Any]] = []
    seen_cand: Set[int] = set()
    for group in ambiguous:
        for cand in group.get("candidates") or []:
            cid = int(cand["id"])
            if cid in seen_cand:
                continue
            seen_cand.add(cid)
            candidates_flat.append(cand)

    if emit_telemetry and unresolved:
        # Import lazily so unit tests that only exercise resolve stay light.
        from projectionist.facets.closed_loop import schedule_unmapped_facet_tokens

        schedule_unmapped_facet_tokens(
            unresolved,
            context_source=context_source,
            media_type=media_type,
        )

    return {
        "resolved": resolved,
        "unresolved": unresolved,
        "ambiguous": ambiguous,
        "genres_candidates": candidates_flat,
        "genre_ids": ",".join(matched_ids) if matched_ids else "",
    }


def match_facet_pack(
    genres_text: str,
    *,
    pack_id: Optional[str] = None,
    registry: Optional[FacetRegistry] = None,
) -> Optional[FacetPack]:
    """Return the first facet pack whose pattern/aliases match ``genres_text``."""
    reg = registry or get_registry()
    text = str(genres_text or "").strip()
    if not text:
        return None
    folded = text.casefold()
    packs = (
        [reg.facet_packs[pack_id]]
        if pack_id and pack_id in reg.facet_packs
        else list(reg.facet_packs.values())
    )
    for pack in packs:
        for alias in pack.match_aliases:
            if alias.casefold() in folded or folded == alias.casefold():
                return pack
        if pack.match_pattern:
            try:
                if re.search(pack.match_pattern, folded, re.IGNORECASE):
                    return pack
            except re.error:
                continue
    return None


def genres_match_pack(
    genres_text: str,
    pack_id: str,
    registry: Optional[FacetRegistry] = None,
) -> bool:
    pack = match_facet_pack(genres_text, pack_id=pack_id, registry=registry)
    return pack is not None and pack.id == pack_id


def item_text_relevance(item: Mapping[str, Any], theme_tokens: Sequence[str]) -> int:
    """Score a discover/search hit against theme tokens (title + overview)."""
    if not theme_tokens:
        return 1
    hay = " ".join(
        [
            str(item.get("title") or item.get("name") or ""),
            str(item.get("original_title") or item.get("original_name") or ""),
            str(item.get("overview") or ""),
        ]
    ).casefold()
    if not hay.strip():
        return 0
    return sum(1 for tok in theme_tokens if tok.casefold() in hay)


def filter_pack_keyword_hits(
    items: Sequence[Mapping[str, Any]],
    pack: FacetPack,
    *,
    genre_list: Optional[Sequence[Mapping[str, Any]]] = None,
) -> List[Mapping[str, Any]]:
    """Keep keyword-union hits that match the pack (drop off-theme noise).

    Rules (all data-driven from the pack + live genre list):
    * ``keep_genre_names`` resolved against ``genre_list`` always pass
    * ``reject_genre_names`` need a ``strong_theme_tokens`` hit
    * strong theme hits pass
    * soft ``theme_tokens`` pass unless overview matches a reject pattern

    Discover genre ids are never trusted from seed — pass the live list.
    """
    keep_ids = (
        _genre_ids_for_names(genre_list, pack.keep_genre_names) if genre_list is not None else set()
    )
    reject_ids = (
        _genre_ids_for_names(genre_list, pack.reject_genre_names)
        if genre_list is not None
        else set()
    )
    strong = pack.strong_theme_tokens
    soft = pack.theme_tokens
    reject_patterns = []
    for pattern in pack.reject_overview_patterns:
        try:
            reject_patterns.append(re.compile(pattern, re.IGNORECASE))
        except re.error:
            continue

    kept: List[Mapping[str, Any]] = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        try:
            genre_ids = {int(g) for g in (item.get("genre_ids") or [])}
        except (TypeError, ValueError):
            genre_ids = set()
        if keep_ids and genre_ids & keep_ids:
            kept.append(item)
            continue
        # Reject-tagged titles (e.g. Crime) need a strong period/war signal.
        if reject_ids and genre_ids & reject_ids:
            if strong and item_text_relevance(item, strong) > 0:
                kept.append(item)
            continue
        if strong and item_text_relevance(item, strong) > 0:
            kept.append(item)
            continue
        if soft and item_text_relevance(item, soft) > 0:
            hay = " ".join(
                [
                    str(item.get("title") or item.get("name") or ""),
                    str(item.get("overview") or ""),
                ]
            ).casefold()
            if any(rx.search(hay) for rx in reject_patterns):
                continue
            kept.append(item)
    return kept


def motif_search_expansions(
    name: str,
    registry: Optional[FacetRegistry] = None,
) -> List[str]:
    """Expand a station/motif name into search terms from the alias registry."""
    reg = registry or get_registry()
    name_l = str(name or "").strip().casefold()
    if not name_l:
        return []
    compact = name_l.replace(" ", "").replace("-", "")
    terms: List[str] = []
    for key, words in reg.motif_search_aliases.items():
        key_compact = key.replace(" ", "").replace("-", "")
        if key in name_l or key_compact in compact:
            for word in words:
                w = str(word).strip()
                if w and w.casefold() not in {t.casefold() for t in terms}:
                    terms.append(w)
    return terms


def gap_theme_tokens(
    *parts: str,
    registry: Optional[FacetRegistry] = None,
) -> List[str]:
    """Normalize free-text theme tokens for post-filter relevance scoring."""
    reg = registry or get_registry()
    stop = reg.intent.theme_stopwords
    tokens: List[str] = []
    seen: Set[str] = set()
    for part in parts:
        for raw in re.split(r"[\s,/|;]+", str(part or "").strip().lower()):
            tok = raw.strip(".,!?:;\"'()[]")
            if len(tok) < 3 or tok in stop or tok in seen:
                continue
            seen.add(tok)
            tokens.append(tok)
    return tokens
