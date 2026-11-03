"""Acquire-domain agent tools (Radarr / Sonarr / Seerr / confirm)."""

from __future__ import annotations

from projectionist.agent.tools._helpers import (
    Any,
    ArrTitleNotFoundError,
    Dict,
    List,
    Mapping,
    RadarrClient,
    SeerrClient,
    SonarrClient,
    _PENDING_CONFIRM_HINT,
    _seerr_search_item_to_tool_item,
    json,
    radarr_add_configuration_error,
    resolve_radarr_root_folder,
    resolve_sonarr_root_folder,
    seerr_configuration_error,
    sonarr_add_configuration_error,
    uuid,
    validate_arr_root_folder,
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

class AcquireToolsMixin:
    async def _autoconfirm_member_add(self, token: str, service: str) -> str:
        """Run a member's add now; the owner turned on add-without-confirm for them."""
        try:
            outcome = await execute_confirmed_action(
                self.db,
                self.settings,
                token,
                user_id=self.user_id,
                actor_is_owner=False,
                actor_is_youth=False,
                actor_autoconfirms_adds=True,
            )
        except PermissionError as error:
            return json.dumps({"error": str(error), "code": "agent_tool_not_permitted"})
        except Exception as error:  # noqa: BLE001
            return json.dumps({"error": f"{service} add failed: {error}"})
        if outcome.get("already_exists"):
            return json.dumps(outcome)
        return json.dumps(
            {
                **outcome,
                "message": (
                    f"Added to {service}. The owner lets this account add without their "
                    "confirm, so there is nothing to confirm."
                ),
            }
        )

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
        if self._autoconfirms_adds():
            return await self._autoconfirm_member_add(token, "Radarr")
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
        if self._autoconfirms_adds():
            return await self._autoconfirm_member_add(token, "Sonarr")
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
        """Propose a bad-file replacement; the owner confirms it in the UI."""
        payload: Dict[str, Any] = {
            "action": "mark_bad_media",
            "rating_key": str(args.get("rating_key") or "") or None,
            "tmdb_id": int(args["tmdb_id"]) if args.get("tmdb_id") is not None else None,
            "tvdb_id": int(args["tvdb_id"]) if args.get("tvdb_id") is not None else None,
            "media_type": str(args.get("media_type") or "") or None,
            "episode_rating_key": str(args.get("episode_rating_key") or "") or None,
            "season_number": int(args["season_number"]) if args.get("season_number") is not None else None,
            "episode_number": int(args["episode_number"]) if args.get("episode_number") is not None else None,
            "note": str(args.get("note") or ""),
            "title": str(args.get("title") or ""),
        }
        if not any(payload.get(key) for key in ("rating_key", "tmdb_id", "tvdb_id", "episode_rating_key")):
            return json.dumps({"error": "rating_key, tmdb_id, or tvdb_id is required"})
        token = uuid.uuid4().hex
        self.db.save_pending_action(token, "mark_bad_media", payload, user_id=self.user_id)
        self._register_pending_token(token, "mark_bad_media")
        return json.dumps(
            {
                "confirmation_token": token,
                "add_exclusion": False,
                "message": (
                    "Awaiting confirmation to ask Radarr/Sonarr to replace the bad file. "
                    f"{_PENDING_CONFIRM_HINT}"
                ),
            }
        )

    async def _tool_confirm_pending_action(self, args: Mapping[str, Any]) -> str:
        """Cancel a pending token. Redeeming is a user action (POST /api/actions/confirm)."""
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
        return json.dumps(
            {
                "ok": False,
                "code": "confirm_requires_user",
                "error": (
                    "Confirmation happens in the app, not in chat. Ask the user to press "
                    "Confirm on the proposal card."
                ),
            }
        )
