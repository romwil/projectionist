"""Agent tool definitions and execution."""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any, Callable, Dict, List, Mapping, Optional

from curatorx.config_store import (
    Settings,
    plex_collections_configuration_error,
    radarr_add_configuration_error,
    resolve_radarr_root_folder,
    resolve_sonarr_root_folder,
    seerr_configuration_error,
    sonarr_add_configuration_error,
    validate_arr_root_folder,
)
from curatorx.connectors.arr_errors import ArrTitleExistsError, ArrTitleNotFoundError
from curatorx.connectors.radarr import RadarrClient
from curatorx.connectors.seerr import SeerrClient
from curatorx.connectors.sonarr import SonarrClient
from curatorx.connectors.tmdb import TMDBClient
from curatorx.library.db import Database
from curatorx.library.episodes import query_episodes, summarize_tv_progress
from curatorx.library.facets import library_facet_catalog
from curatorx.library.query import (
    LibraryFilters,
    _build_where,
    aggregate_library,
    build_facet_match_details,
    filters_from_mapping,
    format_overview_for_prompt,
    library_overview,
    maybe_set_audit_context_label,
    query_library,
    query_library_async,
    row_to_query_item,
)
from curatorx.library.search import row_to_title_card, search_library
from curatorx.library.titles import get_title_detail
from curatorx.models.recommendation import sanitize_recommendation_reason
from curatorx.models.schemas import TitleCard
from curatorx.preferences.purge import suggest_purge_candidates
from curatorx.preferences.store import preference_context, remember_preference
from curatorx.reviews.store import get_reviews, list_pending_prompts, list_titles_to_rate, mark_prompts_surfaced, save_review
from curatorx.reviews.plex_sync import sync_review_rating_to_plex

logger = logging.getLogger(__name__)


TOOL_DEFINITIONS: List[Mapping[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_library",
            "description": (
                "Search the user's Plex library by theme, genre, title, or mood. "
                "Uses semantic/fuzzy matching over owned titles — not for exact external TMDB lookups."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "media_type": {"type": "string", "enum": ["movie", "show"]},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_collection_gaps",
            "description": "Find movies or shows missing from the library for a genre/decade/theme query.",
            "parameters": {
                "type": "object",
                "properties": {
                    "media_type": {"type": "string", "enum": ["movie", "show"]},
                    "year_from": {"type": "integer"},
                    "year_to": {"type": "integer"},
                    "genres": {"type": "string", "description": "Comma-separated genre names"},
                    "keywords": {"type": "string", "description": "Theme keywords"},
                },
                "required": ["media_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recommend_hidden_gems",
            "description": "Recommend highly rated titles not in the library, filtered by taste.",
            "parameters": {
                "type": "object",
                "properties": {
                    "media_type": {"type": "string", "enum": ["movie", "show"]},
                    "query": {"type": "string"},
                },
                "required": ["media_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "suggest_purge_candidates",
            "description": "Find library items wasting drive space that are unlikely to be watched.",
            "parameters": {"type": "object", "properties": {"limit": {"type": "integer"}}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remember_preference",
            "description": "Store an explicit user taste preference for future recommendations.",
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_to_radarr",
            "description": "Propose adding a movie to Radarr. Returns a confirmation token.",
            "parameters": {
                "type": "object",
                "properties": {"tmdb_id": {"type": "integer"}, "title": {"type": "string"}},
                "required": ["tmdb_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_to_sonarr",
            "description": "Propose adding a TV show to Sonarr. Returns a confirmation token.",
            "parameters": {
                "type": "object",
                "properties": {"tvdb_id": {"type": "integer"}, "title": {"type": "string"}},
                "required": ["tvdb_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "request_via_seerr",
            "description": (
                "Queue a movie or TV show request in Seerr for household members. "
                "Always returns a confirmation token; the user must confirm before submit."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "media_type": {"type": "string", "enum": ["movie", "show"]},
                    "tmdb_id": {"type": "integer"},
                    "tvdb_id": {"type": "integer"},
                    "title": {"type": "string"},
                },
                "required": ["media_type", "tmdb_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "approve_seerr_request",
            "description": "Approve a pending Seerr media request by request id (owner only).",
            "parameters": {
                "type": "object",
                "properties": {"request_id": {"type": "integer"}},
                "required": ["request_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_seerr_movie",
            "description": "Search Seerr/Overseerr for movies to request (requires Seerr enabled).",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Movie title to search"},
                    "limit": {"type": "integer"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_seerr_tv",
            "description": "Search Seerr/Overseerr for TV shows to request (requires Seerr enabled).",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "TV show title to search"},
                    "limit": {"type": "integer"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remove_from_arr",
            "description": (
                "Propose removing a title from Radarr/Sonarr. Returns a confirmation token. "
                "Prefer tmdb_id for movies and tvdb_id for shows so the correct Radarr/Sonarr id is resolved."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "media_type": {"type": "string", "enum": ["movie", "show"]},
                    "arr_id": {"type": "integer", "description": "Radarr/Sonarr internal id (optional if tmdb_id/tvdb_id provided)"},
                    "tmdb_id": {"type": "integer", "description": "TMDB id for movies"},
                    "tvdb_id": {"type": "integer", "description": "TVDB id for shows"},
                    "title": {"type": "string"},
                    "delete_files": {"type": "boolean"},
                },
                "required": ["media_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_tmdb",
            "description": (
                "Resolve an external movie/show on TMDB before add_to_radarr/add_to_sonarr. "
                "Prefer tmdb_id when known (exact one title card). Otherwise pass title+year "
                "so same-name hits are not expanded into multiple turnstyle cards. "
                "Title-only search may return several candidates for disambiguation. "
                "Pass reason with a specific curator rationale for why this title fits "
                "(taste/context — never pipeline labels like 'TMDB title match')."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Title to look up on TMDB (required unless tmdb_id is set)",
                    },
                    "tmdb_id": {
                        "type": "integer",
                        "description": (
                            "Exact TMDB id when already known — returns that single work only "
                            "(preferred over title search for recommendations)."
                        ),
                    },
                    "year": {
                        "type": "integer",
                        "description": (
                            "Release/air year — when set, only that year is returned as cards "
                            "(does not expand to other years with the same title)."
                        ),
                    },
                    "media_type": {"type": "string", "enum": ["movie", "show"]},
                    "limit": {"type": "integer", "description": "Max results to return (default 10)"},
                    "reason": {
                        "type": "string",
                        "description": (
                            "Optional curator rationale shown on the title card Why this? — "
                            "specific to taste/context, not an internal search source label."
                        ),
                    },
                },
                "required": ["media_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_recommendation_reasons",
            "description": (
                "Attach curator rationale to title cards already returned this turn. "
                "Use after search_tmdb / gap tools so Why this? shows taste-based reasons, "
                "not pipeline labels. One short sentence per title."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reasons": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "tmdb_id": {"type": "integer"},
                                "reason": {"type": "string"},
                            },
                            "required": ["tmdb_id", "reason"],
                        },
                        "description": "List of {tmdb_id, reason} pairs for cards already attached",
                    },
                },
                "required": ["reasons"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_title_detail",
            "description": "Get rich metadata for a specific title by TMDB/TVDB id or Plex rating key.",
            "parameters": {
                "type": "object",
                "properties": {
                    "media_type": {"type": "string", "enum": ["movie", "show"]},
                    "tmdb_id": {"type": "integer"},
                    "tvdb_id": {"type": "integer"},
                    "rating_key": {"type": "string"},
                },
                "required": ["media_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "explore_genre",
            "description": (
                "Browse a genre: owned titles (include_missing=false) or TMDB gaps to add "
                "(include_missing=true). Do not use for add recommendations when the user only "
                "wants missing titles — prefer find_collection_gaps or recommend_hidden_gems."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "genre": {"type": "string"},
                    "media_type": {"type": "string", "enum": ["movie", "show"]},
                    "include_missing": {
                        "type": "boolean",
                        "description": "When true, include TMDB titles not in library (add candidates)",
                    },
                },
                "required": ["genre", "media_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "what_to_watch_tonight",
            "description": "Suggest unwatched or under-watched library titles for tonight.",
            "parameters": {
                "type": "object",
                "properties": {
                    "media_type": {"type": "string", "enum": ["movie", "show"]},
                    "limit": {"type": "integer"},
                    "mood": {"type": "string", "description": "Optional mood or theme filter"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_library",
            "description": (
                "Browse titles the user already owns with rich filters. "
                "Supports year/decade, genre, director, cast, keywords, runtime, ratings, "
                "date added (added_from, added_to, recently_added_days, sort=added_at), "
                "watch history (last_viewed_from/to, stale_days, view_count), file_size for purge, "
                "Radarr/Sonarr presence (in_radarr, in_sonarr), "
                "semantic_query, fts_query, and TV progress fields. Returns total_matched and has_more."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "media_type": {"type": "string", "enum": ["movie", "show"]},
                    "year_from": {"type": "integer"},
                    "year_to": {"type": "integer"},
                    "genres": {"type": "string", "description": "Comma-separated genre names"},
                    "directors": {"type": "string", "description": "Comma-separated director names"},
                    "cast": {"type": "string", "description": "Comma-separated actor names"},
                    "keywords": {"type": "string", "description": "Comma-separated theme keywords"},
                    "countries": {"type": "string", "description": "Comma-separated countries"},
                    "content_ratings": {"type": "string", "description": "Comma-separated content ratings"},
                    "original_language": {"type": "string"},
                    "query": {"type": "string", "description": "Keyword filter on title/summary"},
                    "fts_query": {"type": "string", "description": "Full-text search across metadata"},
                    "semantic_query": {"type": "string", "description": "Mood/theme semantic search"},
                    "unwatched_only": {"type": "boolean"},
                    "min_view_count": {"type": "integer", "description": "Minimum play count"},
                    "max_view_count": {"type": "integer", "description": "Maximum play count (0 = never watched)"},
                    "stale_days": {
                        "type": "integer",
                        "description": "Not watched in this many days (includes never watched)",
                    },
                    "recently_added_days": {
                        "type": "integer",
                        "description": "Added to Plex within the last N days",
                    },
                    "added_from": {
                        "type": "string",
                        "description": "Added on/after date (YYYY-MM-DD or unix timestamp)",
                    },
                    "added_to": {
                        "type": "string",
                        "description": "Added on/before date (YYYY-MM-DD or unix timestamp)",
                    },
                    "last_viewed_from": {
                        "type": "string",
                        "description": "Last watched on/after date (YYYY-MM-DD or unix timestamp)",
                    },
                    "last_viewed_to": {
                        "type": "string",
                        "description": "Last watched on/before date (YYYY-MM-DD or unix timestamp)",
                    },
                    "runtime_min": {"type": "integer"},
                    "runtime_max": {"type": "integer"},
                    "vote_min": {"type": "number"},
                    "vote_max": {"type": "number"},
                    "file_size_min": {"type": "integer", "description": "Minimum file size in bytes"},
                    "file_size_max": {"type": "integer", "description": "Maximum file size in bytes"},
                    "in_radarr": {
                        "type": "boolean",
                        "description": "Filter by Radarr presence (false = in Plex but missing from Radarr)",
                    },
                    "in_sonarr": {
                        "type": "boolean",
                        "description": "Filter by Sonarr presence (false = in Plex but missing from Sonarr)",
                    },
                    "missing_tmdb_id": {
                        "type": "boolean",
                        "description": "Titles without TMDB id (metadata gaps)",
                    },
                    "in_progress_only": {"type": "boolean", "description": "Shows partially watched"},
                    "sort": {
                        "type": "string",
                        "enum": [
                            "title",
                            "year",
                            "view_count",
                            "file_size",
                            "vote_average",
                            "runtime_minutes",
                            "added_at",
                            "last_viewed_at",
                            "unwatched_episode_count",
                        ],
                    },
                    "offset": {"type": "integer"},
                    "limit": {"type": "integer", "description": "Max 50 per page"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "summarize_library",
            "description": (
                "Aggregate owned library counts without listing every title. "
                "group_by: decade, year, genre, media_type, director, actor, keyword, "
                "country, language, content_rating, runtime_bucket, decade_genre."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "group_by": {
                        "type": "string",
                        "enum": [
                            "decade",
                            "year",
                            "genre",
                            "media_type",
                            "director",
                            "actor",
                            "keyword",
                            "country",
                            "language",
                            "content_rating",
                            "runtime_bucket",
                            "decade_genre",
                        ],
                    },
                    "media_type": {"type": "string", "enum": ["movie", "show"]},
                    "year_from": {"type": "integer"},
                    "year_to": {"type": "integer"},
                    "genres": {"type": "string", "description": "Comma-separated genre names"},
                },
                "required": ["group_by"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_library_overview",
            "description": "Get compact library inventory stats: totals, decades, genres, directors, TV progress.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_facet_catalog",
            "description": "List top directors, actors, keywords, countries, or languages in the owned library.",
            "parameters": {
                "type": "object",
                "properties": {
                    "facet_type": {
                        "type": "string",
                        "enum": ["director", "actor", "keyword", "country", "language"],
                    },
                    "limit": {"type": "integer"},
                },
                "required": ["facet_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_tv_episodes",
            "description": "Browse unwatched or all episodes for a TV show the user owns.",
            "parameters": {
                "type": "object",
                "properties": {
                    "show": {"type": "string", "description": "Show title"},
                    "show_id": {"type": "integer"},
                    "season": {"type": "integer"},
                    "unwatched_only": {"type": "boolean"},
                    "offset": {"type": "integer"},
                    "limit": {"type": "integer"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "summarize_tv_progress",
            "description": "Summarize TV completion progress by show or season.",
            "parameters": {
                "type": "object",
                "properties": {
                    "group_by": {"type": "string", "enum": ["show", "season"]},
                    "in_progress_only": {"type": "boolean"},
                    "limit": {"type": "integer"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_watch_patterns",
            "description": "Summarize viewing habits: top genres, stale titles, binge patterns.",
            "parameters": {
                "type": "object",
                "properties": {
                    "year_from": {"type": "integer"},
                    "year_to": {"type": "integer"},
                    "media_type": {"type": "string", "enum": ["movie", "show"]},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_user_reviews",
            "description": "Query the user's personal title reviews by title, rating, or media type.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "rating_key": {"type": "string"},
                    "tmdb_id": {"type": "integer"},
                    "media_type": {"type": "string", "enum": ["movie", "show"]},
                    "min_stars": {"type": "integer"},
                    "limit": {"type": "integer"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_user_review",
            "description": (
                "Save or update a personal review for a watched title. "
                "Stars accept half-star values (0.5–5 in 0.5 steps, e.g. 4.5). Never ask the user to round."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "media_type": {"type": "string", "enum": ["movie", "show"]},
                    "stars": {
                        "type": "number",
                        "minimum": 0.5,
                        "maximum": 5,
                        "description": "Star rating from 0.5 to 5 in 0.5 increments (half-stars allowed).",
                    },
                    "review_text": {"type": "string"},
                    "review_tags": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "rating_key": {"type": "string"},
                    "tmdb_id": {"type": "integer"},
                    "tvdb_id": {"type": "integer"},
                    "replace_plex_rating": {
                        "type": "boolean",
                        "description": "Overwrite an existing Plex star rating when it differs.",
                    },
                    "force_replace": {
                        "type": "boolean",
                        "description": "Alias for replace_plex_rating.",
                    },
                },
                "required": ["title", "media_type", "stars"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "suggest_titles_to_rate",
            "description": (
                "List ~10 recently viewed or near-complete titles without a personal review. "
                "Surfaces rateable cards in the UI — prefer this when the user asks to rate/review "
                "recently watched titles instead of multi-turn Q&A."
            ),
            "parameters": {
                "type": "object",
                "properties": {"limit": {"type": "integer"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "start_review_dialogue",
            "description": (
                "Optional persona-voiced multi-turn review dialogue for a single title. "
                "Prefer suggest_titles_to_rate for batch \"rate recently watched\" requests. "
                "Returns an opener from review_prompt_templates plus follow-up questions."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "media_type": {"type": "string", "enum": ["movie", "show"]},
                    "rating_key": {"type": "string"},
                    "template_key": {
                        "type": "string",
                        "enum": ["near_complete", "rewatch", "family"],
                    },
                    "completion_pct": {"type": "number"},
                },
                "required": ["title", "media_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_watchlist",
            "description": (
                "List titles the user pinned to their personal watchlist, "
                "including in_library / watched signals when matched."
            ),
            "parameters": {
                "type": "object",
                "properties": {"limit": {"type": "integer"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_to_watchlist",
            "description": (
                "Pin a title to the user's personal watchlist (and push to Plex Discover when sync is enabled). "
                "No confirmation token required."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "media_type": {"type": "string", "enum": ["movie", "show"]},
                    "tmdb_id": {"type": "integer"},
                    "tvdb_id": {"type": "integer"},
                },
                "required": ["title", "media_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remove_from_watchlist",
            "description": (
                "Remove a title from the user's personal watchlist by pin_id or tmdb/tvdb identity. "
                "No confirmation token required."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pin_id": {"type": "string"},
                    "title": {"type": "string"},
                    "media_type": {"type": "string", "enum": ["movie", "show"]},
                    "tmdb_id": {"type": "integer"},
                    "tvdb_id": {"type": "integer"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "curate_watchlist",
            "description": (
                "Suggest watchlist prune candidates (already watched) and note that adds should come from discovery tools. "
                "Does not silently delete pins."
            ),
            "parameters": {
                "type": "object",
                "properties": {"limit": {"type": "integer"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "critique_watchlist",
            "description": (
                "Persona-flavored commentary on the user's watchlist (roast stale pins, praise deep cuts). "
                "Read-only unless paired with explicit curate/remove actions."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "focus_title": {"type": "string"},
                    "limit": {"type": "integer"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_lists",
            "description": (
                "List the user's named CuratorX curated lists (local shelves; not Plex Lists). "
                "Returns id, name, description, and item_count."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_list",
            "description": (
                "Create a named curated list on CuratorX (local only; Plex Lists publish is not available). "
                "No confirmation token required."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_to_list",
            "description": (
                "Add a title to a named CuratorX curated list by list_id or list_name. "
                "Requires title + media_type and tmdb_id or tvdb_id. No confirmation token."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "list_id": {"type": "string"},
                    "list_name": {"type": "string"},
                    "title": {"type": "string"},
                    "media_type": {"type": "string", "enum": ["movie", "show"]},
                    "tmdb_id": {"type": "integer"},
                    "tvdb_id": {"type": "integer"},
                },
                "required": ["title", "media_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remove_from_list",
            "description": (
                "Remove a title from a named CuratorX curated list by item_id or tmdb/tvdb identity. "
                "Identify the list with list_id or list_name. No confirmation token."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "list_id": {"type": "string"},
                    "list_name": {"type": "string"},
                    "item_id": {"type": "string"},
                    "title": {"type": "string"},
                    "media_type": {"type": "string", "enum": ["movie", "show"]},
                    "tmdb_id": {"type": "integer"},
                    "tvdb_id": {"type": "integer"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "upcoming_premieres",
            "description": (
                "List upcoming episode premieres for TV shows in the user's library "
                "using TMDB next_episode_to_air metadata."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer"},
                    "days_ahead": {
                        "type": "integer",
                        "description": "How many days ahead to include (default 14)",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_plex_collections",
            "description": "List Plex collections in the user's movie or TV library section.",
            "parameters": {
                "type": "object",
                "properties": {
                    "media_type": {"type": "string", "enum": ["movie", "show"]},
                },
                "required": ["media_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_plex_collection",
            "description": (
                "Propose creating a Plex collection in the user's library. "
                "Returns a confirmation token before any Plex write."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Collection name"},
                    "media_type": {"type": "string", "enum": ["movie", "show"]},
                    "rating_keys": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional initial Plex rating keys to include",
                    },
                },
                "required": ["title", "media_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_to_plex_collection",
            "description": (
                "Propose adding owned titles to an existing Plex collection. "
                "Returns a confirmation token before any Plex write."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "collection_title": {
                        "type": "string",
                        "description": "Existing collection title (case-insensitive match)",
                    },
                    "collection_rating_key": {
                        "type": "string",
                        "description": "Existing collection rating key (preferred when known)",
                    },
                    "media_type": {"type": "string", "enum": ["movie", "show"]},
                    "rating_keys": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Plex rating keys to add",
                    },
                },
                "required": ["media_type", "rating_keys"],
            },
        },
    },
]


PLEX_COLLECTION_TOOL_NAMES = frozenset(
    {
        "list_plex_collections",
        "create_plex_collection",
        "add_to_plex_collection",
    }
)

SEERR_TOOL_NAMES = frozenset(
    {
        "request_via_seerr",
        "approve_seerr_request",
        "search_seerr_movie",
        "search_seerr_tv",
    }
)


def build_tool_definitions(settings: Settings) -> List[Mapping[str, Any]]:
    """Return LLM tool schemas with feature-gated tools omitted when disabled."""
    omitted: set[str] = set()
    if not settings.features.plex_collections_enabled:
        omitted |= PLEX_COLLECTION_TOOL_NAMES
    if not settings.features.seerr_enabled:
        omitted |= SEERR_TOOL_NAMES
    if not omitted:
        return list(TOOL_DEFINITIONS)
    return [
        tool
        for tool in TOOL_DEFINITIONS
        if str((tool.get("function") or {}).get("name") or "") not in omitted
    ]


def _tmdb_result_year(item: Mapping[str, Any]) -> Optional[int]:
    date = item.get("release_date") or item.get("first_air_date") or ""
    if not date:
        return None
    try:
        return int(str(date)[:4])
    except ValueError:
        return None


def _rank_tmdb_search_results(results: List[Mapping[str, Any]], *, year: Optional[int]) -> List[Mapping[str, Any]]:
    """Order/filter TMDB search hits.

    When ``year`` is set, keep only that release year so one recommendation
    (e.g. Mandy 2018) does not expand into every same-name hit.
    """
    ordered = list(results)
    if year is None:
        return ordered
    exact = [item for item in ordered if _tmdb_result_year(item) == year]
    return exact


def _tmdb_search_item_to_tool_item(item: Mapping[str, Any], media_type: str) -> Dict[str, Any]:
    title = str(item.get("title") or item.get("name") or "")
    overview = str(item.get("overview") or "")
    payload: Dict[str, Any] = {
        "title": title,
        "year": _tmdb_result_year(item),
        "media_type": media_type,
        "tmdb_id": int(item.get("id") or 0),
        "overview": overview[:200] if overview else "",
        "in_library": False,
    }
    if media_type == "show":
        external = item.get("external_ids") or {}
        if external.get("tvdb_id"):
            payload["tvdb_id"] = int(external["tvdb_id"])
    return payload


def _seerr_result_year(item: Mapping[str, Any]) -> Optional[int]:
    date = item.get("releaseDate") or item.get("firstAirDate") or item.get("release_date") or ""
    if not date:
        return None
    try:
        return int(str(date)[:4])
    except ValueError:
        return None


def _seerr_search_item_to_tool_item(item: Mapping[str, Any], media_type: str) -> Dict[str, Any]:
    title = str(item.get("title") or item.get("name") or "")
    overview = str(item.get("overview") or "")
    payload: Dict[str, Any] = {
        "title": title,
        "year": _seerr_result_year(item),
        "media_type": media_type,
        "overview": overview[:200] if overview else "",
        "in_library": False,
    }
    tmdb_id = item.get("tmdbId") or item.get("tmdb_id")
    tvdb_id = item.get("tvdbId") or item.get("tvdb_id")
    if tmdb_id is not None:
        payload["tmdb_id"] = int(tmdb_id)
    if tvdb_id is not None:
        payload["tvdb_id"] = int(tvdb_id)
    return payload


def _tmdb_card(item: Mapping[str, Any], media_type: str, tmdb: TMDBClient, *, reason: str = "") -> TitleCard:
    poster = tmdb.poster_url(item.get("poster_path"))
    backdrop = tmdb.backdrop_url(item.get("backdrop_path"))
    title = item.get("title") or item.get("name") or ""
    year = None
    date = item.get("release_date") or item.get("first_air_date") or ""
    if date:
        year = int(str(date)[:4])
    tvdb_id = None
    if media_type == "show":
        external = item.get("external_ids") or {}
        if external.get("tvdb_id"):
            tvdb_id = int(external["tvdb_id"])
    return TitleCard(
        media_type=media_type,  # type: ignore[arg-type]
        title=str(title),
        year=year,
        tmdb_id=int(item.get("id") or 0),
        tvdb_id=tvdb_id,
        poster_url=poster,
        backdrop_url=backdrop,
        overview=str(item.get("overview") or ""),
        rating=float(item.get("vote_average") or 0) or None,
        recommendation_reason=sanitize_recommendation_reason(reason),
        in_library=False,
    )


def _card_to_tool_item(card: TitleCard) -> Dict[str, Any]:
    item: Dict[str, Any] = {
        "title": card.title,
        "year": card.year,
        "media_type": card.media_type,
        "genres": list(card.genres or []),
        "view_count": getattr(card, "view_count", 0),
        "in_library": card.in_library,
    }
    if card.tmdb_id:
        item["tmdb_id"] = card.tmdb_id
    if card.tvdb_id:
        item["tvdb_id"] = card.tvdb_id
    if card.rating_key:
        item["rating_key"] = card.rating_key
    if card.in_radarr:
        item["in_radarr"] = True
    if card.in_sonarr:
        item["in_sonarr"] = True
    reason = sanitize_recommendation_reason(card.recommendation_reason)
    if reason:
        item["recommendation_reason"] = reason
    if getattr(card, "card_kind", None):
        item["card_kind"] = card.card_kind
    return item


def _query_item_to_tool_item(item: Mapping[str, Any]) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "title": item.get("title"),
        "year": item.get("year"),
        "media_type": item.get("media_type"),
        "genres": item.get("genres") or [],
        "directors": item.get("directors") or [],
        "cast": item.get("cast") or [],
        "keywords": item.get("keywords") or [],
        "view_count": item.get("view_count"),
        "runtime_minutes": item.get("runtime_minutes"),
        "vote_average": item.get("vote_average"),
        "content_rating": item.get("content_rating"),
        "unwatched_episode_count": item.get("unwatched_episode_count"),
        "total_episode_count": item.get("total_episode_count"),
        "in_library": True,
    }
    if item.get("tmdb_id"):
        payload["tmdb_id"] = item["tmdb_id"]
    if item.get("tvdb_id"):
        payload["tvdb_id"] = item["tvdb_id"]
    if item.get("rating_key"):
        payload["rating_key"] = item["rating_key"]
    return payload


def _enrich_show_external_ids(item: Mapping[str, Any], tmdb: TMDBClient) -> Mapping[str, Any]:
    if item.get("external_ids"):
        return item
    tmdb_id = int(item.get("id") or 0)
    if not tmdb_id:
        return item
    try:
        details = tmdb.tv_details(tmdb_id)
    except RuntimeError:
        return item
    return {**item, "external_ids": details.get("external_ids") or {}}


def _detail_to_tool_payload(detail: Any, settings: Settings) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "title": detail.title,
        "year": detail.year,
        "media_type": detail.media_type,
        "in_library": detail.in_library,
        "overview": detail.overview[:200] if detail.overview else "",
    }
    if detail.tmdb_id:
        payload["tmdb_id"] = detail.tmdb_id
    if detail.tvdb_id:
        payload["tvdb_id"] = detail.tvdb_id
    if detail.rating_key:
        payload["rating_key"] = detail.rating_key
    if not detail.title and not detail.overview:
        if not settings.tmdb_api_key and not detail.in_library:
            payload["error"] = "TMDB API key not configured — cannot look up external titles"
        else:
            payload["error"] = "No metadata found for the provided id"
    return payload


def _attach_query_cards(
    registry: "ToolRegistry",
    db: Database,
    items: List[Mapping[str, Any]],
    filters: Optional[LibraryFilters] = None,
) -> None:
    for item in items:
        row = db.library_item_by_id(int(item["id"])) if item.get("id") else None
        if row is not None:
            reason = "In your library"
            facet_matches: List[str] = []
            if filters is not None:
                reason, facet_matches = build_facet_match_details(filters, item)
            registry._cards.append(
                row_to_title_card(row, reason=reason, facet_matches=facet_matches)
            )


def _append_recommendation_cards(registry: "ToolRegistry", cards: List[TitleCard]) -> None:
    """Attach title cards for titles the user may want to add (never owned or already queued)."""
    registry._recommendation_context = True
    for card in cards:
        if card.in_library or card.in_radarr or card.in_sonarr:
            continue
        if card.tmdb_id and registry.db.is_arr_queued(media_type=card.media_type, tmdb_id=card.tmdb_id):
            card.in_radarr = card.media_type == "movie"
            card.in_sonarr = card.media_type == "show"
            continue
        if card.tvdb_id and registry.db.is_arr_queued(media_type="show", tvdb_id=card.tvdb_id):
            card.in_sonarr = True
            continue
        registry._cards.append(card)


def _excluded_add_tmdb_ids(db: Database, media_type: str) -> set[int]:
    return db.owned_tmdb_ids(media_type) | db.queued_tmdb_ids(media_type)


def _apply_queue_flags(db: Database, card: TitleCard) -> TitleCard:
    if card.media_type == "movie" and card.tmdb_id:
        if db.is_arr_queued(media_type="movie", tmdb_id=card.tmdb_id):
            card.in_radarr = True
    if card.media_type == "show":
        if card.tvdb_id and db.is_arr_queued(media_type="show", tvdb_id=card.tvdb_id):
            card.in_sonarr = True
        elif card.tmdb_id and db.is_arr_queued(media_type="show", tmdb_id=card.tmdb_id):
            card.in_sonarr = True
    return card


class ToolRegistry:
    def __init__(
        self,
        db: Database,
        settings: Settings,
        lens_id: str,
        *,
        user_id: Optional[str] = None,
        seerr_user_id: Optional[int] = None,
        user_role: Optional[str] = None,
    ) -> None:
        self.db = db
        self.settings = settings
        self.lens_id = lens_id
        self.user_id = user_id
        self.seerr_user_id = seerr_user_id
        self.user_role = user_role
        self._cards: List[TitleCard] = []
        self._pending_token_entries: List[Dict[str, str]] = []
        self._recommendation_context = False
        self._review_conflicts: List[Dict[str, Any]] = []
        self._review_prompts: List[Dict[str, Any]] = []

    def _register_pending_token(self, token: str, action: str) -> None:
        self._pending_token_entries.append({"token": token, "action": action})

    @property
    def cards(self) -> List[TitleCard]:
        return list(self._cards)

    @property
    def recommendation_context(self) -> bool:
        return self._recommendation_context

    @property
    def pending_tokens(self) -> List[Dict[str, str]]:
        return list(self._pending_token_entries)

    @property
    def review_conflicts(self) -> List[Dict[str, Any]]:
        return list(self._review_conflicts)

    @property
    def review_prompts(self) -> List[Dict[str, Any]]:
        return list(self._review_prompts)

    async def execute(self, name: str, arguments: Mapping[str, Any]) -> str:
        guest_denied = {
            "add_to_radarr",
            "add_to_sonarr",
            "request_via_seerr",
            "approve_seerr_request",
            "remove_from_arr",
            "create_plex_collection",
            "add_to_plex_collection",
        }
        if self.user_role == "guest" and name in guest_denied:
            return json.dumps({"error": "Guests cannot request or modify media"})
        handler: Optional[Callable] = getattr(self, f"_tool_{name}", None)
        if handler is None:
            logger.warning("Unknown agent tool requested: %s", name)
            return json.dumps({"error": f"Unknown tool {name}"})
        logger.debug("Executing tool %s", name)
        try:
            return await handler(arguments)
        except Exception:
            logger.exception("Tool %s failed", name)
            raise

    async def _tool_search_library(self, args: Mapping[str, Any]) -> str:
        cards = await search_library(
            self.db,
            self.settings,
            str(args.get("query") or ""),
            media_type=args.get("media_type"),
        )
        self._cards.extend(cards)
        items = [_card_to_tool_item(c) for c in cards]
        return json.dumps(
            {
                "total_matched": len(cards),
                "returned": len(cards),
                "offset": 0,
                "has_more": False,
                "items": items,
            }
        )

    async def _tool_query_library(self, args: Mapping[str, Any]) -> str:
        filters = filters_from_mapping(args)
        if filters.semantic_query:
            result = await query_library_async(self.db, filters, self.settings)
        else:
            result = query_library(self.db, filters)
        _attach_query_cards(self, self.db, result["items"], filters)
        maybe_set_audit_context_label(self.db, filters)
        payload = {
            **result,
            "items": [_query_item_to_tool_item(item) for item in result["items"]],
        }
        if result.get("has_more"):
            payload["hint"] = "More titles match — increase offset or call summarize_library first."
        return json.dumps(payload)

    async def _tool_get_facet_catalog(self, args: Mapping[str, Any]) -> str:
        facet_type = str(args.get("facet_type") or "director")
        limit = int(args.get("limit") or 50)
        return json.dumps(library_facet_catalog(self.db, facet_type, limit=limit))

    async def _tool_query_tv_episodes(self, args: Mapping[str, Any]) -> str:
        result = query_episodes(
            self.db,
            show=args.get("show"),
            show_id=args.get("show_id"),
            season=args.get("season"),
            unwatched_only=bool(args.get("unwatched_only")),
            offset=int(args.get("offset") or 0),
            limit=int(args.get("limit") or 25),
        )
        return json.dumps(result)

    async def _tool_summarize_tv_progress(self, args: Mapping[str, Any]) -> str:
        result = summarize_tv_progress(
            self.db,
            group_by=str(args.get("group_by") or "show"),
            in_progress_only=bool(args.get("in_progress_only")),
            limit=int(args.get("limit") or 25),
        )
        return json.dumps(result)

    async def _tool_summarize_library(self, args: Mapping[str, Any]) -> str:
        group_by = str(args.get("group_by") or "decade")
        filters = filters_from_mapping(args)
        maybe_set_audit_context_label(self.db, filters)
        summary = aggregate_library(self.db, group_by, filters)  # type: ignore[arg-type]
        return json.dumps(summary)

    async def _tool_get_library_overview(self, args: Mapping[str, Any]) -> str:
        del args
        return json.dumps(library_overview(self.db))

    async def _tool_find_collection_gaps(self, args: Mapping[str, Any]) -> str:
        media_type = str(args.get("media_type") or "movie")
        if not self.settings.tmdb_api_key:
            return json.dumps({"error": "TMDB API key not configured"})
        tmdb = TMDBClient(self.settings.tmdb_api_key)
        owned = _excluded_add_tmdb_ids(self.db, media_type)
        genres = str(args.get("genres") or "")
        genre_ids = ""
        if genres:
            genre_list = tmdb.genre_list_movies() if media_type == "movie" else tmdb.genre_list_tv()
            wanted = {g.strip().lower() for g in genres.split(",") if g.strip()}
            matched = [str(g["id"]) for g in genre_list if g.get("name", "").lower() in wanted]
            genre_ids = ",".join(matched)

        if media_type == "movie":
            results = tmdb.discover_movies(
                year_from=args.get("year_from"),
                year_to=args.get("year_to"),
                with_genres=genre_ids or None,
                with_keywords=str(args.get("keywords") or "") or None,
            )
        else:
            results = tmdb.discover_tv(
                year_from=args.get("year_from"),
                year_to=args.get("year_to"),
                with_genres=genre_ids or None,
            )

        cards: List[TitleCard] = []
        for item in results:
            tmdb_id = int(item.get("id") or 0)
            if tmdb_id <= 0 or tmdb_id in owned:
                continue
            if media_type == "show":
                item = _enrich_show_external_ids(item, tmdb)
            card = _apply_queue_flags(self.db, _tmdb_card(item, media_type, tmdb, reason="Missing from your collection"))
            if card.in_radarr or card.in_sonarr:
                continue
            cards.append(card)
            if len(cards) >= 12:
                break
        _append_recommendation_cards(self, cards)
        return json.dumps(
            {
                "total_matched": len(cards),
                "returned": len(cards),
                "offset": 0,
                "has_more": False,
                "items": [_card_to_tool_item(c) for c in cards],
                "note": (
                    "TMDB titles missing from the library and not already queued in Radarr/Sonarr. "
                    "Do not re-propose already_queued / in_radarr / in_sonarr titles."
                ),
            }
        )

    async def _tool_recommend_hidden_gems(self, args: Mapping[str, Any]) -> str:
        media_type = str(args.get("media_type") or "movie")
        if not self.settings.tmdb_api_key:
            return json.dumps({"error": "TMDB API key not configured"})
        tmdb = TMDBClient(self.settings.tmdb_api_key)
        query = str(args.get("query") or "")
        if media_type == "movie":
            results = tmdb.discover_movies(sort_by="vote_average.desc", page=1)
            if query:
                results = tmdb.search_movie(query)
        else:
            results = tmdb.discover_tv(sort_by="vote_average.desc", page=1)
            if query:
                results = tmdb.search_tv(query)
        owned = _excluded_add_tmdb_ids(self.db, media_type)
        cards = []
        for item in results:
            tmdb_id = int(item.get("id") or 0)
            if tmdb_id <= 0 or tmdb_id in owned:
                continue
            rating = float(item.get("vote_average") or 0)
            if rating < 7.0:
                continue
            if media_type == "show":
                item = _enrich_show_external_ids(item, tmdb)
            card = _apply_queue_flags(
                self.db,
                _tmdb_card(item, media_type, tmdb, reason=f"Hidden gem ({rating:.1f}/10)"),
            )
            if card.in_radarr or card.in_sonarr:
                continue
            cards.append(card)
            if len(cards) >= 10:
                break
        _append_recommendation_cards(self, cards)
        return json.dumps(
            {
                "total_matched": len(cards),
                "returned": len(cards),
                "offset": 0,
                "has_more": False,
                "items": [_card_to_tool_item(c) for c in cards],
                "note": "Highly rated TMDB titles not in the library and not already queued.",
            }
        )

    async def _tool_suggest_purge_candidates(self, args: Mapping[str, Any]) -> str:
        cards = suggest_purge_candidates(self.db, self.settings, limit=int(args.get("limit") or 12))
        self._cards.extend(cards)
        return json.dumps(
            {
                "total_matched": len(cards),
                "returned": len(cards),
                "offset": 0,
                "has_more": False,
                "items": [_card_to_tool_item(c) for c in cards],
            }
        )

    async def _tool_remember_preference(self, args: Mapping[str, Any]) -> str:
        from curatorx.models.schemas import PreferenceSignal

        remember_preference(
            self.db,
            PreferenceSignal(
                signal_type="explicit",
                text=str(args.get("text") or ""),
                lens_id=self.lens_id,
            ),
            user_id=self.user_id,
        )
        return json.dumps({"saved": True})

    async def _tool_add_to_radarr(self, args: Mapping[str, Any]) -> str:
        config_error = radarr_add_configuration_error(self.settings)
        if config_error:
            return json.dumps({"error": config_error})
        client = RadarrClient(self.settings.radarr_url, self.settings.radarr_api_key)
        root_error = validate_arr_root_folder(
            "Radarr",
            resolve_radarr_root_folder(self.settings),
            client.root_folders(),
        )
        if root_error:
            return json.dumps({"error": root_error})
        tmdb_id = int(args["tmdb_id"])
        existing = check_radarr_already_exists(
            client,
            tmdb_id,
            title=str(args.get("title") or ""),
        )
        if existing:
            mark_in_radarr(self.db, tmdb_id, title=str(args.get("title") or ""))
            return json.dumps(existing)
        token = uuid.uuid4().hex
        payload = {
            "action": "add_radarr",
            "tmdb_id": tmdb_id,
            "title": str(args.get("title") or ""),
        }
        self.db.save_pending_action(token, "add_radarr", payload, user_id=self.user_id)
        self._register_pending_token(token, "add_radarr")
        return json.dumps({"confirmation_token": token, "message": "Awaiting user confirmation to add to Radarr"})

    async def _tool_add_to_sonarr(self, args: Mapping[str, Any]) -> str:
        config_error = sonarr_add_configuration_error(self.settings)
        if config_error:
            return json.dumps({"error": config_error})
        client = SonarrClient(self.settings.sonarr_url, self.settings.sonarr_api_key)
        root_error = validate_arr_root_folder(
            "Sonarr",
            resolve_sonarr_root_folder(self.settings),
            client.root_folders(),
        )
        if root_error:
            return json.dumps({"error": root_error})
        tvdb_id = int(args["tvdb_id"])
        existing = check_sonarr_already_exists(
            client,
            tvdb_id,
            title=str(args.get("title") or ""),
        )
        if existing:
            mark_in_sonarr(self.db, tvdb_id, title=str(args.get("title") or ""))
            return json.dumps(existing)
        token = uuid.uuid4().hex
        payload = {
            "action": "add_sonarr",
            "tvdb_id": tvdb_id,
            "title": str(args.get("title") or ""),
        }
        self.db.save_pending_action(token, "add_sonarr", payload, user_id=self.user_id)
        self._register_pending_token(token, "add_sonarr")
        return json.dumps({"confirmation_token": token, "message": "Awaiting user confirmation to add to Sonarr"})

    async def _tool_request_via_seerr(self, args: Mapping[str, Any]) -> str:
        config_error = seerr_configuration_error(self.settings)
        if config_error:
            return json.dumps({"error": config_error})
        media_type = str(args.get("media_type") or "movie")
        tmdb_id = int(args["tmdb_id"])
        tvdb_id = args.get("tvdb_id")
        title = str(args.get("title") or "")
        # Ignore require_confirmation=false — Seerr writes always need UI confirm (S10).
        if self.settings.seerr.require_linked_user_for_requests and not self.seerr_user_id:
            return json.dumps({"error": "Seerr account must be linked before requesting"})
        pending_payload: Dict[str, Any] = {
            "action": "request_seerr",
            "media_type": media_type,
            "tmdb_id": tmdb_id,
            "title": title,
        }
        if tvdb_id is not None:
            pending_payload["tvdb_id"] = int(tvdb_id)
        if self.seerr_user_id is not None:
            pending_payload["seerr_user_id"] = int(self.seerr_user_id)
        token = uuid.uuid4().hex
        self.db.save_pending_action(
            token, "request_seerr", pending_payload, user_id=self.user_id
        )
        self._register_pending_token(token, "request_seerr")
        return json.dumps(
            {
                "confirmation_token": token,
                "message": "Awaiting user confirmation to request in Seerr",
            }
        )

    async def _tool_approve_seerr_request(self, args: Mapping[str, Any]) -> str:
        config_error = seerr_configuration_error(self.settings)
        if config_error:
            return json.dumps({"error": config_error})
        request_id = int(args["request_id"])
        client = SeerrClient(self.settings.seerr.url, self.settings.seerr.api_key)
        result = client.approve_request(request_id)
        return json.dumps({"approved": True, "request_id": request_id, "status": result.get("status")})

    async def _tool_search_seerr_movie(self, args: Mapping[str, Any]) -> str:
        config_error = seerr_configuration_error(self.settings)
        if config_error:
            return json.dumps({"error": config_error})
        query = str(args.get("query") or "").strip()
        if not query:
            return json.dumps({"error": "query is required"})
        limit = min(int(args.get("limit") or 10), 20)
        client = SeerrClient(self.settings.seerr.url, self.settings.seerr.api_key)
        results = client.search_movie(query)
        owned = self.db.owned_tmdb_ids("movie")
        items: List[Dict[str, Any]] = []
        for item in results:
            if not isinstance(item, Mapping):
                continue
            tool_item = _seerr_search_item_to_tool_item(item, "movie")
            tmdb_id = tool_item.get("tmdb_id")
            tool_item["in_library"] = bool(tmdb_id and int(tmdb_id) in owned)
            items.append(tool_item)
            if len(items) >= limit:
                break
        return json.dumps({"total_matched": len(results), "returned": len(items), "items": items})

    async def _tool_search_seerr_tv(self, args: Mapping[str, Any]) -> str:
        config_error = seerr_configuration_error(self.settings)
        if config_error:
            return json.dumps({"error": config_error})
        query = str(args.get("query") or "").strip()
        if not query:
            return json.dumps({"error": "query is required"})
        limit = min(int(args.get("limit") or 10), 20)
        client = SeerrClient(self.settings.seerr.url, self.settings.seerr.api_key)
        results = client.search_tv(query)
        owned = self.db.owned_tvdb_ids()
        items: List[Dict[str, Any]] = []
        for item in results:
            if not isinstance(item, Mapping):
                continue
            tool_item = _seerr_search_item_to_tool_item(item, "show")
            tvdb_id = tool_item.get("tvdb_id")
            tool_item["in_library"] = bool(tvdb_id and int(tvdb_id) in owned)
            items.append(tool_item)
            if len(items) >= limit:
                break
        return json.dumps({"total_matched": len(results), "returned": len(items), "items": items})

    async def _tool_remove_from_arr(self, args: Mapping[str, Any]) -> str:
        media_type = str(args.get("media_type") or "movie")
        title = str(args.get("title") or "")
        delete_files = bool(args.get("delete_files"))
        tmdb_id = args.get("tmdb_id")
        tvdb_id = args.get("tvdb_id")
        arr_id = args.get("arr_id")
        try:
            resolved = resolve_arr_removal_target(
                self.settings,
                media_type=media_type,
                arr_id=int(arr_id) if arr_id is not None else None,
                tmdb_id=int(tmdb_id) if tmdb_id is not None else None,
                tvdb_id=int(tvdb_id) if tvdb_id is not None else None,
                title=title,
            )
        except ArrTitleNotFoundError as error:
            return json.dumps({"error": str(error)})
        token = uuid.uuid4().hex
        payload = {
            "action": "remove_arr",
            "media_type": media_type,
            "arr_id": resolved["arr_id"],
            "title": resolved.get("title") or title,
            "delete_files": delete_files,
        }
        if resolved.get("tmdb_id") is not None:
            payload["tmdb_id"] = resolved["tmdb_id"]
        if resolved.get("tvdb_id") is not None:
            payload["tvdb_id"] = resolved["tvdb_id"]
        self.db.save_pending_action(token, "remove_arr", payload, user_id=self.user_id)
        self._register_pending_token(token, "remove_arr")
        return json.dumps(
            {
                "confirmation_token": token,
                "message": "Awaiting user confirmation to remove",
                "arr_id": resolved["arr_id"],
            }
        )

    async def _tool_search_tmdb(self, args: Mapping[str, Any]) -> str:
        if not self.settings.tmdb_api_key:
            return json.dumps({"error": "TMDB API key not configured"})
        media_type = str(args.get("media_type") or "movie")
        title = str(args.get("title") or "").strip()
        raw_tmdb_id = args.get("tmdb_id")
        pinned_tmdb_id = int(raw_tmdb_id) if raw_tmdb_id is not None else None
        if pinned_tmdb_id is not None and pinned_tmdb_id <= 0:
            return json.dumps({"error": "tmdb_id must be a positive integer"})
        if not title and pinned_tmdb_id is None:
            return json.dumps({"error": "title or tmdb_id is required"})
        year = args.get("year")
        year_int = int(year) if year is not None else None
        limit = min(int(args.get("limit") or 10), 20)
        reason = sanitize_recommendation_reason(
            str(args.get("reason") or args.get("recommendation_reason") or "")
        )

        tmdb = TMDBClient(self.settings.tmdb_api_key)
        results: List[Mapping[str, Any]] = []
        total_matched = 0
        if pinned_tmdb_id is not None:
            try:
                details = (
                    tmdb.movie_details(pinned_tmdb_id)
                    if media_type == "movie"
                    else tmdb.tv_details(pinned_tmdb_id)
                )
            except RuntimeError as error:
                return json.dumps({"error": str(error)})
            if not isinstance(details, Mapping) or not int(details.get("id") or 0):
                return json.dumps({"error": f"TMDB {media_type} {pinned_tmdb_id} not found"})
            results = [details]
            total_matched = 1
        else:
            if media_type == "movie":
                page = tmdb.search_movie_page(title, year=year_int)
            else:
                page = tmdb.search_tv_page(title)
            raw_results = page.get("results", [])
            if not isinstance(raw_results, list):
                raw_results = []
            total_matched = int(page.get("total_results") or len(raw_results))
            results = _rank_tmdb_search_results(raw_results, year=year_int)
            if year_int is not None:
                # Year pin: honest count is filtered matches, not unscoped TMDB total.
                total_matched = len(results)

        owned = self.db.owned_tmdb_ids(media_type)
        queued = self.db.queued_tmdb_ids(media_type)
        cards: List[TitleCard] = []
        items: List[Dict[str, Any]] = []
        for item in results:
            if not isinstance(item, Mapping):
                continue
            tmdb_id = int(item.get("id") or 0)
            if tmdb_id <= 0:
                continue
            if media_type == "show":
                item = _enrich_show_external_ids(item, tmdb)
            card = _apply_queue_flags(self.db, _tmdb_card(item, media_type, tmdb, reason=reason))
            card.in_library = tmdb_id in owned
            if tmdb_id in queued and media_type == "movie":
                card.in_radarr = True
            cards.append(card)
            tool_item = _tmdb_search_item_to_tool_item(item, media_type)
            tool_item["in_library"] = card.in_library
            tool_item["in_radarr"] = bool(card.in_radarr)
            tool_item["in_sonarr"] = bool(card.in_sonarr)
            tool_item["already_queued"] = bool(card.in_radarr or card.in_sonarr or tmdb_id in queued)
            if reason:
                tool_item["recommendation_reason"] = reason
            items.append(tool_item)
            if len(items) >= limit:
                break

        _append_recommendation_cards(self, cards)
        return json.dumps(
            {
                "total_matched": total_matched,
                "returned": len(items),
                "offset": 0,
                "has_more": total_matched > len(items),
                "items": items,
                "note": (
                    "Prefer tmdb_id (exact) or title+year so turnstyle cards pin one work. "
                    "Only propose adds for in_library=false AND already_queued=false "
                    "(also respect in_radarr/in_sonarr). Use tmdb_id for add_to_radarr; tvdb_id for add_to_sonarr. "
                    "Pass reason on search_tmdb or call set_recommendation_reasons so Why this? "
                    "shows curator rationale (never pipeline labels)."
                ),
            }
        )

    async def _tool_set_recommendation_reasons(self, args: Mapping[str, Any]) -> str:
        raw_reasons = args.get("reasons") or []
        if not isinstance(raw_reasons, list):
            return json.dumps({"error": "reasons must be a list"})
        updated = 0
        by_tmdb: Dict[int, str] = {}
        for entry in raw_reasons:
            if not isinstance(entry, Mapping):
                continue
            tmdb_id = int(entry.get("tmdb_id") or 0)
            reason = sanitize_recommendation_reason(str(entry.get("reason") or ""))
            if tmdb_id <= 0 or not reason:
                continue
            by_tmdb[tmdb_id] = reason
        if not by_tmdb:
            return json.dumps({"updated": 0, "note": "No usable reasons provided."})
        for card in self._cards:
            if card.tmdb_id and int(card.tmdb_id) in by_tmdb:
                card.recommendation_reason = by_tmdb[int(card.tmdb_id)]
                updated += 1
        return json.dumps({"updated": updated, "requested": len(by_tmdb)})

    async def _tool_get_title_detail(self, args: Mapping[str, Any]) -> str:
        media_type = str(args.get("media_type") or "movie")
        kwargs: Dict[str, Any] = {"media_type": media_type}
        if args.get("rating_key"):
            kwargs["rating_key"] = str(args["rating_key"])
        elif args.get("tvdb_id"):
            kwargs["tvdb_id"] = int(args["tvdb_id"])
        elif args.get("tmdb_id"):
            kwargs["tmdb_id"] = int(args["tmdb_id"])
        else:
            return json.dumps({"error": "Provide tmdb_id, tvdb_id, or rating_key"})
        detail = get_title_detail(self.db, self.settings, **kwargs)
        card = TitleCard.model_validate(detail.model_dump())
        self._cards.append(card)
        return json.dumps(_detail_to_tool_payload(detail, self.settings))

    async def _tool_explore_genre(self, args: Mapping[str, Any]) -> str:
        genre = str(args.get("genre") or "").strip()
        media_type = str(args.get("media_type") or "movie")
        include_missing = bool(args.get("include_missing", True))
        offset = int(args.get("offset") or 0)
        page_limit = int(args.get("limit") or 16)

        filters = LibraryFilters(
            media_type=media_type,
            genres=[genre] if genre else [],
            offset=offset,
            limit=page_limit,
        )
        owned_result = query_library(self.db, filters)
        owned_cards: List[TitleCard] = []
        for item in owned_result["items"]:
            row = self.db.library_item_by_id(int(item["id"]))
            if row is not None:
                owned_cards.append(row_to_title_card(row, reason=f"In library · {genre.title()}"))
        missing_cards: List[TitleCard] = []

        if include_missing and self.settings.tmdb_api_key:
            tmdb = TMDBClient(self.settings.tmdb_api_key)
            owned = _excluded_add_tmdb_ids(self.db, media_type)
            genre_list = tmdb.genre_list_movies() if media_type == "movie" else tmdb.genre_list_tv()
            genre_ids = [str(g["id"]) for g in genre_list if genre.lower() in str(g.get("name", "")).lower()]
            if genre_ids:
                if media_type == "movie":
                    results = tmdb.discover_movies(with_genres=",".join(genre_ids))
                else:
                    results = tmdb.discover_tv(with_genres=",".join(genre_ids))
                for item in results:
                    tmdb_id = int(item.get("id") or 0)
                    if tmdb_id <= 0 or tmdb_id in owned:
                        continue
                    if media_type == "show":
                        item = _enrich_show_external_ids(item, tmdb)
                    card = _apply_queue_flags(
                        self.db,
                        _tmdb_card(item, media_type, tmdb, reason=f"Not in library · {genre.title()}"),
                    )
                    if card.in_radarr or card.in_sonarr:
                        continue
                    missing_cards.append(card)
                    if len(missing_cards) >= page_limit:
                        break

        if include_missing:
            _append_recommendation_cards(self, missing_cards)
        else:
            self._cards.extend(owned_cards)

        response_items = [_card_to_tool_item(c) for c in owned_cards + missing_cards]
        return json.dumps(
            {
                "genre": genre,
                "total_in_library": owned_result["total_matched"],
                "returned_in_library": owned_result["returned"],
                "library_has_more": owned_result["has_more"],
                "returned_missing": len(missing_cards),
                "total_returned": len(response_items),
                "items": response_items,
                "note": (
                    "items mix owned (in_library=true) and TMDB gaps (in_library=false). "
                    "Only propose adds for in_library=false and already_queued/in_radarr/in_sonarr=false."
                    if include_missing
                    else "Owned library titles only."
                ),
            }
        )

    async def _tool_what_to_watch_tonight(self, args: Mapping[str, Any]) -> str:
        media_type = args.get("media_type")
        mood = str(args.get("mood") or "").lower()
        limit = int(args.get("limit") or 8)
        if mood:
            cards = await search_library(self.db, self.settings, mood, media_type=media_type, limit=limit * 2)
        else:
            candidates: List[tuple[int, TitleCard]] = []
            for row in self.db.all_library_items():
                if media_type and row["media_type"] != media_type:
                    continue
                view_count = int(row["view_count"] or 0)
                if view_count > 2:
                    continue
                score = (3 - view_count) * 10
                if row["last_viewed_at"]:
                    score -= 2
                candidates.append((score, row_to_title_card(row, reason="Good pick for tonight")))
            candidates.sort(key=lambda item: item[0], reverse=True)
            cards = [card for _, card in candidates[:limit]]
        self._cards.extend(cards[:limit])
        return json.dumps(
            {
                "total_matched": len(cards[:limit]),
                "returned": len(cards[:limit]),
                "offset": 0,
                "has_more": False,
                "items": [_card_to_tool_item(c) for c in cards[:limit]],
            }
        )

    async def _tool_analyze_watch_patterns(self, args: Mapping[str, Any]) -> str:
        filters = filters_from_mapping(args)
        where_sql, params = _build_where_for_patterns(filters)
        genre_counts: Dict[str, int] = {}
        total_views = 0
        unwatched = 0
        stale = 0
        decade_counts: Dict[int, int] = {}
        now = time.time()
        total_items = 0
        with self.db.connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM library_items WHERE {where_sql}",
                params,
            ).fetchall()
        for row in rows:
            total_items += 1
            views = int(row["view_count"] or 0)
            total_views += views
            if views == 0:
                unwatched += 1
            last = row["last_viewed_at"]
            if last and (now - int(last)) > 365 * 24 * 3600:
                stale += 1
            if row["year"] is not None:
                decade = (int(row["year"]) // 10) * 10
                decade_counts[decade] = decade_counts.get(decade, 0) + 1
            for genre in json.loads(row["genres"]) if row["genres"] else []:
                genre_counts[genre] = genre_counts.get(genre, 0) + max(views, 1)
        top_genres = sorted(genre_counts.items(), key=lambda item: item[1], reverse=True)[:8]
        decades = [
            {"decade": f"{decade}s", "count": count}
            for decade, count in sorted(decade_counts.items())
        ]
        summary = {
            "total_items": total_items,
            "total_plays": total_views,
            "unwatched_count": unwatched,
            "stale_count": stale,
            "top_genres": [{"genre": g, "weight": c} for g, c in top_genres],
            "decades": decades,
        }
        return json.dumps(summary)

    async def _tool_get_user_reviews(self, args: Mapping[str, Any]) -> str:
        items = get_reviews(
            self.db,
            rating_key=str(args["rating_key"]) if args.get("rating_key") else None,
            tmdb_id=int(args["tmdb_id"]) if args.get("tmdb_id") is not None else None,
            media_type=str(args["media_type"]) if args.get("media_type") else None,
            title=str(args["title"]) if args.get("title") else None,
            min_stars=int(args["min_stars"]) if args.get("min_stars") is not None else None,
            limit=int(args.get("limit") or 25),
        )
        return json.dumps({"items": items, "count": len(items)})

    async def _tool_save_user_review(self, args: Mapping[str, Any]) -> str:
        stars = float(args["stars"])
        review = save_review(
            self.db,
            stars=stars,
            title=str(args.get("title") or ""),
            media_type=str(args.get("media_type") or "movie"),
            rating_key=str(args["rating_key"]) if args.get("rating_key") else None,
            tmdb_id=int(args["tmdb_id"]) if args.get("tmdb_id") is not None else None,
            tvdb_id=int(args["tvdb_id"]) if args.get("tvdb_id") is not None else None,
            review_text=str(args.get("review_text") or ""),
            review_tags=list(args.get("review_tags") or []),
            prompted_by="curator_suggestion",
            lens_id=self.lens_id,
            user_id=self.user_id,
        )
        review = sync_review_rating_to_plex(
            self.db,
            self.settings,
            review,
            replace_plex_rating=bool(
                args.get("replace_plex_rating") or args.get("force_replace")
            ),
        )
        payload: Dict[str, Any] = {"saved": True, "review": review}
        if review.get("reason") == "plex_rating_conflict":
            plex_stars = float(review.get("plex_stars") or 0)
            submitted_stars = float(review.get("submitted_stars") or stars)
            payload["plex_rating_conflict"] = True
            payload["code"] = "plex_rating_conflict"
            payload["plex_stars"] = plex_stars
            payload["submitted_stars"] = submitted_stars
            payload["message"] = (
                f"Plex has {plex_stars}★ but you submitted {submitted_stars}★. "
                "Resubmit with replace_plex_rating=true or force_replace=true to overwrite Plex."
            )
            self._review_conflicts.append(
                {
                    "review": review,
                    "plex_stars": plex_stars,
                    "submitted_stars": submitted_stars,
                }
            )
        return json.dumps(payload)

    def _plex_section_for_media_type(self, media_type: str) -> Optional[str]:
        normalized = str(media_type or "").strip().lower()
        if normalized == "movie":
            section = str(self.settings.plex_movie_section or "").strip()
        elif normalized == "show":
            section = str(self.settings.plex_tv_section or "").strip()
        else:
            return None
        return section or None

    def _plex_configuration_error(self) -> Optional[str]:
        if not self.settings.plex_url or not self.settings.plex_token:
            return "Plex is not configured. Add Plex URL and token in Configuration."
        return None

    async def _tool_list_plex_collections(self, args: Mapping[str, Any]) -> str:
        from curatorx.connectors.plex import PlexClient
        from curatorx.connectors.plex_collections import list_collections

        config_error = plex_collections_configuration_error(self.settings)
        if config_error:
            return json.dumps({"error": config_error})
        media_type = str(args.get("media_type") or "movie")
        section_id = self._plex_section_for_media_type(media_type)
        if not section_id:
            return json.dumps(
                {
                    "error": (
                        f"Plex {media_type} library section is not configured. "
                        "Open Configuration → Plex library mapping."
                    )
                }
            )
        client = PlexClient(self.settings.plex_url, self.settings.plex_token)
        items = list_collections(client, section_id)
        return json.dumps(
            {
                "items": [
                    {
                        "rating_key": item.rating_key,
                        "title": item.title,
                        "section_id": item.section_id,
                        "media_type": item.media_type,
                    }
                    for item in items
                ],
                "count": len(items),
            }
        )

    async def _tool_create_plex_collection(self, args: Mapping[str, Any]) -> str:
        config_error = plex_collections_configuration_error(self.settings)
        if config_error:
            return json.dumps({"error": config_error})
        media_type = str(args.get("media_type") or "movie")
        section_id = self._plex_section_for_media_type(media_type)
        if not section_id:
            return json.dumps(
                {
                    "error": (
                        f"Plex {media_type} library section is not configured. "
                        "Open Configuration → Plex library mapping."
                    )
                }
            )
        title = str(args.get("title") or "").strip()
        if not title:
            return json.dumps({"error": "title is required"})
        rating_keys = [str(key).strip() for key in (args.get("rating_keys") or []) if str(key).strip()]
        token = uuid.uuid4().hex
        payload = {
            "action": "create_plex_collection",
            "title": title,
            "media_type": media_type,
            "section_id": section_id,
            "rating_keys": rating_keys,
        }
        self.db.save_pending_action(token, "create_plex_collection", payload, user_id=self.user_id)
        self._register_pending_token(token, "create_plex_collection")
        return json.dumps(
            {
                "confirmation_token": token,
                "message": f"Awaiting user confirmation to create Plex collection '{title}'",
            }
        )

    async def _tool_add_to_plex_collection(self, args: Mapping[str, Any]) -> str:
        config_error = plex_collections_configuration_error(self.settings)
        if config_error:
            return json.dumps({"error": config_error})
        media_type = str(args.get("media_type") or "movie")
        section_id = self._plex_section_for_media_type(media_type)
        if not section_id:
            return json.dumps(
                {
                    "error": (
                        f"Plex {media_type} library section is not configured. "
                        "Open Configuration → Plex library mapping."
                    )
                }
            )
        rating_keys = [str(key).strip() for key in (args.get("rating_keys") or []) if str(key).strip()]
        if not rating_keys:
            return json.dumps({"error": "rating_keys is required"})
        collection_rating_key = str(args.get("collection_rating_key") or "").strip()
        collection_title = str(args.get("collection_title") or "").strip()
        if not collection_rating_key and not collection_title:
            return json.dumps({"error": "collection_rating_key or collection_title is required"})
        token = uuid.uuid4().hex
        payload = {
            "action": "add_to_plex_collection",
            "media_type": media_type,
            "section_id": section_id,
            "rating_keys": rating_keys,
            "collection_rating_key": collection_rating_key,
            "collection_title": collection_title,
        }
        self.db.save_pending_action(token, "add_to_plex_collection", payload, user_id=self.user_id)
        self._register_pending_token(token, "add_to_plex_collection")
        label = collection_title or collection_rating_key
        return json.dumps(
            {
                "confirmation_token": token,
                "message": f"Awaiting user confirmation to add items to Plex collection '{label}'",
            }
        )

    async def _tool_suggest_titles_to_rate(self, args: Mapping[str, Any]) -> str:
        limit = int(args.get("limit") or 10)
        suggestions = list_titles_to_rate(self.db, limit=limit)
        prompts: List[Dict[str, Any]] = []
        for item in suggestions:
            prompt = {
                "id": str(item.get("id") or f"rate-{item.get('rating_key')}"),
                "rating_key": str(item["rating_key"]),
                "media_type": str(item["media_type"]),
                "title": str(item["title"]),
                "completion_pct": float(item.get("completion_pct") or 100),
                "poster_url": item.get("poster_url") or "",
            }
            prompts.append(prompt)
            if str(item.get("reason")) == "near_complete" and not str(prompt["id"]).startswith("viewed-"):
                mark_prompts_surfaced(self.db, [prompt["id"]])
        self._review_prompts.extend(prompts)
        return json.dumps(
            {
                "items": suggestions[:limit],
                "count": len(suggestions[:limit]),
                "note": (
                    "Rateable cards are shown in the UI. Summarize briefly; do not grill one-by-one in chat "
                    "unless the user asks for discussion. Half-stars (e.g. 4.5) are valid."
                ),
            }
        )

    async def _tool_query_watchlist(self, args: Mapping[str, Any]) -> str:
        from curatorx.watchlist.curate import enrich_watchlist_pins

        limit = int(args.get("limit") or 50)
        user_id = self.user_id if self.settings.features.multi_user_enabled else None
        pins = self.db.list_watchlist_pins(user_id=user_id)[:limit]
        items = enrich_watchlist_pins(self.db, pins)
        return json.dumps({"items": items, "count": len(items)})

    async def _tool_add_to_watchlist(self, args: Mapping[str, Any]) -> str:
        from curatorx.watchlist.plex_sync import push_pin_to_plex

        title = str(args.get("title") or "").strip()
        media_type = str(args.get("media_type") or "movie")
        tmdb_id = args.get("tmdb_id")
        tvdb_id = args.get("tvdb_id")
        if not title:
            return json.dumps({"error": "title is required"})
        if tmdb_id is None and tvdb_id is None:
            return json.dumps({"error": "tmdb_id or tvdb_id is required"})
        user_id = self.user_id if self.settings.features.multi_user_enabled else None
        try:
            pin = self.db.add_watchlist_pin(
                pin_id=str(uuid.uuid4()),
                user_id=user_id,
                tmdb_id=int(tmdb_id) if tmdb_id is not None else None,
                tvdb_id=int(tvdb_id) if tvdb_id is not None else None,
                media_type=media_type,
                title=title,
            )
        except ValueError as error:
            return json.dumps({"error": str(error)})
        push = push_pin_to_plex(self.db, self.settings, pin, user_id=self.user_id)
        return json.dumps({"pin": pin, "plex_push": push})

    async def _tool_remove_from_watchlist(self, args: Mapping[str, Any]) -> str:
        from curatorx.watchlist.plex_sync import remove_pin_from_plex

        user_id = self.user_id if self.settings.features.multi_user_enabled else None
        pin_id = str(args.get("pin_id") or "").strip() or None
        pin = None
        if pin_id:
            pin = self.db.get_watchlist_pin(pin_id, user_id=user_id)
        else:
            tmdb_id = args.get("tmdb_id")
            tvdb_id = args.get("tvdb_id")
            media_type = str(args.get("media_type") or "").strip() or None
            for candidate in self.db.list_watchlist_pins(user_id=user_id):
                if media_type and candidate.get("media_type") != media_type:
                    continue
                if tmdb_id is not None and candidate.get("tmdb_id") == int(tmdb_id):
                    pin = candidate
                    break
                if tvdb_id is not None and candidate.get("tvdb_id") == int(tvdb_id):
                    pin = candidate
                    break
                title = str(args.get("title") or "").strip().lower()
                if title and str(candidate.get("title") or "").strip().lower() == title:
                    pin = candidate
                    break
        if pin is None:
            return json.dumps({"error": "Watchlist pin not found"})
        removed = self.db.delete_watchlist_pin(str(pin["id"]), user_id=user_id)
        plex = remove_pin_from_plex(self.db, self.settings, pin, user_id=self.user_id)
        return json.dumps({"removed": bool(removed), "plex_remove": plex, "pin": pin})

    async def _tool_curate_watchlist(self, args: Mapping[str, Any]) -> str:
        from curatorx.watchlist.curate import curate_watchlist

        user_id = self.user_id if self.settings.features.multi_user_enabled else None
        pins = self.db.list_watchlist_pins(user_id=user_id)
        return json.dumps(curate_watchlist(self.db, pins, limit=int(args.get("limit") or 12)))

    async def _tool_critique_watchlist(self, args: Mapping[str, Any]) -> str:
        from curatorx.watchlist.curate import critique_watchlist

        user_id = self.user_id if self.settings.features.multi_user_enabled else None
        limit = int(args.get("limit") or 50)
        pins = self.db.list_watchlist_pins(user_id=user_id)[:limit]
        persona_row = self.db.get_persona()
        persona = dict(persona_row) if persona_row is not None else None
        return json.dumps(
            critique_watchlist(
                pins,
                persona=persona,
                focus_title=str(args.get("focus_title") or "") or None,
            )
        )

    def _resolve_curated_list_id(self, args: Mapping[str, Any]) -> tuple[Optional[str], Optional[str]]:
        user_id = self.user_id if self.settings.features.multi_user_enabled else None
        list_id = str(args.get("list_id") or "").strip() or None
        list_name = str(args.get("list_name") or "").strip() or None
        if list_id:
            found = self.db.get_curated_list(list_id, user_id=user_id)
            if found is None:
                return None, "List not found"
            return str(found["id"]), None
        if list_name:
            for candidate in self.db.list_curated_lists(user_id=user_id):
                if str(candidate["name"]).strip().lower() == list_name.lower():
                    return str(candidate["id"]), None
            return None, "List not found"
        return None, "list_id or list_name is required"

    async def _tool_list_lists(self, args: Mapping[str, Any]) -> str:
        del args
        user_id = self.user_id if self.settings.features.multi_user_enabled else None
        items = self.db.list_curated_lists(user_id=user_id)
        return json.dumps({"items": items, "count": len(items)})

    async def _tool_create_list(self, args: Mapping[str, Any]) -> str:
        name = str(args.get("name") or "").strip()
        if not name:
            return json.dumps({"error": "name is required"})
        user_id = self.user_id if self.settings.features.multi_user_enabled else None
        try:
            created = self.db.create_curated_list(
                list_id=str(uuid.uuid4()),
                user_id=user_id,
                name=name,
                description=str(args.get("description") or ""),
            )
        except ValueError as error:
            return json.dumps({"error": str(error)})
        return json.dumps({"list": created})

    async def _tool_add_to_list(self, args: Mapping[str, Any]) -> str:
        list_id, error = self._resolve_curated_list_id(args)
        if error:
            return json.dumps({"error": error})
        title = str(args.get("title") or "").strip()
        media_type = str(args.get("media_type") or "movie")
        tmdb_id = args.get("tmdb_id")
        tvdb_id = args.get("tvdb_id")
        if not title:
            return json.dumps({"error": "title is required"})
        if tmdb_id is None and tvdb_id is None:
            return json.dumps({"error": "tmdb_id or tvdb_id is required"})
        user_id = self.user_id if self.settings.features.multi_user_enabled else None
        try:
            item = self.db.add_curated_list_item(
                item_id=str(uuid.uuid4()),
                list_id=str(list_id),
                user_id=user_id,
                tmdb_id=int(tmdb_id) if tmdb_id is not None else None,
                tvdb_id=int(tvdb_id) if tvdb_id is not None else None,
                media_type=media_type,
                title=title,
            )
        except ValueError as err:
            return json.dumps({"error": str(err)})
        return json.dumps({"item": item})

    async def _tool_remove_from_list(self, args: Mapping[str, Any]) -> str:
        list_id, error = self._resolve_curated_list_id(args)
        if error:
            return json.dumps({"error": error})
        user_id = self.user_id if self.settings.features.multi_user_enabled else None
        item_id = str(args.get("item_id") or "").strip() or None
        item = self.db.find_curated_list_item(
            str(list_id),
            user_id=user_id,
            item_id=item_id,
            tmdb_id=int(args["tmdb_id"]) if args.get("tmdb_id") is not None else None,
            tvdb_id=int(args["tvdb_id"]) if args.get("tvdb_id") is not None else None,
            media_type=str(args.get("media_type") or "") or None,
            title=str(args.get("title") or "").strip() or None,
        )
        if item is None:
            return json.dumps({"error": "List item not found"})
        removed = self.db.delete_curated_list_item(str(list_id), str(item["id"]), user_id=user_id)
        return json.dumps({"removed": removed, "item": item})

    async def _tool_upcoming_premieres(self, args: Mapping[str, Any]) -> str:
        if not self.settings.tmdb_api_key:
            return json.dumps({"error": "TMDB API key not configured"})
        from datetime import datetime, timedelta, timezone

        limit = int(args.get("limit") or 15)
        days_ahead = int(args.get("days_ahead") or 14)
        today = datetime.now(timezone.utc).date()
        cutoff = today + timedelta(days=days_ahead)
        tmdb = TMDBClient(self.settings.tmdb_api_key)
        premieres: List[Dict[str, Any]] = []

        for row in self.db.all_library_items():
            if row["media_type"] != "show":
                continue
            tmdb_id = row["tmdb_id"]
            if not tmdb_id:
                continue
            try:
                details = tmdb.tv_details(int(tmdb_id))
            except RuntimeError:
                continue
            next_ep = details.get("next_episode_to_air")
            if not isinstance(next_ep, dict):
                continue
            air_date_raw = str(next_ep.get("air_date") or "")
            if not air_date_raw:
                continue
            try:
                air_date = datetime.strptime(air_date_raw, "%Y-%m-%d").date()
            except ValueError:
                continue
            if air_date < today or air_date > cutoff:
                continue
            premieres.append(
                {
                    "title": str(row["title"]),
                    "tmdb_id": int(tmdb_id),
                    "air_date": air_date_raw,
                    "episode_name": next_ep.get("name"),
                    "season_number": next_ep.get("season_number"),
                    "episode_number": next_ep.get("episode_number"),
                }
            )

        premieres.sort(key=lambda item: item["air_date"])
        trimmed = premieres[:limit]
        return json.dumps(
            {
                "items": trimmed,
                "count": len(trimmed),
                "days_ahead": days_ahead,
                "note": "Premieres from TMDB next_episode_to_air for shows in your library.",
            }
        )

    async def _tool_start_review_dialogue(self, args: Mapping[str, Any]) -> str:
        from curatorx.persona.presets import build_review_dialogue

        title = str(args.get("title") or "").strip()
        if not title:
            return json.dumps({"error": "title is required"})
        media_type = str(args.get("media_type") or "movie")
        rating_key = str(args["rating_key"]).strip() if args.get("rating_key") else None
        template_key = str(args.get("template_key") or "near_complete")
        completion_pct = float(args.get("completion_pct") or 0)

        persona = self.db.get_persona()
        preset_id = str(persona["preset_id"]) if persona and persona.get("preset_id") else None
        curator_name = str(persona["curator_name"]) if persona and persona.get("curator_name") else "Curator"

        if rating_key:
            prompts = list_pending_prompts(self.db, limit=50)
            matching = [prompt for prompt in prompts if prompt["rating_key"] == rating_key]
            if matching:
                completion_pct = float(matching[0].get("completion_pct") or completion_pct)
                mark_prompts_surfaced(self.db, [str(matching[0]["id"])])

        dialogue = build_review_dialogue(
            preset_id,
            template_key,
            curator_name=curator_name,
            title=title,
            media_type=media_type,
            rating_key=rating_key,
            completion_pct=completion_pct,
        )
        return json.dumps({"dialogue": dialogue})


def _build_where_for_patterns(filters: LibraryFilters) -> tuple[str, List[Any]]:
    return _build_where(filters)


def mark_in_radarr(db: Database, tmdb_id: int, *, title: str = "", session_id: Optional[str] = None) -> None:
    db.set_arr_presence(tmdb_id=tmdb_id, in_radarr=True)
    db.record_arr_queue(
        media_type="movie",
        source="radarr",
        tmdb_id=tmdb_id,
        title=title,
        session_id=session_id,
    )


def mark_in_sonarr(db: Database, tvdb_id: int, *, title: str = "", session_id: Optional[str] = None) -> None:
    db.set_arr_presence(tvdb_id=tvdb_id, in_sonarr=True)
    db.record_arr_queue(
        media_type="show",
        source="sonarr",
        tvdb_id=tvdb_id,
        title=title,
        session_id=session_id,
    )


def _already_exists_response(action: str, error: ArrTitleExistsError) -> dict:
    return {
        "action": action,
        "already_exists": True,
        "message": str(error),
        "result": {
            "id": error.arr_id,
            "title": error.title,
        },
    }


def check_radarr_already_exists(
    client: RadarrClient,
    tmdb_id: int,
    *,
    title: str = "",
) -> Optional[dict]:
    existing = client.movie_by_tmdb_id(tmdb_id)
    if not existing:
        return None
    label = existing.title or title or str(tmdb_id)
    return {
        "already_exists": True,
        "message": f'"{label}" is already in Radarr',
        "result": {"id": existing.id, "title": existing.title},
    }


def check_sonarr_already_exists(
    client: SonarrClient,
    tvdb_id: int,
    *,
    title: str = "",
) -> Optional[dict]:
    existing = client.series_by_tvdb_id(tvdb_id)
    if not existing:
        return None
    label = existing.title or title or str(tvdb_id)
    return {
        "already_exists": True,
        "message": f'"{label}" is already in Sonarr',
        "result": {"id": existing.id, "title": existing.title},
    }


def resolve_arr_removal_target(
    settings: Settings,
    *,
    media_type: str,
    arr_id: Optional[int] = None,
    tmdb_id: Optional[int] = None,
    tvdb_id: Optional[int] = None,
    title: str = "",
) -> Dict[str, Any]:
    if media_type == "movie":
        if not settings.radarr_url or not settings.radarr_api_key:
            raise RuntimeError("Radarr is not configured")
        client = RadarrClient(settings.radarr_url, settings.radarr_api_key)
        found = None
        if tmdb_id is not None:
            found = client.movie_by_tmdb_id(tmdb_id)
        elif arr_id is not None:
            movies = client.movies()
            found = next((movie for movie in movies if movie.id == arr_id), None)
        if found is None:
            raise ArrTitleNotFoundError(
                "Radarr",
                title=title,
                external_id=tmdb_id or 0,
                arr_id=arr_id,
            )
        return {
            "arr_id": found.id,
            "title": found.title or title,
            "tmdb_id": found.tmdb_id or tmdb_id,
        }

    if not settings.sonarr_url or not settings.sonarr_api_key:
        raise RuntimeError("Sonarr is not configured")
    client = SonarrClient(settings.sonarr_url, settings.sonarr_api_key)
    found = None
    if tvdb_id is not None:
        found = client.series_by_tvdb_id(tvdb_id)
    elif arr_id is not None:
        series_items = client.series_list()
        found = next((series for series in series_items if series.id == arr_id), None)
    if found is None:
        raise ArrTitleNotFoundError(
            "Sonarr",
            title=title,
            external_id=tvdb_id or 0,
            arr_id=arr_id,
        )
    return {
        "arr_id": found.id,
        "title": found.title or title,
        "tvdb_id": found.tvdb_id or tvdb_id,
    }


async def execute_confirmed_action(
    db: Database,
    settings: Settings,
    token: str,
    *,
    user_id: Optional[str] = None,
) -> dict:
    payload = db.pop_pending_action(token, user_id=user_id)
    if not payload:
        raise RuntimeError("Invalid or expired confirmation token")
    action = payload.get("action")
    logger.info("Executing confirmed action=%s", action)
    if action == "add_radarr":
        config_error = radarr_add_configuration_error(settings)
        if config_error:
            raise RuntimeError(config_error)
        client = RadarrClient(settings.radarr_url, settings.radarr_api_key)
        tmdb_id = int(payload["tmdb_id"])
        title = str(payload.get("title") or "")
        try:
            result = client.add_movie(
                tmdb_id,
                root_folder=resolve_radarr_root_folder(settings),
                quality_profile_id=settings.radarr_quality_profile_id,
            )
        except ArrTitleExistsError as error:
            mark_in_radarr(db, tmdb_id, title=title or error.title)
            return _already_exists_response(action, error)
        mark_in_radarr(db, tmdb_id, title=title)
        return {"action": action, "result": result}
    if action == "add_sonarr":
        config_error = sonarr_add_configuration_error(settings)
        if config_error:
            raise RuntimeError(config_error)
        client = SonarrClient(settings.sonarr_url, settings.sonarr_api_key)
        tvdb_id = int(payload["tvdb_id"])
        title = str(payload.get("title") or "")
        try:
            result = client.add_series(
                tvdb_id,
                root_folder=resolve_sonarr_root_folder(settings),
                quality_profile_id=settings.sonarr_quality_profile_id,
            )
        except ArrTitleExistsError as error:
            mark_in_sonarr(db, tvdb_id, title=title or error.title)
            return _already_exists_response(action, error)
        mark_in_sonarr(db, tvdb_id, title=title)
        return {"action": action, "result": result}
    if action == "request_seerr":
        config_error = seerr_configuration_error(settings)
        if config_error:
            raise RuntimeError(config_error)
        client = SeerrClient(settings.seerr.url, settings.seerr.api_key)
        media_type = str(payload.get("media_type") or "movie")
        tmdb_id = int(payload["tmdb_id"])
        tvdb_id = payload.get("tvdb_id")
        title = str(payload.get("title") or "")
        seerr_uid = payload.get("seerr_user_id")
        result = client.create_request(
            media_type,
            tmdb_id,
            tvdb_id=int(tvdb_id) if tvdb_id is not None else None,
            user_id=int(seerr_uid) if seerr_uid is not None else None,
        )
        db.record_arr_queue(
            media_type=media_type,
            source="seerr",
            tmdb_id=tmdb_id,
            tvdb_id=int(tvdb_id) if tvdb_id is not None else None,
            title=title,
        )
        return {
            "action": action,
            "result": {
                "id": result.get("id"),
                "status": result.get("status"),
                "title": title,
            },
        }
    if action == "remove_arr":
        delete_files = bool(payload.get("delete_files"))
        media_type = str(payload.get("media_type") or "movie")
        title = str(payload.get("title") or "")
        resolved = resolve_arr_removal_target(
            settings,
            media_type=media_type,
            arr_id=int(payload["arr_id"]) if payload.get("arr_id") is not None else None,
            tmdb_id=int(payload["tmdb_id"]) if payload.get("tmdb_id") is not None else None,
            tvdb_id=int(payload["tvdb_id"]) if payload.get("tvdb_id") is not None else None,
            title=title,
        )
        arr_id = int(resolved["arr_id"])
        removed_title = str(resolved.get("title") or title)
        try:
            if media_type == "movie":
                RadarrClient(settings.radarr_url, settings.radarr_api_key).delete_movie(
                    arr_id, delete_files=delete_files
                )
                if resolved.get("tmdb_id"):
                    db.set_arr_presence(tmdb_id=int(resolved["tmdb_id"]), in_radarr=False)
            else:
                SonarrClient(settings.sonarr_url, settings.sonarr_api_key).delete_series(
                    arr_id, delete_files=delete_files
                )
                if resolved.get("tvdb_id"):
                    db.set_arr_presence(tvdb_id=int(resolved["tvdb_id"]), in_sonarr=False)
        except RuntimeError as error:
            from curatorx.connectors.arr_errors import format_arr_http_error, is_arr_not_found_error

            if is_arr_not_found_error(error):
                raise ArrTitleNotFoundError(
                    "Radarr" if media_type == "movie" else "Sonarr",
                    title=removed_title,
                    arr_id=arr_id,
                ) from error
            raise RuntimeError(format_arr_http_error(error)) from error
        return {
            "action": action,
            "removed": True,
            "result": {"title": removed_title, "arr_id": arr_id},
        }
    if action == "create_plex_collection":
        from curatorx.connectors.plex import PlexClient
        from curatorx.connectors.plex_collections import create_collection

        config_error = plex_collections_configuration_error(settings)
        if config_error:
            raise RuntimeError(config_error)
        client = PlexClient(settings.plex_url, settings.plex_token)
        collection = create_collection(
            client,
            section_id=str(payload["section_id"]),
            title=str(payload["title"]),
            media_type=str(payload["media_type"]),
            rating_keys=list(payload.get("rating_keys") or []),
        )
        return {
            "action": action,
            "result": {
                "rating_key": collection.rating_key,
                "title": collection.title,
                "section_id": collection.section_id,
            },
        }
    if action == "add_to_plex_collection":
        from curatorx.connectors.plex import PlexClient
        from curatorx.connectors.plex_collections import add_items_to_collection, find_collection_by_title

        config_error = plex_collections_configuration_error(settings)
        if config_error:
            raise RuntimeError(config_error)
        client = PlexClient(settings.plex_url, settings.plex_token)
        collection_key = str(payload.get("collection_rating_key") or "").strip()
        if not collection_key:
            match = find_collection_by_title(
                client,
                str(payload["section_id"]),
                str(payload.get("collection_title") or ""),
            )
            if match is None:
                raise RuntimeError("Plex collection not found")
            collection_key = match.rating_key
        add_items_to_collection(client, collection_key, list(payload.get("rating_keys") or []))
        return {"action": action, "result": {"collection_rating_key": collection_key, "added": True}}
    raise RuntimeError(f"Unknown action {action}")


def _persona_prompt_block(db: Database, *, persona_id: Optional[str] = None) -> str:
    """Build the persona section of the system prompt.

    Resolution order for per-conversation persona:
    1. ``persona_id`` — the persona template attached to this conversation
    2. Global singleton in ``curator_persona_metrics`` (legacy fallback)

    When a persona_template is found, its 7 slider values are passed through
    the same prompt-assembly pipeline as the legacy 3-slider persona.
    """
    from curatorx.persona import build_persona_prompt, persona_row_to_dict

    if persona_id:
        template = db.get_persona_template(persona_id)
        if template:
            synth = {
                "curator_name": template.get("name", "Curator"),
                "persona_identity": "",
                "val_bro_prof": template["val_bro_prof"],
                "val_dipl_snark": template["val_dipl_snark"],
                "val_pass_auto": template["val_pass_auto"],
                "val_depth": template["val_depth"],
                "val_obscurity": template["val_obscurity"],
                "val_verbosity": template["val_verbosity"],
                "val_formality": template["val_formality"],
                "persona_prompt_override": template.get("system_prompt_override"),
                "persona_preset_id": template["id"] if template["visibility"] == "builtin" else None,
            }
            return build_persona_prompt(synth)

    persona = db.get_persona()
    if not persona:
        return ""
    return build_persona_prompt(persona_row_to_dict(persona))


def build_system_prompt(
    db: Database,
    lens_id: Optional[str] = None,
    *,
    persona_id: Optional[str] = None,
) -> str:
    """Assemble the full system prompt for the Curator agent.

    ``persona_id`` specifies the per-conversation persona template. When
    omitted, the global singleton persona is used (backward-compatible).
    """
    from curatorx.library.db import DEFAULT_LENS_ID

    resolved = lens_id or db.get_active_lens_id() or DEFAULT_LENS_ID
    lens = db.get_lens(resolved)
    lens_name = str(lens["lens_name"]) if lens else resolved
    lens_desc = str(lens["description"] or "").strip() if lens else ""
    lens_block = f"Active curation lens: {lens_name} ({resolved})."
    if lens_desc:
        lens_block += f" Focus: {lens_desc}"
    persona = db.get_persona()
    curator_name = str(persona["curator_name"]) if persona else "Curator"
    overview_block = format_overview_for_prompt(library_overview(db))
    queued = db.list_recent_arr_queue(limit=30)
    if queued:
        queued_bits = []
        for entry in queued:
            label = entry.get("title") or "Untitled"
            ids = []
            if entry.get("tmdb_id") is not None:
                ids.append(f"tmdb:{entry['tmdb_id']}")
            if entry.get("tvdb_id") is not None:
                ids.append(f"tvdb:{entry['tvdb_id']}")
            source = entry.get("source") or "arr"
            queued_bits.append(f"{label} ({source}{', ' + ', '.join(ids) if ids else ''})")
        queued_block = (
            "Already queued / confirmed adds — do NOT re-propose these for Radarr/Sonarr/Seerr: "
            + "; ".join(queued_bits)
            + ".\n"
        )
    else:
        queued_block = ""
    return (
        f"You are {curator_name}, an expert movie and TV collection curator for CuratorX. "
        "You know the user's Plex library and help them discover what to add, what to watch tonight, "
        "and what to purge to save drive space. Use tools to ground recommendations in their actual library. "
        "Never add or remove titles without confirmation tokens. "
        "Plex collection create/add actions also require confirmation tokens. "
        "When proposing adds, always use the exact tmdb_id or tvdb_id from tool item responses — never guess or invent external IDs. "
        "For titles to add, use find_collection_gaps, recommend_hidden_gems, search_tmdb, or explore_genre(include_missing=true) — "
        "never query_library or search_library (those only return owned titles). "
        "Never present in_library=true or already_queued/in_radarr/in_sonarr titles as recommendations to add; "
        "title cards for adds exclude owned and already-queued titles. "
        "For exact external title lookup before add_to_radarr or add_to_sonarr, use search_tmdb — not search_library. "
        "When you already know a specific work, call search_tmdb with tmdb_id (and media_type), or title+year — "
        "never title-only when recommending one film/show, or turnstyle cards may list every same-name TMDB hit. "
        "When recommending external titles, set a specific taste-based reason via search_tmdb(reason=…) "
        "or set_recommendation_reasons — never leave Why this? as a pipeline label. "
        "For movies use tmdb_id with add_to_radarr; for shows use tvdb_id with add_to_sonarr.\n"
        "When Seerr is enabled for household members, use request_via_seerr instead of add_to_radarr/add_to_sonarr.\n"
        "Star ratings accept half-stars (e.g. 4.5); never ask users to round fractional ratings.\n"
        f"{queued_block}"
        f"{overview_block}\n"
        f"{_persona_prompt_block(db, persona_id=persona_id)}"
        f"{lens_block}\n\n"
        + preference_context(db, lens_id=resolved)
    )
