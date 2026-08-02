"""Deterministic NL → structured gap-arg inference (no LLM).

Uses the facet alias registry for genre/tv-type/negation rules so new synonyms
grow in JSON, not in the agent tool registry.
"""

from __future__ import annotations

import re
from datetime import datetime as _dt
from typing import Any, Dict, Mapping, Optional

from projectionist.facets.registry import FacetRegistry, get_registry


def is_descriptive_ask(query: str, registry: Optional[FacetRegistry] = None) -> bool:
    """True for natural-language gap asks — not short brand/title needles."""
    reg = registry or get_registry()
    words = re.findall(r"[a-z0-9']+", (query or "").casefold())
    if len(words) >= reg.intent.descriptive_ask_min_words:
        return True
    normalized = {w.replace("'", "") for w in words}
    return bool(normalized & reg.intent.descriptive_ask_glue)


def augment_gaps_args_from_query(
    args: Mapping[str, Any],
    *,
    registry: Optional[FacetRegistry] = None,
    now: Optional[_dt] = None,
) -> Dict[str, Any]:
    """Infer structured discover filters from NL query; drop sentence-as-search."""
    reg = registry or get_registry()
    out: Dict[str, Any] = dict(args)
    query = str(out.get("query") or "").strip()
    if not query:
        return out
    q = query.casefold()
    clock = now or _dt.now()

    for negation in reg.intent.negations:
        try:
            matched = re.search(negation.pattern, query, re.IGNORECASE)
        except re.error:
            matched = None
        if not matched:
            continue
        if negation.without_genres and not str(out.get("without_genres") or "").strip():
            out["without_genres"] = negation.without_genres
        if negation.without_keywords and not str(out.get("without_keywords") or "").strip():
            out["without_keywords"] = negation.without_keywords

    for hint in reg.intent.tv_type_hints:
        try:
            matched = re.search(hint.pattern, q)
        except re.error:
            matched = None
        if not matched:
            continue
        if not str(out.get("tv_type") or "").strip():
            out["tv_type"] = hint.tv_type
        if hint.media_type:
            out["media_type"] = hint.media_type

    for hint in reg.intent.genre_hints:
        try:
            matched = re.search(hint.pattern, q)
        except re.error:
            matched = None
        if not matched:
            continue
        if not str(out.get("genres") or "").strip():
            out["genres"] = hint.genres
        if hint.prefer_media_type and str(out.get("media_type") or "") != "movie":
            out["media_type"] = hint.prefer_media_type

    if reg.intent.recent_pattern:
        try:
            recent_hit = re.search(reg.intent.recent_pattern, q)
        except re.error:
            recent_hit = None
        if recent_hit and out.get("year_from") is None:
            out["year_from"] = clock.year - reg.intent.recent_years_lookback

    # Sentence-shaped asks must not hit search_tv — that yields mismatched IDs.
    if is_descriptive_ask(query, registry=reg) and (
        str(out.get("tv_type") or "").strip()
        or str(out.get("genres") or "").strip()
        or str(out.get("without_genres") or "").strip()
    ):
        out["query"] = ""
    return out
