"""Watchlist agent tools."""

from __future__ import annotations

from projectionist.agent.tools._helpers import *  # noqa: F401, F403

class WatchlistToolsMixin:
    async def _tool_query_watchlist(self, args: Mapping[str, Any]) -> str:
        from projectionist.watchlist.curate import enrich_watchlist_pins

        limit = int(args.get("limit") or 50)
        user_id = self.user_id if self.settings.features.multi_user_enabled else None
        pins = self.db.list_watchlist_pins(user_id=user_id)[:limit]
        items = enrich_watchlist_pins(self.db, pins)
        return json.dumps({"items": items, "count": len(items)})

    async def _tool_add_to_watchlist(self, args: Mapping[str, Any]) -> str:
        denied = self._deny_personal_mutation_if_gated()
        if denied:
            return denied
        from projectionist.watchlist.plex_sync import push_pin_to_plex

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
        denied = self._deny_personal_mutation_if_gated()
        if denied:
            return denied
        from projectionist.watchlist.plex_sync import remove_pin_from_plex

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
        from projectionist.watchlist.curate import curate_watchlist

        user_id = self.user_id if self.settings.features.multi_user_enabled else None
        pins = self.db.list_watchlist_pins(user_id=user_id)
        return json.dumps(curate_watchlist(self.db, pins, limit=int(args.get("limit") or 12)))

    async def _tool_critique_watchlist(self, args: Mapping[str, Any]) -> str:
        from projectionist.watchlist.curate import critique_watchlist

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

