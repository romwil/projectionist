"""Owner full-remove: *arr (files + exclusion) → Plex metadata → Projectionist index.

Prefer Radarr/Sonarr delete APIs for disk cleanup and list-exclusion. Plex metadata
delete is cleanup after files are gone — it does not remove media from disk.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Mapping, Optional, Sequence

from projectionist.agent.tools import resolve_arr_removal_target
from projectionist.config_store import Settings, plex_configuration_error
from projectionist.connectors.arr_errors import (
    ArrTitleNotFoundError,
    format_arr_http_error,
    is_arr_not_found_error,
)
from projectionist.connectors.plex import PlexClient
from projectionist.connectors.radarr import RadarrClient
from projectionist.connectors.sonarr import SonarrClient
from projectionist.library.db import Database
from projectionist.scheduler.tasks.purge_candidates import drop_cached_purge_keys

logger = logging.getLogger(__name__)

LIBRARY_DELETE_MODES = frozenset({"index", "full"})


def normalize_library_delete_mode(value: Any) -> str:
    mode = str(value or "index").strip().lower() or "index"
    if mode not in LIBRARY_DELETE_MODES:
        raise ValueError('mode must be "index" or "full"')
    return mode


def _row_value(row: Any, key: str) -> Any:
    if row is None:
        return None
    if isinstance(row, Mapping):
        return row.get(key)
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return None


def _optional_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _media_type_for_arr(media_type: str) -> str:
    """Map library media_type to resolve_arr_removal_target's movie-vs-Sonarr split."""
    return "movie" if str(media_type or "").strip().lower() == "movie" else "show"


def _remove_from_arr(
    db: Database,
    settings: Settings,
    *,
    media_type: str,
    title: str,
    tmdb_id: Optional[int],
    tvdb_id: Optional[int],
) -> Dict[str, Any]:
    arr_media = _media_type_for_arr(media_type)
    service = "Radarr" if arr_media == "movie" else "Sonarr"
    if arr_media == "movie":
        if not settings.radarr_url or not settings.radarr_api_key:
            raise RuntimeError("Radarr is not configured — cannot delete media files or prevent re-add")
    elif not settings.sonarr_url or not settings.sonarr_api_key:
        raise RuntimeError("Sonarr is not configured — cannot delete media files or prevent re-add")

    try:
        resolved = resolve_arr_removal_target(
            settings,
            media_type=arr_media,
            tmdb_id=tmdb_id if arr_media == "movie" else None,
            tvdb_id=tvdb_id if arr_media != "movie" else None,
            title=title,
        )
    except ArrTitleNotFoundError:
        raise
    except RuntimeError:
        raise

    arr_id = int(resolved["arr_id"])
    removed_title = str(resolved.get("title") or title)
    try:
        if arr_media == "movie":
            RadarrClient(settings.radarr_url, settings.radarr_api_key).delete_movie(
                arr_id,
                delete_files=True,
                add_exclusion=True,
            )
            if resolved.get("tmdb_id"):
                db.set_arr_presence(tmdb_id=int(resolved["tmdb_id"]), in_radarr=False)
        else:
            SonarrClient(settings.sonarr_url, settings.sonarr_api_key).delete_series(
                arr_id,
                delete_files=True,
                add_exclusion=True,
            )
            if resolved.get("tvdb_id"):
                db.set_arr_presence(tvdb_id=int(resolved["tvdb_id"]), in_sonarr=False)
    except RuntimeError as error:
        if is_arr_not_found_error(error):
            raise ArrTitleNotFoundError(
                service,
                title=removed_title,
                arr_id=arr_id,
            ) from error
        raise RuntimeError(format_arr_http_error(error)) from error

    return {
        "service": service.lower(),
        "removed": True,
        "arr_id": arr_id,
        "title": removed_title,
        "delete_files": True,
        "add_exclusion": True,
    }


def _remove_from_plex(settings: Settings, rating_key: str) -> Dict[str, Any]:
    config_error = plex_configuration_error(settings)
    if config_error:
        return {"removed": False, "skipped": True, "reason": "plex_not_configured"}
    try:
        PlexClient(settings.plex_url, settings.plex_token).delete_metadata(rating_key)
    except Exception as error:  # noqa: BLE001 — surface to owner as plex step result
        logger.warning("Plex metadata delete failed for %s: %s", rating_key, error)
        return {"removed": False, "skipped": False, "reason": "plex_error", "error": str(error)}
    return {"removed": True, "skipped": False}


def full_remove_library_items(
    db: Database,
    settings: Settings,
    rating_keys: Sequence[str],
) -> Dict[str, Any]:
    """Fully remove titles: *arr files+exclusion, Plex metadata, then index rows.

    Per-title: if *arr cannot remove the title, the Projectionist index row is
    left intact and the title is reported under ``errors``. Plex cleanup failures
    after a successful *arr delete still allow the index delete (files are gone).
    """
    keys = [str(key).strip() for key in rating_keys if str(key).strip()]
    results: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    deleted_keys: List[str] = []

    for key in keys:
        row = db.library_item_by_rating_key(key)
        title = str(_row_value(row, "title") or key)
        if row is None:
            errors.append(
                {
                    "rating_key": key,
                    "title": title,
                    "error": "Title not found in the Projectionist library index",
                    "index_deleted": False,
                }
            )
            continue

        media_type = str(_row_value(row, "media_type") or "movie")
        tmdb_id = _optional_int(_row_value(row, "tmdb_id"))
        tvdb_id = _optional_int(_row_value(row, "tvdb_id"))
        entry: Dict[str, Any] = {
            "rating_key": key,
            "title": title,
            "media_type": media_type,
            "ok": False,
            "index_deleted": False,
        }

        try:
            entry["arr"] = _remove_from_arr(
                db,
                settings,
                media_type=media_type,
                title=title,
                tmdb_id=tmdb_id,
                tvdb_id=tvdb_id,
            )
        except ArrTitleNotFoundError as error:
            errors.append(
                {
                    "rating_key": key,
                    "title": title,
                    "error": str(error),
                    "index_deleted": False,
                }
            )
            continue
        except RuntimeError as error:
            errors.append(
                {
                    "rating_key": key,
                    "title": title,
                    "error": str(error),
                    "index_deleted": False,
                }
            )
            continue

        entry["plex"] = _remove_from_plex(settings, key)
        removed = db.delete_library_items_by_rating_keys([key])
        entry["index_deleted"] = removed > 0
        entry["ok"] = removed > 0
        if removed > 0:
            deleted_keys.append(key)
        results.append(entry)

    if deleted_keys:
        drop_cached_purge_keys(db, deleted_keys)

    return {
        "mode": "full",
        "deleted": len(deleted_keys),
        "results": results,
        "errors": errors,
    }
