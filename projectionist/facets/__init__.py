"""Data-driven layered facet taxonomy for TMDB + library discover paths.

Add synonyms and TV↔movie remaps in ``facets/data/taxonomy.json`` (or a
``DATA_DIR/taxonomy.json`` / ``facet_aliases.json`` overlay). Tool registry
code should call these helpers — not grow frozen alias dicts.

Layers: ``concepts`` (canonical names) / ``aliases`` (tokens → concept) /
``packs`` (keyword unions + theme filters). Discover genre ids resolve against
**live** TMDB lists only.
"""

from projectionist.facets.closed_loop import (
    bind_closed_loop_database,
    resolve_closed_loop_database,
    schedule_unmapped_facet_tokens,
)
from projectionist.facets.intent import augment_gaps_args_from_query, is_descriptive_ask
from projectionist.facets.overlay import promote_facet_alias_to_overlay
from projectionist.facets.registry import (
    FacetConcept,
    FacetPack,
    FacetRegistry,
    get_registry,
    load_facet_registry,
    reload_registry,
    reset_registry_cache,
)
from projectionist.facets.resolve import (
    filter_pack_keyword_hits,
    gap_theme_tokens,
    genres_match_pack,
    item_text_relevance,
    match_facet_pack,
    motif_search_expansions,
    normalize_tv_type,
    resolve_genre_ids,
)

__all__ = [
    "FacetConcept",
    "FacetPack",
    "FacetRegistry",
    "augment_gaps_args_from_query",
    "bind_closed_loop_database",
    "filter_pack_keyword_hits",
    "gap_theme_tokens",
    "genres_match_pack",
    "get_registry",
    "is_descriptive_ask",
    "item_text_relevance",
    "load_facet_registry",
    "match_facet_pack",
    "motif_search_expansions",
    "normalize_tv_type",
    "promote_facet_alias_to_overlay",
    "reload_registry",
    "reset_registry_cache",
    "resolve_closed_loop_database",
    "resolve_genre_ids",
    "schedule_unmapped_facet_tokens",
]
