"""Agent tool definitions and execution.

Domain implementations live in sibling modules; this package is the
public registry surface. Tool count is frozen — add tools by editing
``_definitions.py`` and a domain mixin, not a plugin loader.
"""

from __future__ import annotations

from datetime import datetime as _dt

from projectionist.config_store import plex_collections_configuration_error
from projectionist.connectors.radarr import RadarrClient
from projectionist.connectors.seerr import SeerrClient
from projectionist.connectors.sonarr import SonarrClient
from projectionist.connectors.tmdb import TMDBClient
from projectionist.library.external_search import (
    _apply_queue_flags,
    _enrich_show_external_ids,
    _rank_tmdb_search_results,
    _titles_roughly_match,
    _tmdb_card,
    _tmdb_result_year,
    _tmdb_search_item_to_tool_item,
    external_tmdb_search,
)
from projectionist.library.search import search_library

from projectionist.agent.tools._definitions import (
    PLEX_COLLECTION_TOOL_NAMES,
    SEERR_TOOL_NAMES,
    TOOL_DEFINITIONS,
    build_tool_definitions,
)
from projectionist.agent.tools._helpers import (
    UNTRUSTED_DATA_CLOSE,
    UNTRUSTED_DATA_OPEN,
    UNTRUSTED_MEMORY_TOOLS,
    _append_recommendation_cards,
    _callback_title_metadata,
    _card_to_tool_item,
    _enrich_memory_note_deep_link,
    _excluded_add_tmdb_ids,
    _query_item_to_tool_item,
    wrap_untrusted_data,
)
from projectionist.agent.tools.confirmed import (
    check_radarr_already_exists,
    check_sonarr_already_exists,
    execute_confirmed_action,
    mark_in_radarr,
    mark_in_sonarr,
    resolve_arr_removal_target,
    resolve_radarr_search_for_movie,
)
from projectionist.agent.tools.prompt import _persona_prompt_block, build_system_prompt
from projectionist.agent.tools.registry import ToolRegistry

__all__ = [
    "PLEX_COLLECTION_TOOL_NAMES",
    "RadarrClient",
    "SEERR_TOOL_NAMES",
    "SeerrClient",
    "SonarrClient",
    "TMDBClient",
    "TOOL_DEFINITIONS",
    "ToolRegistry",
    "UNTRUSTED_DATA_CLOSE",
    "UNTRUSTED_DATA_OPEN",
    "UNTRUSTED_MEMORY_TOOLS",
    "_append_recommendation_cards",
    "_apply_queue_flags",
    "_callback_title_metadata",
    "_card_to_tool_item",
    "_dt",
    "_enrich_memory_note_deep_link",
    "_enrich_show_external_ids",
    "_excluded_add_tmdb_ids",
    "_tmdb_card",
    "_tmdb_result_year",
    "_tmdb_search_item_to_tool_item",
    "_titles_roughly_match",
    "external_tmdb_search",
    "_persona_prompt_block",
    "_query_item_to_tool_item",
    "_rank_tmdb_search_results",
    "build_system_prompt",
    "build_tool_definitions",
    "check_radarr_already_exists",
    "check_sonarr_already_exists",
    "execute_confirmed_action",
    "mark_in_radarr",
    "mark_in_sonarr",
    "plex_collections_configuration_error",
    "resolve_arr_removal_target",
    "resolve_radarr_search_for_movie",
    "search_library",
    "wrap_untrusted_data",
]
