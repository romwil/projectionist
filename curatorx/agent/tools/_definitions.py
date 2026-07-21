"""LLM tool schemas (``TOOL_DEFINITIONS``) and feature-gated selection.

Behavior-preserving extraction from the former single-file
``curatorx.agent.tools`` module. The schema list and its wording are verbatim
(M2's prompt-injection additions included); ``build_tool_definitions`` and the
tool-name sets are re-exported from the package so existing imports resolve.
"""

from __future__ import annotations

from typing import Any, List, Mapping

from curatorx.config_store import Settings


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
            "name": "research_title",
            "description": (
                "Research a specific movie or show using configured official media APIs: TMDB details "
                "(credits, keywords, images), Wikipedia, optional OMDb, and optional TVDB. Use this "
                "when a local record or search result has thin plot/credit data. Returns provenance and "
                "honest source gaps; it is not arbitrary web browsing."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "item_id": {"type": "integer", "description": "Optional local library item id"},
                    "title": {"type": "string"},
                    "year": {"type": "integer"},
                    "media_type": {"type": "string", "enum": ["movie", "show"]},
                    "tmdb_id": {"type": "integer"},
                    "tvdb_id": {"type": "integer"},
                    "imdb_id": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "research_person",
            "description": "Research a filmmaker or performer from TMDB and return public biography plus filmography with provenance.",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string"}, "tmdb_id": {"type": "integer"}},
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "research_company",
            "description": "Research a production company from TMDB. Requires its TMDB company id to avoid ambiguous name matching.",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string"}, "tmdb_id": {"type": "integer"}},
                "required": ["name", "tmdb_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compare_filmographies",
            "description": "Compare two people’s TMDB filmographies by counts and shared credits; do not infer subjective similarity.",
            "parameters": {
                "type": "object",
                "properties": {
                    "left_name": {"type": "string"},
                    "left_tmdb_id": {"type": "integer"},
                    "right_name": {"type": "string"},
                    "right_tmdb_id": {"type": "integer"},
                },
                "required": ["left_name", "right_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recall_repo_memory",
            "description": (
                "Recall what CuratorX already knows about a title, person, or company from its "
                "persistent, source-cited repository memory: the latest research snapshot, when it "
                "was first known and last refreshed, saved insights, and how often it has come up. "
                "Call this BEFORE declaring you have no information — the store may already hold a "
                "cited answer. Returns provenance for prose citations; never local file paths."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Entity name (title, person, or company)"},
                    "entity_type": {"type": "string", "enum": ["title", "person", "company", "location", "other"]},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_memory",
            "description": (
                "Fuzzy-search the persistent repository knowledge store — \"what do I already know "
                "about X\". Returns matching entities with type and freshness so you can then "
                "recall_repo_memory the best match. Use before research when the user references "
                "something you may have already looked up."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_repo_insight",
            "description": (
                "Persist a durable, source-cited insight about a known repository entity (a lasting "
                "fact or synthesis worth remembering across sessions — Scholar cited knowledge). "
                "Cite sources so the claim can be repeated with provenance. The entity must already "
                "exist in memory (research it first if needed). Use for shared/library knowledge — "
                "NOT for private user facts (use remember_about_user for those)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Entity name; resolved against known entities"},
                    "entity_id": {"type": "string", "description": "Exact entity id from recall_repo_memory/search_memory"},
                    "entity_type": {"type": "string", "enum": ["title", "person", "company", "location", "other"]},
                    "insight": {"type": "string"},
                    "citations": {
                        "type": "array",
                        "description": "Sources backing the insight",
                        "items": {
                            "type": "object",
                            "properties": {
                                "source": {"type": "string", "description": "e.g. TMDB, Wikipedia"},
                                "ref": {"type": "string", "description": "Optional reference/URL"},
                                "note": {"type": "string"},
                            },
                        },
                    },
                },
                "required": ["insight"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_similar_titles",
            "description": (
                "Find titles similar or surprisingly adjacent to a seed library title using "
                "cached plot-neighbor scores (embedding cosine + surprise). Prefer this over "
                "search_library when the user asks for 'more like X' or 'something similar but unexpected'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "item_id": {
                        "type": "integer",
                        "description": "Library item id of the seed title",
                    },
                    "title": {
                        "type": "string",
                        "description": "Seed title to look up when item_id is unknown",
                    },
                    "year": {
                        "type": "integer",
                        "description": "Release/air year to disambiguate same-name seed titles",
                    },
                    "media_type": {
                        "type": "string",
                        "enum": ["movie", "show"],
                        "description": "Optional media type to disambiguate same-name seed titles",
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["similar", "surprising"],
                        "description": "similar = high cosine; surprising = high cosine with low genre/keyword/credit overlap",
                    },
                    "limit": {"type": "integer"},
                },
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
            "name": "remember_about_user",
            "description": "Remember a user-provided private fact, goal, intention, or external watch for that same user only.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "kind": {"type": "string", "enum": ["self_disclosure", "learning_goal", "watch_intention", "watched_external", "follow_up", "preference"]},
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recall_user_memory",
            "description": "Recall only the current user's private memory. Never use it for another account.",
            "parameters": {"type": "object", "properties": {"limit": {"type": "integer"}}},
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
            "description": (
                "List top directors, actors, keywords, countries, languages, plot motifs, "
                "or themes in the owned library."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "facet_type": {
                        "type": "string",
                        "enum": [
                            "director",
                            "actor",
                            "keyword",
                            "country",
                            "language",
                            "motif",
                            "theme",
                        ],
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
            "name": "list_relations",
            "description": (
                "List title_relations edges from a seed library item (collection, neighbor, "
                "shared_crew, or llm_theme). Prefer walk_relations for a shallow multi-hop walk."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "item_id": {"type": "integer", "description": "Library item id"},
                    "title": {
                        "type": "string",
                        "description": "Seed title lookup when item_id is unknown",
                    },
                    "relation": {
                        "type": "string",
                        "enum": ["collection", "neighbor", "shared_crew", "llm_theme"],
                        "description": "Optional relation filter",
                    },
                    "limit": {"type": "integer"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "walk_relations",
            "description": (
                "Shallow BFS over title_relations from a seed (depth 1–2). Uses the idle "
                "title_relations_refresh cache — empty means the graph has not been built yet."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "item_id": {"type": "integer"},
                    "title": {"type": "string"},
                    "relation": {
                        "type": "string",
                        "enum": ["collection", "neighbor", "shared_crew", "llm_theme"],
                    },
                    "depth": {"type": "integer"},
                    "limit": {"type": "integer"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "titles_by_person",
            "description": (
                "List in-library titles linked to a person via structured credits "
                "(local person_id or TMDB person id)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "person_id": {
                        "type": "integer",
                        "description": "Local people.id",
                    },
                    "tmdb_person_id": {
                        "type": "integer",
                        "description": "TMDB person id",
                    },
                    "name": {
                        "type": "string",
                        "description": "Person name lookup when ids are unknown",
                    },
                    "limit": {"type": "integer"},
                },
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
    {
        "type": "function",
        "function": {
            "name": "get_todays_anniversaries",
            "description": (
                "Surface film/show anniversaries from the library — titles whose release date "
                "month+day matches today. Returns items with anniversary context."
            ),
            "parameters": {
                "type": "object",
                "properties": {"limit": {"type": "integer", "description": "Max results (default 5)"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_library_snapshot",
            "description": (
                "Return a high-level summary of the library: total titles, movies vs shows, "
                "top genres, decade range, and estimated hidden gems (high rating, 0 views)."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_tonight_picks",
            "description": (
                "Suggest unwatched titles for tonight, optionally filtered by max runtime. "
                "Prioritizes high taste-match titles under the runtime limit. "
                "Use when it's late and the user wants something short."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "max_runtime_minutes": {
                        "type": "integer",
                        "description": "Only return titles shorter than this runtime (minutes)",
                    },
                    "limit": {"type": "integer", "description": "Max results (default 5)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "suggest_double_feature",
            "description": (
                "Pick two complementary titles from the library for a double feature pairing. "
                "Returns a DoubleFeature structure with bridge text explaining the connection."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "theme": {
                        "type": "string",
                        "description": "Optional thematic hint for the pairing (e.g. 'noir', 'coming-of-age')",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "suggest_follow_ups",
            "description": (
                "Offer 2-4 concise, safe next user messages after a useful answer. "
                "Use after recommendation or gap results; this only renders reply chips and never performs an action."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "replies": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 2,
                        "maxItems": 4,
                    },
                },
                "required": ["replies"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "quick_pick_roulette",
            "description": (
                "Pick ONE random unwatched title matching taste profile. "
                "Optionally constrained by runtime and genre. Returns a single title with a 'Why this?' reason."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "max_runtime_minutes": {
                        "type": "integer",
                        "description": "Only pick titles shorter than this runtime",
                    },
                    "genres": {
                        "type": "string",
                        "description": "Comma-separated genre filter",
                    },
                },
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

