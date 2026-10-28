"""Acquire-domain agent tools (Radarr / Sonarr / Seerr / confirm)."""

from __future__ import annotations

from projectionist.agent.tools._helpers import *  # noqa: F401, F403

from projectionist.agent.tools.confirmed import (
    check_radarr_already_exists,
    check_sonarr_already_exists,
    execute_confirmed_action,
    mark_in_radarr,
    mark_in_sonarr,
    resolve_arr_removal_target,
    resolve_radarr_search_for_movie,
)

class AcquireToolsMixin:
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
        explicit_search = args.get("search_for_movie")
        if explicit_search is None and "register_existing" in args:
            explicit_search = not bool(args.get("register_existing"))
        search_for_movie = resolve_radarr_search_for_movie(
            self.db,
            tmdb_id,
            explicit=None if explicit_search is None else bool(explicit_search),
        )
        token = uuid.uuid4().hex
        payload = {
            "action": "add_radarr",
            "tmdb_id": tmdb_id,
            "title": str(args.get("title") or ""),
            "search_for_movie": search_for_movie,
        }
        self.db.save_pending_action(token, "add_radarr", payload, user_id=self.user_id)
        self._register_pending_token(token, "add_radarr")
        mode = "register existing on disk" if not search_for_movie else "search for download"
        return json.dumps(
            {
                "confirmation_token": token,
                "search_for_movie": search_for_movie,
                "message": (
                    f"Awaiting user confirmation to add to Radarr ({mode}). "
                    f"{_PENDING_CONFIRM_HINT}"
                ),
            }
        )

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
        return json.dumps(
            {
                "confirmation_token": token,
                "message": f"Awaiting user confirmation to add to Sonarr. {_PENDING_CONFIRM_HINT}",
            }
        )

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
                "message": f"Awaiting user confirmation to request in Seerr. {_PENDING_CONFIRM_HINT}",
            }
        )

    async def _tool_propose_acquire_path(self, args: Mapping[str, Any]) -> str:
        from projectionist.acquire import build_acquire_path

        path = build_acquire_path(
            self.db,
            self.settings,
            title=str(args.get("title") or ""),
            media_type=str(args.get("media_type") or "movie"),
            tmdb_id=int(args["tmdb_id"]) if args.get("tmdb_id") is not None else None,
            tvdb_id=int(args["tvdb_id"]) if args.get("tvdb_id") is not None else None,
            user_id=self.user_id,
            seerr_user_id=self.seerr_user_id,
        )
        token = path.get("confirmation_token")
        if token:
            self._register_pending_token(str(token), "request_seerr")
        return json.dumps(path)

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
        # Full removes should stay off acquisition lists; default matches *arr UI.
        add_exclusion = (
            True
            if "add_exclusion" not in args
            else bool(args.get("add_exclusion"))
        )
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
            "add_exclusion": add_exclusion,
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
                "message": f"Awaiting user confirmation to remove. {_PENDING_CONFIRM_HINT}",
                "arr_id": resolved["arr_id"],
            }
        )

    async def _tool_mark_bad_media(self, args: Mapping[str, Any]) -> str:
        from projectionist.library.bad_media import BadMediaError, mark_bad_media

        try:
            result = mark_bad_media(
                self.db,
                self.settings,
                rating_key=str(args.get("rating_key") or "") or None,
                tmdb_id=int(args["tmdb_id"]) if args.get("tmdb_id") is not None else None,
                tvdb_id=int(args["tvdb_id"]) if args.get("tvdb_id") is not None else None,
                media_type=str(args.get("media_type") or "") or None,
                episode_rating_key=str(args.get("episode_rating_key") or "") or None,
                season_number=int(args["season_number"]) if args.get("season_number") is not None else None,
                episode_number=int(args["episode_number"]) if args.get("episode_number") is not None else None,
                note=str(args.get("note") or ""),
            )
        except BadMediaError as error:
            return json.dumps({"error": str(error)})
        except RuntimeError as error:
            from projectionist.connectors.arr_errors import format_arr_http_error

            return json.dumps({"error": format_arr_http_error(error)})
        return json.dumps(
            {
                "ok": True,
                "title": result.get("title"),
                "action": result.get("action"),
                "files_removed": result.get("files_removed", 0),
                "add_exclusion": False,
                "message": (
                    "Asked Radarr/Sonarr to replace the bad file. "
                    "No import exclusion was added — the title stays wanted."
                ),
            }
        )

    async def _tool_confirm_pending_action(self, args: Mapping[str, Any]) -> str:
        """Redeem or cancel a pending confirmation token after the user affirms."""
        token = str(
            args.get("confirmation_token") or args.get("token") or args.get("pending_token") or ""
        ).strip()
        if not token:
            return json.dumps(
                {
                    "error": (
                        "confirmation_token is required. Use the token returned by the "
                        "propose tool (add_to_radarr, create_plex_collection, etc.)."
                    )
                }
            )
        confirmed = args.get("confirmed", True)
        if isinstance(confirmed, str):
            confirmed = confirmed.strip().lower() not in {"0", "false", "no", "cancel"}
        else:
            confirmed = bool(confirmed)
        if not confirmed:
            try:
                popped = self.db.pop_pending_action(token, user_id=self.user_id)
            except Exception as error:  # noqa: BLE001
                return json.dumps({"error": str(error)})
            return json.dumps({"cancelled": True, "found": popped is not None})
        try:
            result = await execute_confirmed_action(
                self.db, self.settings, token, user_id=self.user_id
            )
            return json.dumps({"ok": True, **result})
        except Exception as error:  # noqa: BLE001
            return json.dumps({"error": str(error), "ok": False})

