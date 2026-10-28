"""Library-domain agent tools (search, query, gaps, TMDB, snapshot)."""

from __future__ import annotations

from projectionist.agent.tools._helpers import *  # noqa: F401, F403

class LibraryToolsMixin:
    async def _tool_search_library(self, args: Mapping[str, Any]) -> str:
        query = str(args.get("query") or "")
        cards = self._allowed_cards(
            await search_library(
                self.db,
                self.settings,
                query,
                media_type=args.get("media_type"),
            )
        )
        cleaned = " ".join(query.split())
        exact = exact_title_cards(cards, cleaned) if cleaned else []
        words = cleaned.split()
        # Title-shaped queries (Title Case / year pin) vs lowercase mood browse.
        title_like = bool(cleaned) and (
            bool(re.search(r"\(\d{4}\)", cleaned))
            or (len(words) >= 2 and sum(1 for w in words if w[:1].isupper()) >= 2)
            or (len(words) == 1 and words[0][:1].isupper() and len(words[0]) > 3)
        )
        if exact:
            presence = "exact"
            # Exact hits only — never mix in fuzzy remainder for title checks.
            display_cards = exact
        elif not cards:
            presence = "none"
            display_cards = []
        elif title_like:
            # Title-shaped query with no exact hit (e.g. Buckaroo Banzai) — keep JSON
            # for the agent but do not fill the rail with Adventures of… noise.
            presence = "partial"
            display_cards = []
        else:
            # Theme / mood / keyword browse ("robots", "noir") — cards are the point.
            presence = "partial"
            display_cards = cards
        self._cards.extend(display_cards)
        items = [_card_to_tool_item(c) for c in (display_cards or cards[:8])]
        return json.dumps(
            {
                "total_matched": len(cards),
                "returned": len(items),
                "offset": 0,
                "has_more": False,
                "presence": presence,
                "exact_title_matches": [_card_to_tool_item(c) for c in exact],
                "items": items,
                "note": (
                    "presence=exact means owned. presence=partial for a title-like query is "
                    "uncertain — do not claim ownership or show those fuzzy hits as the rail. "
                    "presence=none means no library hit; use search_tmdb with title+year for gaps. "
                    "When naming a specific owned title in prose, link it for dig-in: "
                    "[Title](/title/movie/TMDB_ID) or [Title](/title/show/TMDB_ID); "
                    "rating_key-only → [Title](/title/movie/RATING_KEY?id_type=rating_key)."
                ),
            }
        )

    async def _tool_find_similar_titles(self, args: Mapping[str, Any]) -> str:
        """Read cached plot neighbors (similar or surprising) for a seed title."""
        from projectionist.notifications.recommendation_reasons import (
            watched_bridge,
            watched_library_rows,
        )

        limit = min(max(1, int(args.get("limit") or 10)), 25)
        mode = str(args.get("mode") or "similar").strip().lower()
        if mode not in {"similar", "surprising"}:
            mode = "similar"

        seed_row = self._resolve_seed_library_row(args)
        if seed_row is None:
            return json.dumps({"error": "Seed title not found in library", "items": []})

        seed_id = int(seed_row["id"])
        watched_seed = next(
            (
                row
                for row in watched_library_rows(
                    self.db,
                    user_id=self.user_id,
                    multi_user_enabled=bool(self.user_id),
                )
                if int(row.get("id") or 0) == seed_id
            ),
            None,
        )
        neighbors = self.db.get_neighbors(
            seed_id, mode=mode, limit=limit, explainable_only=True
        )
        cards = []
        items = []
        for row in neighbors:
            peer_map = _row_mapping(row)
            explanation = None
            if watched_seed is not None:
                explanation = watched_bridge(self.db, peer_map, watched_seed)
            if not explanation or not str(explanation.get("sentence") or "").strip():
                link = honest_plot_link(parse_plot_link_json(peer_map.get("plot_link_json")))
                if link:
                    explanation = explanation_from_plot_link(
                        link,
                        seed_ids=[seed_id],
                        peer_id=int(peer_map.get("id") or 0) or None,
                    )
            sentence = str((explanation or {}).get("sentence") or "").strip()
            if not sentence:
                continue
            card = row_to_title_card(row, reason=sanitize_recommendation_reason(sentence))
            if not self._card_allowed(card):
                continue
            cards.append(card)
            payload = _card_to_tool_item(card)
            payload["score"] = float(row["score"] or 0)
            payload["surprise_score"] = float(row["surprise_score"] or 0)
            payload["explanation"] = explanation
            items.append(payload)
        self._cards.extend(cards)
        payload = kinship_empty_payload(
            {
                "seed": {
                    "id": int(seed_row["id"]),
                    "title": str(seed_row["title"]),
                    "year": seed_row["year"],
                    "media_type": str(seed_row["media_type"]),
                },
                "mode": mode,
                "items": items,
                "cache_status": "ready" if items else "seed_pending",
                "note": (
                    KINSHIP_CACHE_NOT_READY_NOTE
                    if not items
                    else "Neighbors come from the plot_neighbors idle cache."
                ),
            }
        )
        return json.dumps(payload)

    async def _tool_get_for_you(self, args: Mapping[str, Any]) -> str:
        """Return Explore For you (watched_bridge) including the honest empty note."""
        from projectionist.library.feeds import feed_for_you
        from projectionist.youth.rating_gate import resolve_youth_max_rating

        limit = min(max(1, int(args.get("limit") or 8)), 12)
        youth_max = resolve_youth_max_rating(self.settings) if self.is_youth else None
        payload = feed_for_you(
            self.db,
            limit=limit,
            user_id=self.user_id,
            multi_user_enabled=bool(self.user_id),
            youth_max_rating=youth_max,
        )
        for item in payload.get("items") or []:
            if not isinstance(item, Mapping):
                continue
            self._offer_card(_feed_item_to_title_card(item))
        if not payload.get("items"):
            payload = dict(payload)
            payload["empty"] = True
            payload["note"] = str(payload.get("note") or "").strip() or (
                "No named link to something you finished — not a cosine guess."
            )
        return json.dumps(payload)

    async def _tool_query_library(self, args: Mapping[str, Any]) -> str:
        filters = self._apply_youth_filters(filters_from_mapping(args))
        if filters.semantic_query:
            result = await query_library_async(self.db, filters, self.settings)
        else:
            result = query_library(self.db, filters)
        _attach_query_cards(self, self.db, result["items"], filters)
        self.note_turn_audit_label(maybe_set_audit_context_label(self.db, filters))
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

    def _resolve_seed_library_row(self, args: Mapping[str, Any]):
        seed_row = None
        seed_id = args.get("item_id")
        if seed_id is not None:
            try:
                seed_row = self.db.library_item_by_id(int(seed_id))
            except (TypeError, ValueError):
                seed_row = None
        if seed_row is None:
            title = str(args.get("title") or "").strip()
            if not title:
                return None
            pattern = f"%{title.lower()}%"
            clauses = ["lower(title) LIKE ?"]
            params: List[Any] = [pattern]
            year = args.get("year")
            if year is not None:
                try:
                    clauses.append("year = ?")
                    params.append(int(year))
                except (TypeError, ValueError):
                    pass
            media_type = str(args.get("media_type") or "").strip().lower()
            if media_type in {"movie", "show"}:
                clauses.append("media_type = ?")
                params.append(media_type)
            with self.db.connect() as conn:
                seed_row = conn.execute(
                    f"""
                    SELECT * FROM library_items
                    WHERE {' AND '.join(clauses)}
                    ORDER BY CASE WHEN lower(title) = ? THEN 0 ELSE 1 END, title
                    LIMIT 1
                    """,
                    [*params, title.lower()],
                ).fetchone()
        return seed_row

    async def _tool_list_relations(self, args: Mapping[str, Any]) -> str:
        from projectionist.library.relations import list_relations_for_item

        seed_row = self._resolve_seed_library_row(args)
        if seed_row is None:
            return json.dumps({"error": "Provide item_id or title", "items": []})
        relation = args.get("relation")
        relation_s = str(relation).strip().lower() if relation else None
        limit = min(max(1, int(args.get("limit") or 25)), 50)
        payload = list_relations_for_item(
            self.db,
            int(seed_row["id"]),
            relation=relation_s,
            limit=limit,
        )
        payload["seed"] = {
            "id": int(seed_row["id"]),
            "title": str(seed_row["title"]),
            "year": seed_row["year"],
            "media_type": str(seed_row["media_type"]),
        }
        payload["items"] = peers_with_named_explanation(payload.get("items") or [])
        payload = kinship_empty_payload(payload)
        if payload.get("items"):
            payload["note"] = (
                "Relations come from title_relations_refresh (collection/neighbor/shared_crew)."
            )
        return json.dumps(payload)

    async def _tool_walk_relations(self, args: Mapping[str, Any]) -> str:
        from projectionist.library.relations import walk_relations

        seed_row = self._resolve_seed_library_row(args)
        if seed_row is None:
            return json.dumps({"error": "Provide item_id or title", "items": []})
        relation = args.get("relation")
        relation_s = str(relation).strip().lower() if relation else None
        payload = walk_relations(
            self.db,
            int(seed_row["id"]),
            relation=relation_s,
            depth=int(args.get("depth") or 1),
            limit=int(args.get("limit") or 25),
        )
        payload["seed"] = {
            "id": int(seed_row["id"]),
            "title": str(seed_row["title"]),
            "year": seed_row["year"],
            "media_type": str(seed_row["media_type"]),
        }
        payload["items"] = peers_with_named_explanation(payload.get("items") or [])
        payload = kinship_empty_payload(payload)
        return json.dumps(payload)

    async def _tool_titles_by_person(self, args: Mapping[str, Any]) -> str:
        person_id = args.get("person_id")
        tmdb_person_id = args.get("tmdb_person_id")
        name = str(args.get("name") or "").strip()
        limit = min(max(1, int(args.get("limit") or 25)), 100)

        resolved_person_id = None
        resolved_tmdb = None
        person_name = name
        if person_id is not None:
            try:
                resolved_person_id = int(person_id)
            except (TypeError, ValueError):
                resolved_person_id = None
        if tmdb_person_id is not None:
            try:
                resolved_tmdb = int(tmdb_person_id)
            except (TypeError, ValueError):
                resolved_tmdb = None

        if resolved_person_id is None and resolved_tmdb is None and name:
            pattern = f"%{name.lower()}%"
            with self.db.connect() as conn:
                person = conn.execute(
                    """
                    SELECT id, tmdb_person_id, name FROM people
                    WHERE lower(name) LIKE ?
                    ORDER BY CASE WHEN lower(name) = ? THEN 0 ELSE 1 END, name
                    LIMIT 1
                    """,
                    (pattern, name.lower()),
                ).fetchone()
            if person is not None:
                resolved_person_id = int(person["id"])
                person_name = str(person["name"] or name)
                if person["tmdb_person_id"] is not None:
                    resolved_tmdb = int(person["tmdb_person_id"])

        if resolved_person_id is None and resolved_tmdb is None:
            return json.dumps(
                {"error": "Provide person_id, tmdb_person_id, or name", "items": []}
            )

        rows = self.db.list_library_titles_for_person(
            person_id=resolved_person_id,
            tmdb_person_id=resolved_tmdb if resolved_person_id is None else None,
        )
        cards = []
        items = []
        for row in rows[:limit]:
            peer_map = _row_mapping(row)
            try:
                peer_id = int(peer_map.get("id") or 0)
            except (TypeError, ValueError):
                peer_id = 0
            explanation = _person_credit_explanation(
                peer_map, person_name=person_name, peer_id=peer_id or None
            )
            sentence = str((explanation or {}).get("sentence") or "").strip()
            if not sentence:
                continue
            card = row_to_title_card(row, reason=sanitize_recommendation_reason(sentence))
            if not self._card_allowed(card):
                continue
            cards.append(card)
            payload = _card_to_tool_item(card)
            payload["department"] = str(row["department"] or "") if "department" in row.keys() else ""
            payload["job"] = str(row["job"] or "") if "job" in row.keys() else ""
            payload["character"] = str(row["character"] or "") if "character" in row.keys() else ""
            payload["explanation"] = explanation
            items.append(payload)
        self._cards.extend(cards)
        payload = kinship_empty_payload(
            {
                "person": {
                    "person_id": resolved_person_id,
                    "tmdb_person_id": resolved_tmdb,
                    "name": person_name or None,
                },
                "items": items,
                "total_matched": len(items) if self.is_youth else len(rows),
            }
        )
        return json.dumps(payload)

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
        self.note_turn_audit_label(maybe_set_audit_context_label(self.db, filters))
        summary = aggregate_library(self.db, group_by, filters)  # type: ignore[arg-type]
        return json.dumps(summary)

    async def _tool_get_library_overview(self, args: Mapping[str, Any]) -> str:
        del args
        return json.dumps(library_overview(self.db))

    async def _tool_find_collection_gaps(self, args: Mapping[str, Any]) -> str:
        args = _augment_gaps_args_from_query(args)
        media_type = str(args.get("media_type") or "movie")
        if not self.settings.tmdb_api_key:
            return json.dumps({"error": "TMDB API key not configured"})
        tmdb = TMDBClient(self.settings.tmdb_api_key)
        owned = _excluded_add_tmdb_ids(self.db, media_type)
        year_from = args.get("year_from")
        year_to = args.get("year_to")
        with_type = _normalize_tv_type(args.get("tv_type")) if media_type == "show" else None

        genres = str(args.get("genres") or "").strip()
        genre_ids = ""
        genres_unresolved: List[str] = []
        genres_resolved: List[Any] = []
        genres_candidates: List[Any] = []
        genre_list: List[Mapping[str, Any]] = []
        if genres or str(args.get("without_genres") or "").strip():
            genre_list = list(
                tmdb.genre_list_movies() if media_type == "movie" else tmdb.genre_list_tv()
            )
        if genres:
            genre_meta = _resolve_tmdb_genre_ids(
                genre_list,
                genres,
                context_source="gaps",
                media_type=media_type,
            )
            genre_ids = str(genre_meta.get("genre_ids") or "")
            genres_unresolved = list(genre_meta.get("unresolved") or [])
            genres_resolved = list(genre_meta.get("resolved") or [])
            genres_candidates = list(genre_meta.get("genres_candidates") or [])
            ambiguous = list(genre_meta.get("ambiguous") or [])
            # Ambiguous genre (e.g. short token matching several names): clarify, keep tools.
            if ambiguous and not genre_ids:
                return _empty_gaps_payload(
                    note=(
                        "Genre filter is ambiguous — re-call find_collection_gaps with one exact "
                        f"name from genres_candidates ({', '.join(c.get('name', '') for c in genres_candidates)}). "
                        "Do not invent titles or broaden to unfiltered discover."
                    ),
                    genres_unresolved=genres_unresolved
                    + [str(a.get("query") or "") for a in ambiguous if a.get("query")],
                    genres_candidates=genres_candidates,
                    stop_retrying=False,
                )
            # Fail closed: empty resolve_genre_ids is the only authority — no pack/regex rescue.
            if not genre_ids:
                return _empty_gaps_payload(
                    note=(
                        "Could not resolve genres to TMDB genre ids "
                        f"({', '.join(genres_unresolved) or genres}). "
                        "Use exact TMDB names (e.g. Documentary, Drama), aliases like Science→Science Fiction, "
                        "plus query/companies for branded themes — do not invent titles or broaden "
                        "to unfiltered discover."
                    ),
                    genres_unresolved=genres_unresolved,
                    genres_candidates=genres_candidates or None,
                )

        without_genres_text = str(args.get("without_genres") or "").strip()
        without_genre_ids = ""
        without_genres_unresolved: List[str] = []
        if without_genres_text:
            if not genre_list:
                genre_list = list(
                    tmdb.genre_list_movies() if media_type == "movie" else tmdb.genre_list_tv()
                )
            without_meta = _resolve_tmdb_genre_ids(
                genre_list,
                without_genres_text,
                context_source="gaps",
                media_type=media_type,
            )
            without_genre_ids = str(without_meta.get("genre_ids") or "")
            without_genres_unresolved = list(without_meta.get("unresolved") or [])
            if without_meta.get("ambiguous") and not without_genre_ids:
                return _empty_gaps_payload(
                    note=(
                        "without_genres is ambiguous — re-call with an exact TMDB genre from "
                        f"genres_candidates ({', '.join(c.get('name', '') for c in (without_meta.get('genres_candidates') or []))})."
                    ),
                    genres_unresolved=without_genres_unresolved,
                    genres_candidates=list(without_meta.get("genres_candidates") or []),
                    stop_retrying=False,
                )

        keywords_text = str(args.get("keywords") or "").strip()
        keyword_meta: Dict[str, Any] = {"resolved": [], "unresolved": [], "keyword_ids": None}
        keyword_ids: Optional[str] = None
        if keywords_text:
            keyword_meta = _resolve_tmdb_keyword_ids(tmdb, keywords_text)
            unresolved_kw = list(keyword_meta.get("unresolved") or [])
            resolved_kw = list(keyword_meta.get("resolved") or [])
            # Brand-like unresolved keywords (BBC, PBS…) often are companies, not keywords.
            promoted_companies: List[str] = []
            still_unresolved: List[str] = []
            for kw in unresolved_kw:
                company_try = _resolve_tmdb_company_ids(tmdb, kw)
                if company_try.get("resolved"):
                    promoted_companies.append(kw)
                else:
                    still_unresolved.append(kw)
            keyword_meta["unresolved"] = still_unresolved
            if promoted_companies:
                existing_companies = str(args.get("companies") or "").strip()
                args = dict(args)
                args["companies"] = ", ".join(
                    part for part in (existing_companies, ", ".join(promoted_companies)) if part
                )
            if not resolved_kw and still_unresolved and not promoted_companies:
                return _empty_gaps_payload(
                    note=(
                        "Could not resolve keyword filter to confident TMDB keyword or company ids. "
                        "Pass query='BBC science documentary' (or similar), companies=BBC, and "
                        "genres=Documentary — or search_tmdb with a concrete title+year. "
                        "Do not invent TMDB ids or retry unfiltered discover."
                    ),
                    keywords_resolved=resolved_kw,
                    keywords_unresolved=still_unresolved,
                )
            keyword_ids = keyword_meta.get("keyword_ids") if resolved_kw else None

        without_keywords_text = str(args.get("without_keywords") or "").strip()
        without_keyword_ids: Optional[str] = None
        negative_kw_tokens: List[str] = []
        if without_keywords_text:
            without_kw_meta = _resolve_tmdb_keyword_ids(tmdb, without_keywords_text)
            without_keyword_ids = without_kw_meta.get("keyword_ids")
            negative_kw_tokens = _gap_theme_tokens(without_keywords_text)

        companies_text = str(args.get("companies") or "").strip()
        company_meta: Dict[str, Any] = {"resolved": [], "unresolved": [], "company_ids": None}
        company_ids: Optional[str] = None
        if companies_text:
            company_meta = _resolve_tmdb_company_ids(tmdb, companies_text)
            if not company_meta.get("resolved"):
                return _empty_gaps_payload(
                    note=(
                        "Could not resolve companies to TMDB company ids "
                        f"({', '.join(company_meta.get('unresolved') or []) or companies_text}). "
                        "Try query text instead (e.g. 'BBC science documentary') — "
                        "do not invent titles."
                    ),
                    companies_unresolved=list(company_meta.get("unresolved") or []),
                    keywords_resolved=list(keyword_meta.get("resolved") or []),
                    keywords_unresolved=list(keyword_meta.get("unresolved") or []),
                    genres_unresolved=genres_unresolved,
                )
            company_ids = company_meta.get("company_ids")

        query = str(args.get("query") or "").strip()
        # Do not boost theme tokens the user negated.
        negative_tokens = set(
            _gap_theme_tokens(without_genres_text, without_keywords_text)
        )
        theme_tokens = [
            tok
            for tok in _gap_theme_tokens(
                query,
                keywords_text,
                companies_text,
                " ".join(genres_unresolved),
            )
            if tok not in negative_tokens
        ]

        results: List[Mapping[str, Any]] = []
        # search_tv/movie cannot apply with_type (miniseries). Prefer discover whenever
        # tv_type is set so cards keep valid limited-series IDs — not sentence-search junk.
        used_search = bool(query) and not with_type
        if used_search:
            # Branded / topical needles (BBC science docs, etc.): text search + post-filters.
            raw = tmdb.search_movie(query) if media_type == "movie" else tmdb.search_tv(query)
            if not isinstance(raw, list):
                raw = []
            if genre_ids:
                wanted_genre_ids = {int(g) for g in genre_ids.split(",") if g.isdigit()}
                filtered: List[Mapping[str, Any]] = []
                for item in raw:
                    if not isinstance(item, Mapping):
                        continue
                    item_genres = item.get("genre_ids") or []
                    try:
                        item_ids = {int(g) for g in item_genres}
                    except (TypeError, ValueError):
                        item_ids = set()
                    if item_ids & wanted_genre_ids:
                        filtered.append(item)
                results = filtered
            else:
                results = [item for item in raw if isinstance(item, Mapping)]
            # year_from/year_to apply on the query/search path too.
            results = _filter_tmdb_results_by_year(
                results, year_from=year_from, year_to=year_to
            )
            results = _filter_tmdb_results_without_genres(results, without_genre_ids)
            results = _filter_tmdb_results_without_keyword_tokens(
                results, negative_kw_tokens
            )
        elif media_type == "movie":
            results = tmdb.discover_movies(
                year_from=year_from,
                year_to=year_to,
                with_genres=genre_ids or None,
                without_genres=without_genre_ids or None,
                with_keywords=keyword_ids,
                without_keywords=without_keyword_ids,
                with_companies=company_ids,
            )
        else:
            results = tmdb.discover_tv(
                year_from=year_from,
                year_to=year_to,
                with_genres=genre_ids or None,
                without_genres=without_genre_ids or None,
                with_keywords=keyword_ids,
                without_keywords=without_keyword_ids,
                with_companies=company_ids,
                with_type=with_type,
            )
            # Optional pack enrichment from taxonomy.json only (never inlined here).
            facet_pack = match_facet_pack(genres) if genres else None
            if facet_pack and facet_pack.keyword_queries:
                pack_kw = _resolve_tmdb_keyword_ids(
                    tmdb, ", ".join(facet_pack.keyword_queries)
                )
                pack_kw_ids = pack_kw.get("keyword_ids")
                if pack_kw_ids and pack_kw_ids != keyword_ids:
                    extra = tmdb.discover_tv(
                        year_from=year_from,
                        year_to=year_to,
                        without_genres=without_genre_ids or None,
                        with_keywords=str(pack_kw_ids),
                        without_keywords=without_keyword_ids,
                        with_type=with_type,
                    )
                    if isinstance(extra, list):
                        results = _merge_tmdb_results_by_id(
                            results if isinstance(results, list) else [],
                            filter_pack_keyword_hits(
                                extra, facet_pack, genre_list=genre_list
                            ),
                        )
                    for entry in pack_kw.get("resolved") or []:
                        if entry not in (keyword_meta.get("resolved") or []):
                            keyword_meta.setdefault("resolved", []).append(entry)

        if not isinstance(results, list):
            results = []

        # Search path: keep only theme-overlapping hits. Fail closed on zero overlap
        # (never emit unrelated posters/IDs). Structured discover trusts TMDB filters.
        if used_search and theme_tokens:
            scored = [
                (_gap_item_relevance(item, theme_tokens), item)
                for item in results
                if isinstance(item, Mapping)
            ]
            scored.sort(key=lambda pair: pair[0], reverse=True)
            results = [item for score, item in scored if score > 0]

        cards: List[TitleCard] = []
        for item in results:
            if not isinstance(item, Mapping):
                continue
            tmdb_id = int(item.get("id") or 0)
            title = str(item.get("title") or item.get("name") or "").strip()
            # Fail closed: never emit id-less or title-less cards onto the gap rail.
            if tmdb_id <= 0 or not title or tmdb_id in owned:
                continue
            if media_type == "show":
                item = _enrich_show_external_ids(item, tmdb, settings=self.settings)
            card = _apply_queue_flags(
                self.db,
                _tmdb_card(item, media_type, tmdb, reason="Missing from your collection"),
            )
            if not card.tmdb_id or not str(card.title or "").strip():
                continue
            if card.in_radarr or card.in_sonarr:
                continue
            cards.append(card)
            if len(cards) >= 12:
                break
        # Youth: unrated TMDB cards fail closed — strip from JSON so the model cannot name them.
        allowed = self._allowed_cards(cards)
        _append_recommendation_cards(self, allowed)
        note = (
            "TMDB titles missing from the library and not already queued in Radarr/Sonarr. "
            "Do not re-propose already_queued / in_radarr / in_sonarr titles. "
            "Shows with add_blocked_reason lack a TVDB id — tell the user honestly; "
            "do not invent tvdb_id values."
        )
        stop_retrying = False
        themed = bool(
            keywords_text
            or companies_text
            or query
            or genres
            or without_genres_text
            or without_keywords_text
            or with_type
            or year_from is not None
            or year_to is not None
        )
        if self.is_youth and not allowed:
            note = (
                "No external titles available under Youth content rules "
                "(unrated and over-ceiling titles are omitted)."
            )
            stop_retrying = True
        elif not allowed and themed:
            note = (
                "No confident missing titles matched these filters. "
                "Tell the user honestly — do not invent titles, do not broaden to unfiltered discover, "
                "and at most try one search_tmdb with a concrete title+year you already know."
            )
            stop_retrying = True
        elif keyword_meta.get("unresolved") or company_meta.get("unresolved") or genres_unresolved:
            note += (
                " Some filters were dropped as unresolved; only confident matches are shown. "
                "Do not invent replacements for unresolved facets."
            )
        if without_genres_unresolved:
            note += (
                f" Unresolved without_genres dropped: {', '.join(without_genres_unresolved)}."
            )
        payload: Dict[str, Any] = {
            "total_matched": len(allowed),
            "returned": len(allowed),
            "offset": 0,
            "has_more": False,
            "items": [_card_to_tool_item(c) for c in allowed],
            "keywords_resolved": keyword_meta.get("resolved") or [],
            "keywords_unresolved": keyword_meta.get("unresolved") or [],
            "companies_resolved": company_meta.get("resolved") or [],
            "companies_unresolved": company_meta.get("unresolved") or [],
            "genres_resolved": genres_resolved,
            "genres_unresolved": genres_unresolved,
            "stop_retrying": stop_retrying,
            "note": note,
        }
        if genres_candidates:
            payload["genres_candidates"] = genres_candidates
        if with_type:
            payload["tv_type"] = str(args.get("tv_type") or "")
            payload["with_type"] = with_type
        return json.dumps(payload)

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
                item = _enrich_show_external_ids(item, tmdb, settings=self.settings)
            card = _apply_queue_flags(
                self.db,
                _tmdb_card(item, media_type, tmdb, reason=f"Hidden gem ({rating:.1f}/10)"),
            )
            if card.in_radarr or card.in_sonarr:
                continue
            cards.append(card)
            if len(cards) >= 10:
                break
        allowed = self._allowed_cards(cards)
        _append_recommendation_cards(self, allowed)
        note = "Highly rated TMDB titles not in the library and not already queued."
        if self.is_youth and not allowed:
            note = (
                "No external titles available under Youth content rules "
                "(unrated and over-ceiling titles are omitted)."
            )
        return json.dumps(
            {
                "total_matched": len(allowed),
                "returned": len(allowed),
                "offset": 0,
                "has_more": False,
                "items": [_card_to_tool_item(c) for c in allowed],
                "note": note,
            }
        )

    async def _tool_suggest_purge_candidates(self, args: Mapping[str, Any]) -> str:
        cards = self._allowed_cards(
            suggest_purge_candidates(self.db, self.settings, limit=int(args.get("limit") or 12))
        )
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

    async def _tool_search_tmdb(self, args: Mapping[str, Any]) -> str:
        raw_tmdb_id = args.get("tmdb_id")
        raw_year = args.get("year")
        result = external_tmdb_search(
            self.db,
            self.settings,
            media_type=str(args.get("media_type") or "movie"),
            title=str(args.get("title") or ""),
            tmdb_id=int(raw_tmdb_id) if raw_tmdb_id is not None else None,
            year=int(raw_year) if raw_year is not None else None,
            limit=int(args.get("limit") or 10),
            reason=str(args.get("reason") or args.get("recommendation_reason") or ""),
        )
        if not result.ok:
            error_payload: Dict[str, Any] = {"error": result.error, "items": []}
            return json.dumps(error_payload)

        allowed_cards = self._allowed_cards(result.cards)
        items = self._youth_filter_tool_items(result.items, cards=result.cards)
        total_matched = len(items) if self.is_youth else result.total_matched
        # Targeted title/id lookups replace prior discover/gap junk so the rail
        # matches the titles the agent is about to name — never leave stale posters.
        targeted = bool(str(args.get("title") or "").strip()) or raw_tmdb_id is not None
        if targeted and allowed_cards and not getattr(self, "_cleared_discussed_for_targeted_search", False):
            self._discussed_cards.clear()
            self._cleared_discussed_for_targeted_search = True
        _append_recommendation_cards(self, allowed_cards)
        note = (
            "Prefer verified title+year (or a tool-returned tmdb_id) so turnstyle cards pin one work. "
            "Never invent numeric ids. Only propose adds for in_library=false AND already_queued=false "
            "(also respect in_radarr/in_sonarr). Use tmdb_id for add_to_radarr; tvdb_id for add_to_sonarr. "
            "Pass reason on search_tmdb or call set_recommendation_reasons so Why this? "
            "shows curator rationale (never pipeline labels)."
        )
        if self.is_youth and not items:
            note = (
                "No external titles available under Youth content rules "
                "(unrated and over-ceiling titles are omitted)."
            )
        return json.dumps(
            {
                "total_matched": total_matched,
                "returned": len(items),
                "offset": 0,
                "has_more": (not self.is_youth) and result.total_matched > len(items),
                "items": items,
                "note": note,
            }
        )

    async def _tool_get_title_detail(self, args: Mapping[str, Any]) -> str:
        media_type = str(args.get("media_type") or "movie")
        kwargs: Dict[str, Any] = {"media_type": media_type}
        if args.get("rating_key"):
            kwargs["rating_key"] = str(args["rating_key"])
        if args.get("tmdb_id"):
            kwargs["tmdb_id"] = int(args["tmdb_id"])
        if args.get("tvdb_id"):
            kwargs["tvdb_id"] = int(args["tvdb_id"])
        if not any(k in kwargs for k in ("rating_key", "tmdb_id", "tvdb_id")):
            return json.dumps({"error": "Provide tmdb_id, tvdb_id, or rating_key"})
        detail = get_title_detail(self.db, self.settings, **kwargs)
        dumped = detail.model_dump()
        # A rating of an unexpected shape must read as unrated so the gate fails closed.
        if not isinstance(dumped.get("content_rating"), str):
            dumped["content_rating"] = ""
        card = TitleCard.model_validate(dumped)
        if not self._card_allowed(card):
            return json.dumps({"error": "Title not available under Youth content rules"})
        self._offer_card(card)
        return json.dumps(_detail_to_tool_payload(detail, self.settings))

    async def _tool_explore_genre(self, args: Mapping[str, Any]) -> str:
        genre = str(args.get("genre") or "").strip()
        media_type = str(args.get("media_type") or "movie")
        include_missing = bool(args.get("include_missing", True))
        offset = int(args.get("offset") or 0)
        page_limit = int(args.get("limit") or 16)
        with_type = _normalize_tv_type(args.get("tv_type")) if media_type == "show" else None
        without_genres_text = str(args.get("without_genres") or "").strip()

        filters = self._apply_youth_filters(
            LibraryFilters(
                media_type=media_type,
                genres=[genre] if genre else [],
                offset=offset,
                limit=page_limit,
            )
        )
        owned_result = query_library(self.db, filters)
        owned_cards: List[TitleCard] = []
        for item in owned_result["items"]:
            row = self.db.library_item_by_id(int(item["id"]))
            if row is not None:
                card = row_to_title_card(row, reason=f"In library · {genre.title()}")
                if self._card_allowed(card):
                    owned_cards.append(card)
        missing_cards: List[TitleCard] = []

        if include_missing and self.settings.tmdb_api_key:
            tmdb = TMDBClient(self.settings.tmdb_api_key)
            owned = _excluded_add_tmdb_ids(self.db, media_type)
            genre_list = tmdb.genre_list_movies() if media_type == "movie" else tmdb.genre_list_tv()
            # Fail-closed: same resolve contract as find_collection_gaps (no soft OR).
            resolved = (
                _resolve_tmdb_genre_ids(
                    genre_list,
                    genre,
                    context_source="explore_genre",
                    media_type=media_type,
                )
                if genre
                else {}
            )
            genre_ids = [
                gid for gid in str(resolved.get("genre_ids") or "").split(",") if gid
            ]
            without_genre_ids = ""
            if without_genres_text:
                without_meta = _resolve_tmdb_genre_ids(
                    genre_list,
                    without_genres_text,
                    context_source="explore_genre",
                    media_type=media_type,
                )
                without_genre_ids = str(without_meta.get("genre_ids") or "")
            if genre_ids:
                if media_type == "movie":
                    results = tmdb.discover_movies(
                        with_genres=",".join(genre_ids),
                        without_genres=without_genre_ids or None,
                    )
                else:
                    results = tmdb.discover_tv(
                        with_genres=",".join(genre_ids),
                        without_genres=without_genre_ids or None,
                        with_type=with_type,
                    )
                for item in results:
                    tmdb_id = int(item.get("id") or 0)
                    if tmdb_id <= 0 or tmdb_id in owned:
                        continue
                    if media_type == "show":
                        item = _enrich_show_external_ids(item, tmdb, settings=self.settings)
                    card = _apply_queue_flags(
                        self.db,
                        _tmdb_card(item, media_type, tmdb, reason=f"Not in library · {genre.title()}"),
                    )
                    if card.in_radarr or card.in_sonarr:
                        continue
                    if not self._card_allowed(card):
                        continue
                    missing_cards.append(card)
                    if len(missing_cards) >= page_limit:
                        break

        if include_missing:
            _append_recommendation_cards(self, missing_cards)
        else:
            for card in owned_cards:
                self._offer_card(card)

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

    async def _tool_get_todays_anniversaries(self, args: Mapping[str, Any]) -> str:
        """Surface library titles with milestone release anniversaries (5, 10, 15, 20, 25+ years)."""
        from datetime import date

        limit = int(args.get("limit") or 5)
        today = date.today()
        current_year = today.year

        milestone_years = [
            current_year - n
            for n in (5, 10, 15, 20, 25, 30, 40, 50, 75)
        ]

        placeholders = ",".join("?" * len(milestone_years))
        with self.db.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT id, rating_key, media_type, title, year, genres, poster_url,
                       backdrop_url, view_count, last_viewed_at, tmdb_id, tvdb_id,
                       runtime_minutes, summary, in_radarr, in_sonarr
                FROM library_items
                WHERE year IN ({placeholders})
                ORDER BY year ASC
                LIMIT ?
                """,
                (*milestone_years, limit),
            ).fetchall()

        if not rows:
            return json.dumps({"items": [], "note": "No library anniversaries today."})

        items = []
        for row in rows:
            years_ago = current_year - (row["year"] or current_year)
            context = f"Released {years_ago} year{'s' if years_ago != 1 else ''} ago"
            last_viewed = row["last_viewed_at"]
            if last_viewed:
                months_ago = max(1, int((time.time() - last_viewed) / (30 * 86400)))
                context += f" \u00b7 Last watched {months_ago} month{'s' if months_ago != 1 else ''} ago"
            card = row_to_title_card(
                dict(row),
                reason=context,
            )
            self._offer_card(card)
            items.append({**_card_to_tool_item(card), "anniversary_context": context})

        return json.dumps({"items": items, "count": len(items)})

    async def _tool_get_library_snapshot(self, args: Mapping[str, Any]) -> str:
        """Return a high-level library summary for the 'at a glance' card."""
        del args
        overview = library_overview(self.db)
        total = overview.get("total", 0)
        movies = overview.get("movies", 0)
        shows = overview.get("shows", 0)

        with self.db.connect() as conn:
            genre_rows = conn.execute(
                "SELECT genres FROM library_items WHERE genres != '[]'"
            ).fetchall()
            decade_rows = conn.execute(
                "SELECT MIN(year) as min_year, MAX(year) as max_year FROM library_items WHERE year IS NOT NULL"
            ).fetchone()
            hidden_gem_count = conn.execute(
                """
                SELECT COUNT(*) as cnt FROM library_items
                WHERE view_count = 0
                  AND vote_average IS NOT NULL
                  AND vote_average >= 7.0
                """
            ).fetchone()

        genre_counts: Dict[str, int] = {}
        for row in genre_rows:
            try:
                genres_list = json.loads(row["genres"]) if isinstance(row["genres"], str) else row["genres"]
            except (json.JSONDecodeError, TypeError):
                continue
            for genre in genres_list:
                genre_counts[genre] = genre_counts.get(genre, 0) + 1

        top_genres = sorted(genre_counts.items(), key=lambda x: x[1], reverse=True)[:3]
        min_year = decade_rows["min_year"] if decade_rows else None
        max_year = decade_rows["max_year"] if decade_rows else None
        decade_range = f"{min_year}–{max_year}" if min_year and max_year else "unknown"
        gems = hidden_gem_count["cnt"] if hidden_gem_count else 0

        return json.dumps({
            "total": total,
            "movies": movies,
            "shows": shows,
            "top_genres": [{"name": g, "count": c} for g, c in top_genres],
            "decade_range": decade_range,
            "hidden_gems": gems,
        })

