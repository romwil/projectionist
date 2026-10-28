"""Tonight / follow-up / persona-consult agent tools."""

from __future__ import annotations

from projectionist.agent.tools._helpers import *  # noqa: F401, F403

class TonightToolsMixin:
    async def _tool_suggest_follow_ups(self, args: Mapping[str, Any]) -> str:
        """Store presentation-only, safe next-turn suggestions from the agent."""
        replies = args.get("replies")
        if not isinstance(replies, list):
            return json.dumps({"error": "replies must be a list of 2-4 strings"})
        cleaned: List[str] = []
        seen: set[str] = set()
        for raw in replies:
            text = " ".join(str(raw or "").split()).strip()
            key = text.casefold()
            if (
                not text
                or len(text) > 120
                or key in seen
                or text.startswith(("/", "~", "\\"))
                or re.search(r"(?:^|[\s])(?:[A-Za-z]:[\\/]|file:|https?://)", text, re.I)
            ):
                continue
            seen.add(key)
            cleaned.append(text)
            if len(cleaned) == 4:
                break
        self._suggested_replies = cleaned
        return json.dumps({"replies": cleaned})

    async def _tool_consult_persona(self, args: Mapping[str, Any]) -> str:
        """Ask a sibling curator for a short quoted answer (village consult)."""
        from projectionist.agent.village import (
            build_shared_consult_context,
            consult_unavailable_payload,
            gather_specialty_context,
            resolve_village_sibling,
            run_persona_consult,
        )

        if self.is_youth:
            return json.dumps(
                consult_unavailable_payload(
                    reason=(
                        "Village consults are unavailable for youth accounts "
                        "(shared memory scope is fail-closed)."
                    ),
                    code="consult_privacy",
                )
            )
        if self._consult_used:
            return json.dumps(
                consult_unavailable_payload(
                    reason=(
                        "Already consulted one sibling this turn — answer with your own take "
                        "or wait for the next user message."
                    ),
                    code="consult_limit",
                )
            )

        sibling = resolve_village_sibling(args.get("persona"))
        if sibling is None:
            return json.dumps(
                consult_unavailable_payload(
                    reason=(
                        "Unknown sibling. Use Scholar, Enthusiast, Concierge, or Companion."
                    ),
                    code="consult_unknown_persona",
                )
            )

        # Same builtin template id is OK (e.g. Classic Curator asking Concierge):
        # village labels are specialty archetypes, not a hard persona switch.

        question = " ".join(str(args.get("question") or "").split()).strip()
        if not question:
            return json.dumps(
                consult_unavailable_payload(
                    reason="consult_persona requires a short question.",
                    code="consult_bad_args",
                )
            )

        # Reserve the single consult slot before the LLM round so parallel tool
        # batches in the same turn cannot fire a second sibling call.
        self._consult_used = True

        shared = build_shared_consult_context(
            self.db,
            user_id=self.user_id,
            user_role=self.user_role,
            discussed_cards=self._discussed_cards,
            cards=self._cards,
            question=question,
        )
        specialty = await gather_specialty_context(self, sibling, args)
        payload = await run_persona_consult(
            self,
            sibling,
            question=question,
            shared=shared,
            specialty=specialty,
            session_id=self.session_id,
        )
        if payload.get("quote_ok") or payload.get("pending"):
            self._persona_consults.append(dict(payload))
        return json.dumps(payload)

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

    async def _tool_what_to_watch_tonight(self, args: Mapping[str, Any]) -> str:
        from projectionist.library.tonight import build_tonight_watch

        youth_ceiling = None
        if self.is_youth:
            from projectionist.youth.rating_gate import resolve_youth_max_rating

            youth_ceiling = resolve_youth_max_rating(self.settings)
        payload = build_tonight_watch(
            self.db,
            media_type=args.get("media_type"),
            runtime_max=args.get("runtime_max"),
            limit=int(args.get("limit") or 8),
            youth_max_rating=youth_ceiling,
            user_id=self.user_id,
            multi_user_enabled=bool(self.settings.features.multi_user_enabled),
        )
        cards: List[TitleCard] = []
        for item in list(payload.get("items") or []) + list(payload.get("continue") or []):
            if not isinstance(item, dict):
                continue
            explanation = item.get("explanation") if isinstance(item.get("explanation"), dict) else {}
            sentence = str(
                (explanation or {}).get("sentence") or item.get("sentence") or item.get("why") or ""
            ).strip()
            cards.append(
                _feed_item_to_title_card({**item, "why": sentence, "recommendation_reason": sentence})
            )
        allowed = self._allowed_cards(cards)
        self._cards.extend(allowed)
        return json.dumps(payload)

    async def _tool_get_tonight_picks(self, args: Mapping[str, Any]) -> str:
        """Suggest unwatched titles for tonight, optionally filtered by runtime."""
        max_runtime = args.get("max_runtime_minutes")
        limit = int(args.get("limit") or 5)

        where_clauses = ["view_count = 0"]
        params: List[Any] = []
        if max_runtime is not None:
            where_clauses.append("runtime_minutes IS NOT NULL AND runtime_minutes <= ?")
            params.append(int(max_runtime))

        where_sql = " AND ".join(where_clauses)
        with self.db.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT id, rating_key, media_type, title, year, genres, poster_url,
                       backdrop_url, view_count, last_viewed_at, tmdb_id, tvdb_id,
                       runtime_minutes, summary, in_radarr, in_sonarr, content_rating
                FROM library_items
                WHERE {where_sql}
                ORDER BY RANDOM()
                LIMIT ?
                """,
                (*params, limit),
            ).fetchall()

        cards: List[TitleCard] = []
        for row in rows:
            runtime = row["runtime_minutes"]
            reason = f"{runtime} min" if runtime else "Unwatched"
            card = row_to_title_card(dict(row), reason=reason)
            if not self._card_allowed(card):
                continue
            cards.append(card)
            self._offer_card(card)

        return json.dumps({
            "items": [_card_to_tool_item(c) for c in cards],
            "count": len(cards),
            "max_runtime_filter": max_runtime,
        })

    async def _tool_suggest_double_feature(self, args: Mapping[str, Any]) -> str:
        """Pick two complementary library titles for a double feature pairing."""
        theme = str(args.get("theme") or "").strip().lower()
        youth_ceiling = None
        if self.is_youth:
            from projectionist.youth.rating_gate import resolve_youth_max_rating

            youth_ceiling = resolve_youth_max_rating(self.settings)

        payload = suggest_tonight_double_feature(
            self.db,
            theme=theme,
            youth_max_rating=youth_ceiling,
        )
        item_a = payload.get("title_a")
        item_b = payload.get("title_b")
        if not item_a or not item_b:
            return json.dumps({"error": "Not enough titles to form a double feature."})

        card_a = _feed_item_to_title_card(item_a)
        card_b = _feed_item_to_title_card(item_b)
        if self.is_youth and (
            not self._card_allowed(card_a) or not self._card_allowed(card_b)
        ):
            return json.dumps({"error": "Not enough titles to form a double feature."})

        self._offer_card(card_a)
        self._offer_card(card_b)

        return json.dumps({
            "double_feature": True,
            "title_a": _card_to_tool_item(card_a),
            "title_b": _card_to_tool_item(card_b),
            "bridge_text": payload.get("bridge_text") or "",
            "combined_runtime": int(payload.get("combined_runtime") or 0),
        })

    async def _tool_quick_pick_roulette(self, args: Mapping[str, Any]) -> str:
        """Pick ONE random unwatched title matching taste profile, optionally constrained."""
        max_runtime = args.get("max_runtime_minutes")
        genres_filter = str(args.get("genres") or "").strip()

        where_clauses = ["COALESCE(view_count, 0) = 0"]
        params: List[Any] = []
        if max_runtime is not None:
            where_clauses.append("runtime_minutes IS NOT NULL AND runtime_minutes <= ?")
            params.append(int(max_runtime))
        if genres_filter:
            genre_parts = [g.strip() for g in genres_filter.split(",") if g.strip()]
            if genre_parts:
                genre_or = " OR ".join("LOWER(genres) LIKE ?" for _ in genre_parts)
                where_clauses.append(f"({genre_or})")
                params.extend(f"%{g.lower()}%" for g in genre_parts)

        where_sql = " AND ".join(where_clauses)
        # Draw a small random pool rather than one row so the Youth gate can reject
        # an over-ceiling draw without turning the roulette into a dead end.
        with self.db.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT id, rating_key, media_type, title, year, genres, poster_url,
                       backdrop_url, view_count, last_viewed_at, tmdb_id, tvdb_id,
                       runtime_minutes, summary, in_radarr, in_sonarr, content_rating
                FROM library_items
                WHERE {where_sql}
                ORDER BY RANDOM()
                LIMIT 25
                """,
                params,
            ).fetchall()

        from projectionist.notifications.recommendation_reasons import (
            named_bridge_for_item,
            tracker_watched_item_ids,
        )
        from projectionist.youth.rating_gate import resolve_youth_max_rating

        watched_ids = tracker_watched_item_ids(self.db)
        youth_max = resolve_youth_max_rating(self.settings) if self.is_youth else None
        row = None
        for candidate in rows:
            try:
                if int(candidate["id"]) in watched_ids:
                    continue
            except (TypeError, ValueError, KeyError):
                pass
            if not self._card_allowed(row_to_title_card(dict(candidate))):
                continue
            row = candidate
            break
        if not row:
            return json.dumps({"error": "No unwatched titles match the criteria."})

        genres_raw = row["genres"]
        genres_list: List[Any] = []
        if isinstance(genres_raw, list):
            genres_list = genres_raw
        elif isinstance(genres_raw, str) and genres_raw.strip():
            try:
                parsed = json.loads(genres_raw)
                genres_list = parsed if isinstance(parsed, list) else []
            except (TypeError, ValueError, json.JSONDecodeError):
                genres_list = []

        # row_to_title_card expects genres as a JSON string (sqlite shape).
        item = dict(row)
        item["genres"] = json.dumps(genres_list)
        explanation = named_bridge_for_item(
            self.db,
            dict(row),
            user_id=self.user_id,
            multi_user_enabled=bool(
                getattr(self.settings.features, "multi_user_enabled", False)
            ),
            youth_max_rating=youth_max,
        )
        sentence = str((explanation or {}).get("sentence") or "").strip()
        card = row_to_title_card(item, reason=sentence)
        self._offer_card(card)
        tool_item = _card_to_tool_item(card)
        if explanation:
            tool_item["explanation"] = explanation
        return json.dumps({
            "quick_pick": True,
            "item": tool_item,
            "why": sentence,
            "explanation": explanation,
        })

