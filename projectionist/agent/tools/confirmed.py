"""Confirmed *arr / Seerr / Plex-collection side effects."""

from __future__ import annotations

from projectionist.agent.tools._helpers import *  # noqa: F401, F403

def mark_in_radarr(db: Database, tmdb_id: int, *, title: str = "", session_id: Optional[str] = None) -> None:
    db.set_arr_presence(tmdb_id=tmdb_id, in_radarr=True)
    db.record_arr_queue(
        media_type="movie",
        source="radarr",
        tmdb_id=tmdb_id,
        title=title,
        session_id=session_id,
    )

def resolve_radarr_search_for_movie(
    db: Database,
    tmdb_id: int,
    *,
    explicit: Optional[bool] = None,
) -> bool:
    """Return whether Radarr should search for a download on add.

    Owned-not-in-Radarr (library row present, in_radarr false) defaults to register-existing
    (search_for_movie=False). Explicit tool/API values always win. Missing TMDB library match
    keeps the download-search default.
    """
    if explicit is not None:
        return bool(explicit)
    row = db.library_item_by_tmdb(int(tmdb_id), "movie")
    if row is None:
        return True
    if int(row["in_radarr"] or 0):
        return True
    return False

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

def _restore_pending_action(
    db: Database,
    token: str,
    payload: Mapping[str, Any],
    *,
    user_id: Optional[str],
) -> None:
    """Re-queue a popped proposal after a failed side effect (best effort)."""
    try:
        db.save_pending_action(token, str(payload.get("action") or ""), dict(payload), user_id=user_id)
    except Exception:  # noqa: BLE001
        logger.warning("Could not restore pending action after failure", exc_info=True)

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
        if db.is_acquisition_excluded(media_type="movie", tmdb_id=tmdb_id):
            raise RuntimeError(
                f"{title or 'This title'} was removed with an acquisition exclusion "
                "and will not be re-added"
            )
        try:
            search_for_movie = bool(payload.get("search_for_movie", True))
            if "search_for_movie" not in payload:
                search_for_movie = resolve_radarr_search_for_movie(db, tmdb_id)
            result = client.add_movie(
                tmdb_id,
                root_folder=resolve_radarr_root_folder(settings),
                quality_profile_id=settings.radarr_quality_profile_id,
                search_for_movie=search_for_movie,
            )
        except ArrTitleExistsError as error:
            mark_in_radarr(db, tmdb_id, title=title or error.title)
            return _already_exists_response(action, error)
        mark_in_radarr(db, tmdb_id, title=title)
        return {"action": action, "result": result, "search_for_movie": search_for_movie}
    if action == "add_sonarr":
        config_error = sonarr_add_configuration_error(settings)
        if config_error:
            raise RuntimeError(config_error)
        client = SonarrClient(settings.sonarr_url, settings.sonarr_api_key)
        tvdb_id = int(payload["tvdb_id"])
        title = str(payload.get("title") or "")
        if db.is_acquisition_excluded(media_type="show", tvdb_id=tvdb_id):
            raise RuntimeError(
                f"{title or 'This title'} was removed with an acquisition exclusion "
                "and will not be re-added"
            )
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
        excluded = False
        if media_type == "movie":
            excluded = db.is_acquisition_excluded(media_type="movie", tmdb_id=tmdb_id)
        elif tvdb_id is not None and db.is_acquisition_excluded(
            media_type="show", tvdb_id=int(tvdb_id)
        ):
            excluded = True
        elif db.is_acquisition_excluded(media_type="show", tmdb_id=tmdb_id):
            excluded = True
        if excluded:
            raise RuntimeError(
                f"{title or 'This title'} was removed with an acquisition exclusion "
                "and will not be re-requested. Clear the exclusion first if you want it back."
            )
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
        add_exclusion = bool(payload.get("add_exclusion"))
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
                    arr_id, delete_files=delete_files, add_exclusion=add_exclusion
                )
                if resolved.get("tmdb_id"):
                    db.set_arr_presence(tmdb_id=int(resolved["tmdb_id"]), in_radarr=False)
            else:
                SonarrClient(settings.sonarr_url, settings.sonarr_api_key).delete_series(
                    arr_id, delete_files=delete_files, add_exclusion=add_exclusion
                )
                if resolved.get("tvdb_id"):
                    db.set_arr_presence(tvdb_id=int(resolved["tvdb_id"]), in_sonarr=False)
        except RuntimeError as error:
            from projectionist.connectors.arr_errors import format_arr_http_error, is_arr_not_found_error

            if is_arr_not_found_error(error):
                raise ArrTitleNotFoundError(
                    "Radarr" if media_type == "movie" else "Sonarr",
                    title=removed_title,
                    arr_id=arr_id,
                ) from error
            raise RuntimeError(format_arr_http_error(error)) from error
        if add_exclusion:
            db.record_acquisition_exclusion(
                media_type="movie" if media_type == "movie" else "show",
                title=removed_title,
                tmdb_id=int(resolved["tmdb_id"]) if resolved.get("tmdb_id") is not None else None,
                tvdb_id=int(resolved["tvdb_id"]) if resolved.get("tvdb_id") is not None else None,
                source="remove_arr",
            )
        return {
            "action": action,
            "removed": True,
            "result": {"title": removed_title, "arr_id": arr_id},
        }
    if action == "create_plex_collection":
        from projectionist.connectors.plex import PlexClient
        from projectionist.connectors.plex_collections import (
            apply_ephemeral_title_prefix,
            create_collection,
        )
        from projectionist.library.db import (
            DEFAULT_EPHEMERAL_TTL_HOURS,
            EPHEMERAL_COLLECTION_PREFIX,
        )

        config_error = plex_collections_configuration_error(settings)
        if config_error:
            raise RuntimeError(config_error)
        client = PlexClient(settings.plex_url, settings.plex_token)
        # Agent / movie-night shelves are ephemeral: prefix + TTL registry.
        titled = apply_ephemeral_title_prefix(
            str(payload["title"]),
            prefix=EPHEMERAL_COLLECTION_PREFIX,
        )
        try:
            collection = create_collection(
                client,
                section_id=str(payload["section_id"]),
                title=titled,
                media_type=str(payload["media_type"]),
                rating_keys=list(payload.get("rating_keys") or []),
            )
        except Exception as error:
            # Nothing was confirmed as created: keep the proposal redeemable so
            # "try again" works instead of "Invalid or expired confirmation token".
            _restore_pending_action(db, token, payload, user_id=user_id)
            raise RuntimeError(
                f"Plex collection '{titled}' was not created: {error}. "
                "The proposal is still pending — confirm again to retry."
            ) from error
        ttl_hours = int(
            getattr(settings, "ephemeral_collection_ttl_hours", None)
            or DEFAULT_EPHEMERAL_TTL_HOURS
        )
        warning = None
        try:
            db.record_ephemeral_plex_collection(
                plex_rating_key=collection.rating_key,
                section_id=collection.section_id,
                title=collection.title,
                media_type=collection.media_type,
                ttl_hours=ttl_hours,
                created_by_user_id=user_id,
            )
        except Exception:  # noqa: BLE001 — Plex write already succeeded; never report failure
            logger.exception(
                "Plex collection %s created but TTL registry write failed",
                collection.rating_key,
            )
            warning = (
                "Plex collection was created, but Projectionist could not register it "
                "for automatic cleanup."
            )
        result = {
            "rating_key": collection.rating_key,
            "title": collection.title,
            "section_id": collection.section_id,
            "ephemeral": warning is None,
            "ttl_hours": ttl_hours,
            # Explicit scope so the agent never reports this as a Projectionist
            # collection/course — it exists only as a Plex collection.
            "scope": "plex_only",
            "projectionist_collection": False,
            "note": (
                "Created in Plex only. It is not a Projectionist collection or course; "
                "use create_list (publish=true; list_kind=course for a course) for that."
            ),
        }
        if warning:
            result["warning"] = warning
        return {"action": action, "result": result}
    if action == "add_to_plex_collection":
        from projectionist.connectors.plex import PlexClient
        from projectionist.connectors.plex_collections import add_items_to_collection, find_collection_by_title

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
                _restore_pending_action(db, token, payload, user_id=user_id)
                raise RuntimeError(
                    "Plex collection not found — check the title or pass collection_rating_key. "
                    "The proposal is still pending."
                )
            collection_key = match.rating_key
        try:
            add_items_to_collection(client, collection_key, list(payload.get("rating_keys") or []))
        except Exception as error:
            _restore_pending_action(db, token, payload, user_id=user_id)
            raise RuntimeError(
                f"Titles were not added to the Plex collection: {error}. "
                "The proposal is still pending — confirm again to retry."
            ) from error
        return {"action": action, "result": {"collection_rating_key": collection_key, "added": True}}
    raise RuntimeError(f"Unknown action {action}")
