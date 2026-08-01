"""Owner full-remove: *arr (files + exclusion) → Plex metadata → Projectionist index.

Prefer Radarr/Sonarr delete APIs for disk cleanup and list-exclusion. Plex metadata
delete is cleanup after files are gone — it does not remove media from disk.

Before DELETE, snapshot file paths / folders / sizes from *arr GET responses so the
API can return a removal summary and application logs can record per-title detail.
"""

from __future__ import annotations

import logging
from pathlib import PurePosixPath, PureWindowsPath
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

logger = logging.getLogger("projectionist.library.full_remove")

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


def _as_nonneg_int(value: Any) -> int:
    """Parse sizes from *arr JSON; ignore bools / mock objects / garbage."""
    if isinstance(value, bool) or value is None:
        return 0
    if isinstance(value, int):
        return max(0, value)
    if isinstance(value, float):
        return max(0, int(value))
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return 0
        try:
            return max(0, int(float(text)))
        except (TypeError, ValueError):
            return 0
    return 0


def _as_path(value: Any) -> str:
    """Only accept real string paths from *arr payloads (not mock reprs)."""
    if not isinstance(value, str):
        return ""
    return value.strip()


def _as_dict(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, dict) else {}


def _media_type_for_arr(media_type: str) -> str:
    """Map library media_type to resolve_arr_removal_target's movie-vs-Sonarr split."""
    return "movie" if str(media_type or "").strip().lower() == "movie" else "show"


def _path_parent(path: str) -> str:
    text = str(path or "").strip()
    if not text:
        return ""
    pure = PureWindowsPath(text) if ("\\" in text and "/" not in text) else PurePosixPath(text)
    parent = str(pure.parent)
    if parent in {"", ".", "/"}:
        return ""
    return parent.rstrip("/\\")


def _normalize_folder(path: str) -> str:
    text = str(path or "").strip().rstrip("/\\")
    return text


def join_arr_path(root_path: str, relative_path: str) -> str:
    """Join *arr root + relativePath when absolute path is missing."""
    root = _normalize_folder(root_path or "")
    rel = _as_path(relative_path).lstrip("/\\")
    if not root or not rel:
        return ""
    if "\\" in root and "/" not in root:
        return f"{root}\\{rel.replace('/', '\\')}"
    return f"{root}/{rel.replace('\\', '/')}"


def resolve_arr_file_path(
    row: Mapping[str, Any],
    *,
    root_path: str = "",
) -> str:
    """Prefer absolute path; fall back to root + relativePath."""
    data = _as_dict(row)
    path = _as_path(data.get("path"))
    if path:
        return path
    return join_arr_path(root_path, _as_path(data.get("relativePath") or data.get("relative_path")))


def infer_removed_folders(
    file_paths: Sequence[str],
    *,
    root_path: Optional[str] = None,
) -> List[str]:
    """Infer folders removed with the files from known paths only (no FS walks).

    Includes the *arr-reported title root (movie/series folder) when present, plus
    each file's immediate parent directory.
    """
    folders: set[str] = set()
    root = _normalize_folder(root_path or "")
    if root:
        folders.add(root)
    for raw in file_paths:
        parent = _normalize_folder(_path_parent(str(raw or "")))
        if parent:
            folders.add(parent)
    return sorted(folders)


def aggregate_removal_totals(results: Sequence[Mapping[str, Any]]) -> Dict[str, int]:
    """Aggregate per-title removal summaries into API ``totals``."""
    files = 0
    folders = 0
    bytes_freed = 0
    for entry in results:
        files += len(entry.get("files") or [])
        folders += len(entry.get("folders") or [])
        try:
            bytes_freed += int(entry.get("bytes_freed") or 0)
        except (TypeError, ValueError):
            pass
    return {
        "files": files,
        "folders": folders,
        "bytes_freed": max(0, bytes_freed),
    }


def apply_library_bytes_fallback(
    snapshot: Mapping[str, Any],
    *,
    library_bytes: int = 0,
) -> Dict[str, Any]:
    """Enrich a snapshot with library size / honesty fields when *arr is sparse."""
    files = list(snapshot.get("files") or [])
    folders = list(snapshot.get("folders") or [])
    bytes_freed = _as_nonneg_int(snapshot.get("bytes_freed"))
    bytes_source = str(snapshot.get("bytes_source") or "")
    note = str(snapshot.get("note") or "").strip()

    if bytes_freed > 0 and not bytes_source:
        bytes_source = "arr"
    elif bytes_freed <= 0 and library_bytes > 0 and (files or folders):
        bytes_freed = int(library_bytes)
        bytes_source = "library_estimate"
        if not note and not files and folders:
            note = (
                "*arr reported the title folder but no episode/file list. "
                "Disk files were still targeted for deletion with the folder; "
                "byte count is from the Projectionist library index."
            )
    elif bytes_freed <= 0 and not files and folders:
        bytes_source = bytes_source or "unknown"
        if not note:
            note = (
                "*arr reported the title folder but no episode file list or size. "
                "Disk files may have been removed with the folder; byte count unavailable."
            )
    elif not bytes_source:
        bytes_source = "arr" if bytes_freed > 0 else "unknown"

    return {
        "files": files,
        "folders": folders,
        "bytes_freed": bytes_freed,
        "bytes_source": bytes_source,
        "note": note,
    }


def snapshot_radarr_movie(payload: Mapping[str, Any]) -> Dict[str, Any]:
    """Build a removal snapshot from a Radarr movie GET payload."""
    data = _as_dict(payload)
    movie_file = _as_dict(data.get("movieFile"))
    root_path = _as_path(data.get("path"))
    files: List[str] = []
    file_path = resolve_arr_file_path(movie_file, root_path=root_path)
    file_size = _as_nonneg_int(movie_file.get("size"))
    if file_path:
        files.append(file_path)
    size_on_disk = _as_nonneg_int(data.get("sizeOnDisk"))
    bytes_freed = size_on_disk if size_on_disk > 0 else file_size
    folders = infer_removed_folders(files, root_path=root_path or None)
    return apply_library_bytes_fallback(
        {
            "files": files,
            "folders": folders,
            "bytes_freed": bytes_freed,
            "bytes_source": "arr" if bytes_freed > 0 else "unknown",
            "note": "",
        }
    )


def snapshot_sonarr_series(
    series_payload: Mapping[str, Any],
    episode_files: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Build a removal snapshot from Sonarr series + episodeFile list."""
    series = _as_dict(series_payload)
    root_path = _as_path(series.get("path"))
    files: List[str] = []
    bytes_from_files = 0
    for item in episode_files:
        row = _as_dict(item)
        path = resolve_arr_file_path(row, root_path=root_path)
        if not path:
            continue
        files.append(path)
        bytes_from_files += _as_nonneg_int(row.get("size"))
    stats = _as_dict(series.get("statistics"))
    size_on_disk = _as_nonneg_int(stats.get("sizeOnDisk"))
    if size_on_disk <= 0:
        size_on_disk = _as_nonneg_int(series.get("sizeOnDisk"))
    bytes_freed = size_on_disk if size_on_disk > 0 else bytes_from_files
    folders = infer_removed_folders(files, root_path=root_path or None)
    note = ""
    if not files and folders:
        note = (
            "Sonarr reported the series folder but no episode file paths. "
            "deleteFiles still targets that folder."
        )
    return apply_library_bytes_fallback(
        {
            "files": files,
            "folders": folders,
            "bytes_freed": bytes_freed,
            "bytes_source": "arr" if bytes_freed > 0 else "unknown",
            "note": note,
        }
    )


def _empty_snapshot() -> Dict[str, Any]:
    return {
        "files": [],
        "folders": [],
        "bytes_freed": 0,
        "bytes_source": "unknown",
        "note": "",
    }


def _snapshot_arr_before_delete(
    settings: Settings,
    *,
    arr_media: str,
    arr_id: int,
) -> Dict[str, Any]:
    """GET *arr details before DELETE so paths survive after the title is gone."""
    try:
        if arr_media == "movie":
            client = RadarrClient(settings.radarr_url, settings.radarr_api_key)
            payload = client.movie_by_id(arr_id)
            if not payload:
                return _empty_snapshot()
            return snapshot_radarr_movie(payload)
        client = SonarrClient(settings.sonarr_url, settings.sonarr_api_key)
        series = client.series_by_id(arr_id)
        if not series:
            return _empty_snapshot()
        episode_files = client.episode_files(arr_id)
        return snapshot_sonarr_series(series, episode_files)
    except Exception as error:  # noqa: BLE001 — snapshot is best-effort; delete still proceeds
        logger.warning(
            "full_remove snapshot failed arr_media=%s arr_id=%s error=%s",
            arr_media,
            arr_id,
            error,
        )
        return _empty_snapshot()


def _log_title_removal(
    *,
    title: str,
    rating_key: str,
    media_type: str,
    files: Sequence[str],
    folders: Sequence[str],
    bytes_freed: int,
) -> None:
    logger.info(
        "full_remove title=%r rating_key=%s media_type=%s files=%d folders=%d "
        "bytes_freed=%d file_paths=%s folder_paths=%s",
        title,
        rating_key,
        media_type,
        len(files),
        len(folders),
        int(bytes_freed or 0),
        list(files),
        list(folders),
    )


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
    snapshot = _snapshot_arr_before_delete(settings, arr_media=arr_media, arr_id=arr_id)

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

    db.record_acquisition_exclusion(
        media_type=arr_media if arr_media == "movie" else "show",
        title=removed_title,
        tmdb_id=int(resolved["tmdb_id"]) if resolved.get("tmdb_id") is not None else tmdb_id,
        tvdb_id=int(resolved["tvdb_id"]) if resolved.get("tvdb_id") is not None else tvdb_id,
        source="full_remove",
    )

    return {
        "service": service.lower(),
        "removed": True,
        "arr_id": arr_id,
        "title": removed_title,
        "delete_files": True,
        "add_exclusion": True,
        "files": list(snapshot.get("files") or []),
        "folders": list(snapshot.get("folders") or []),
        "bytes_freed": int(snapshot.get("bytes_freed") or 0),
        "bytes_source": str(snapshot.get("bytes_source") or "unknown"),
        "note": str(snapshot.get("note") or ""),
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

    Successful results include ``files``, ``folders``, and ``bytes_freed`` snapshotted
    from *arr before DELETE. Aggregate ``totals`` sums those fields across results.
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
        library_bytes = _as_nonneg_int(_row_value(row, "file_size"))
        entry: Dict[str, Any] = {
            "rating_key": key,
            "title": title,
            "media_type": media_type,
            "ok": False,
            "index_deleted": False,
            "files": [],
            "folders": [],
            "bytes_freed": 0,
            "bytes_source": "unknown",
            "note": "",
        }

        try:
            arr_result = _remove_from_arr(
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

        snapshot = apply_library_bytes_fallback(
            {
                "files": list(arr_result.pop("files", []) or []),
                "folders": list(arr_result.pop("folders", []) or []),
                "bytes_freed": int(arr_result.pop("bytes_freed", 0) or 0),
                "bytes_source": str(arr_result.pop("bytes_source", "") or ""),
                "note": str(arr_result.pop("note", "") or ""),
            },
            library_bytes=library_bytes,
        )
        files = list(snapshot.get("files") or [])
        folders = list(snapshot.get("folders") or [])
        bytes_freed = int(snapshot.get("bytes_freed") or 0)
        entry["arr"] = arr_result
        entry["files"] = files
        entry["folders"] = folders
        entry["bytes_freed"] = bytes_freed
        entry["bytes_source"] = str(snapshot.get("bytes_source") or "unknown")
        entry["note"] = str(snapshot.get("note") or "")

        entry["plex"] = _remove_from_plex(settings, key)
        removed = db.delete_library_items_by_rating_keys([key])
        entry["index_deleted"] = removed > 0
        entry["ok"] = removed > 0
        if removed > 0:
            deleted_keys.append(key)
            _log_title_removal(
                title=title,
                rating_key=key,
                media_type=media_type,
                files=files,
                folders=folders,
                bytes_freed=bytes_freed,
            )
        results.append(entry)

    if deleted_keys:
        drop_cached_purge_keys(db, deleted_keys)

    return {
        "mode": "full",
        "deleted": len(deleted_keys),
        "results": results,
        "errors": errors,
        "totals": aggregate_removal_totals(results),
    }
