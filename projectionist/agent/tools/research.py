"""Research-domain agent tools (title / person / company / filmography)."""

from __future__ import annotations

from projectionist.agent.tools._helpers import *  # noqa: F401, F403

class ResearchToolsMixin:
    async def _tool_research_title(self, args: Mapping[str, Any]) -> str:
        """Return source-attributed enrichment without exposing local file metadata."""
        row = self._resolve_seed_library_row(args)
        title = str(args.get("title") or "").strip()
        year = args.get("year")
        media_type = str(args.get("media_type") or "movie").strip().lower()
        tmdb_id = args.get("tmdb_id")
        tvdb_id = args.get("tvdb_id")
        imdb_id = str(args.get("imdb_id") or "").strip()
        if row is not None:
            title = str(row["title"] or title)
            year = row["year"] if row["year"] is not None else year
            media_type = str(row["media_type"] or media_type)
            tmdb_id = row["tmdb_id"] if row["tmdb_id"] is not None else tmdb_id
            tvdb_id = row["tvdb_id"] if row["tvdb_id"] is not None else tvdb_id
            imdb_id = str(row["imdb_id"] or imdb_id)
        if not title:
            return json.dumps({"error": "Provide a library item_id or title"})
        try:
            year_int = int(year) if year is not None else None
            tmdb_int = int(tmdb_id) if tmdb_id is not None else None
            tvdb_int = int(tvdb_id) if tvdb_id is not None else None
        except (TypeError, ValueError):
            return json.dumps({"error": "year, tmdb_id, and tvdb_id must be integers"})
        result = research_title(
            self.settings,
            title=title,
            year=year_int,
            media_type=media_type,
            tmdb_id=tmdb_int,
            tvdb_id=tvdb_int,
            imdb_id=imdb_id,
            db=self.db,
            library_item_id=int(row["id"]) if row is not None else None,
        )
        self._note_research_activity(result)
        return json.dumps(result)

    async def _tool_research_person(self, args: Mapping[str, Any]) -> str:
        name = str(args.get("name") or "").strip()
        if not name:
            return json.dumps({"error": "Provide a person name"})
        try:
            tmdb_id = int(args["tmdb_id"]) if args.get("tmdb_id") is not None else None
        except (TypeError, ValueError):
            return json.dumps({"error": "tmdb_id must be an integer"})
        result = research_person(self.settings, name=name, tmdb_id=tmdb_id, db=self.db)
        self._note_research_activity(result)
        self._register_filmography_gap_cards(result)
        return json.dumps(result)

    async def _tool_research_company(self, args: Mapping[str, Any]) -> str:
        name = str(args.get("name") or "").strip()
        try:
            tmdb_id = int(args["tmdb_id"])
        except (KeyError, TypeError, ValueError):
            return json.dumps({"error": "Provide a company name and integer tmdb_id"})
        result = research_company(self.settings, name=name, tmdb_id=tmdb_id, db=self.db)
        self._note_research_activity(result)
        return json.dumps(result)

    async def _tool_compare_filmographies(self, args: Mapping[str, Any]) -> str:
        def resolve(prefix: str) -> tuple[str, Optional[int]]:
            raw = args.get(f"{prefix}_tmdb_id")
            return str(args.get(f"{prefix}_name") or "").strip(), int(raw) if raw is not None else None
        try:
            left_name, left_id = resolve("left")
            right_name, right_id = resolve("right")
        except (TypeError, ValueError):
            return json.dumps({"error": "person TMDB ids must be integers"})
        if not left_name or not right_name:
            return json.dumps({"error": "Provide both person names"})
        left = research_person(self.settings, name=left_name, tmdb_id=left_id, db=self.db)
        right = research_person(self.settings, name=right_name, tmdb_id=right_id, db=self.db)
        self._note_research_activity(left)
        self._note_research_activity(right)
        return json.dumps(compare_filmographies(left, right))

    def _note_research_activity(self, result: Optional[Mapping[str, Any]]) -> None:
        """Best-effort: mark a just-researched entity as discussed. Never raises."""
        if not isinstance(result, Mapping):
            return
        memory = result.get("memory") if isinstance(result.get("memory"), Mapping) else None
        entity_id = str((memory or {}).get("entity_id") or "").strip()
        try:
            if entity_id:
                self.db.record_entity_discussion(entity_id)
        except Exception:
            logger.debug("Could not record research activity", exc_info=True)

    def _register_filmography_gap_cards(self, result: Mapping[str, Any]) -> None:
        """Push missing filmography titles into discussed cards for section-aware rails."""
        filmography = result.get("filmography") if isinstance(result.get("filmography"), list) else []
        gap_cards: List[TitleCard] = []
        for entry in filmography:
            if not isinstance(entry, Mapping):
                continue
            if entry.get("in_library"):
                continue
            tmdb_id = entry.get("tmdb_id")
            if tmdb_id is None:
                continue
            year_raw = str(entry.get("year") or "").strip()
            year = int(year_raw) if year_raw.isdigit() else None
            media_type = "show" if str(entry.get("media_type") or "") == "show" else "movie"
            gap_cards.append(
                TitleCard(
                    media_type=media_type,
                    title=str(entry.get("title") or "Untitled"),
                    year=year,
                    tmdb_id=int(tmdb_id),
                    in_library=False,
                    in_radarr=bool(entry.get("in_radarr")),
                    in_sonarr=bool(entry.get("in_sonarr")),
                )
            )
            if len(gap_cards) >= 40:
                break
        if gap_cards:
            _append_recommendation_cards(self, gap_cards)

