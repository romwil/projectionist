"""Reviews and watch-pattern agent tools."""

from __future__ import annotations

from projectionist.agent.tools._helpers import *  # noqa: F401, F403

class ReviewsToolsMixin:
    async def _tool_analyze_watch_patterns(self, args: Mapping[str, Any]) -> str:
        filters = filters_from_mapping(args)
        where_sql, params = _build_where_for_patterns(filters)
        genre_counts: Dict[str, int] = {}
        movie_completed_watches = 0
        episode_completed_plays = 0
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
        rows = enrich_rows_with_episode_play_sums(self.db, rows)
        for row in rows:
            total_items += 1
            views = effective_view_count(row)
            if str(row["media_type"] or "").lower() == "show":
                episode_completed_plays += views
            else:
                movie_completed_watches += views
            if watch_progress_state(row) == "unwatched":
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
            "movie_completed_watches": movie_completed_watches,
            "episode_completed_plays": episode_completed_plays,
            "total_completed_units": movie_completed_watches + episode_completed_plays,
            "count_note": (
                "Movie counts are Plex completed-or-marked-played records; TV counts are "
                "completed-or-marked-played episode sums, not playback sessions."
            ),
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
        denied = self._deny_personal_mutation_if_gated()
        if denied:
            return denied
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

    async def _tool_suggest_titles_to_rate(self, args: Mapping[str, Any]) -> str:
        limit = int(args.get("limit") or 10)
        include_household = not self.settings.features.multi_user_enabled
        suggestions = list_titles_to_rate(
            self.db,
            user_id=self.user_id,
            limit=limit,
            include_household_viewed=include_household,
        )
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
                if self.user_id:
                    mark_prompts_surfaced(self.db, [prompt["id"]], user_id=self.user_id)
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

    async def _tool_start_review_dialogue(self, args: Mapping[str, Any]) -> str:
        from projectionist.persona.presets import build_review_dialogue

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
            prompts = list_pending_prompts(self.db, user_id=self.user_id, limit=50)
            matching = [prompt for prompt in prompts if prompt["rating_key"] == rating_key]
            if matching:
                completion_pct = float(matching[0].get("completion_pct") or completion_pct)
                if self.user_id:
                    mark_prompts_surfaced(
                        self.db, [str(matching[0]["id"])], user_id=self.user_id
                    )

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

