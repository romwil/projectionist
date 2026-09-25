"""Same-show apply: Plex-proper rename, Sonarr remap, Plex refresh, undo."""

from __future__ import annotations

import logging
import os
import shutil
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence
from urllib.parse import quote

from projectionist.connectors.http import request_json
from projectionist.library.episode_investigate.filenames import plex_proper_name
from projectionist.library.episode_investigate.fusion import same_show_proposal

logger = logging.getLogger(__name__)

RenameFn = Callable[[str, str], None]
ExistsFn = Callable[[str], bool]


def plex_proper_path(show_title: str, proposed: Mapping[str, Any], current_path: str) -> str:
    current = Path(current_path)
    ext = current.suffix or ".mkv"
    name = plex_proper_name(
        show_title,
        int(proposed.get("season") or 0),
        int(proposed.get("episode") or 0),
        str(proposed.get("title") or "Episode"),
        ext=ext,
    )
    return str(current.with_name(name))


def apply_rows(
    settings: Any,
    show: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    selected_ids: Sequence[str],
    *,
    rename: RenameFn = os.rename,
    exists: ExistsFn = os.path.exists,
    sonarr_remap: Optional[Callable[..., Dict[str, Any]]] = None,
    plex_refresh: Optional[Callable[[Any], None]] = None,
) -> Dict[str, Any]:
    wanted = {str(item) for item in selected_ids}
    apply_id = uuid.uuid4().hex[:12]
    changes: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    failed: List[Dict[str, Any]] = []
    for row in rows:
        file_id = str(row.get("id") or "")
        if file_id not in wanted:
            continue
        proposed = row.get("proposed") if isinstance(row.get("proposed"), Mapping) else {}
        if not same_show_proposal(show, proposed):
            skipped.append(
                {
                    "id": file_id,
                    "reason": "Apply this sprint is same-show only.",
                }
            )
            continue
        current_path = str(row.get("path") or "")
        if not current_path:
            failed.append({"id": file_id, "error": "Missing file path"})
            continue
        target_path = plex_proper_path(str(show.get("title") or "Show"), proposed, current_path)
        try:
            if current_path != target_path:
                if exists(target_path):
                    raise RuntimeError("A file already uses the Plex-proper name")
                if exists(current_path):
                    rename(current_path, target_path)
            remap_fn = sonarr_remap or remap_sonarr_episode_file
            remap_fn(
                settings,
                file_id=int(row.get("file_id") or file_id),
                series_id=int(row.get("series_id") or 0),
                from_path=current_path,
                to_path=target_path,
                target_episode_id=int(proposed.get("sonarr_episode_id") or 0) or None,
            )
            changes.append(
                {
                    "id": file_id,
                    "file_id": row.get("file_id"),
                    "series_id": row.get("series_id"),
                    "from_path": current_path,
                    "to_path": target_path,
                    "from_episode_id": (row.get("sonarr") or {}).get("episode_id"),
                    "to_episode_id": proposed.get("sonarr_episode_id"),
                    "from_season": (row.get("sonarr") or {}).get("season"),
                    "from_episode": (row.get("sonarr") or {}).get("episode"),
                    "to_season": proposed.get("season"),
                    "to_episode": proposed.get("episode"),
                }
            )
        except Exception as error:  # noqa: BLE001
            logger.warning("investigate apply failed file=%s error=%s", file_id, error)
            failed.append({"id": file_id, "error": str(error)[:400]})
    if changes:
        refresh = plex_refresh or refresh_plex_tv
        try:
            refresh(settings)
        except Exception as error:  # noqa: BLE001
            logger.info("plex refresh after investigate apply: %s", error)
    return {
        "apply_id": apply_id,
        "applied": len(changes),
        "skipped": len(skipped),
        "failed": len(failed),
        "changes": changes,
        "skipped_rows": skipped,
        "failed_rows": failed,
        "created_at": time.time(),
    }


def undo_apply(
    settings: Any,
    record: Mapping[str, Any],
    *,
    rename: RenameFn = os.rename,
    exists: ExistsFn = os.path.exists,
    sonarr_remap: Optional[Callable[..., Dict[str, Any]]] = None,
    plex_refresh: Optional[Callable[[Any], None]] = None,
) -> Dict[str, Any]:
    restored = 0
    failed: List[Dict[str, Any]] = []
    remap_fn = sonarr_remap or remap_sonarr_episode_file
    for change in record.get("changes") or []:
        if not isinstance(change, Mapping):
            continue
        to_path = str(change.get("to_path") or "")
        from_path = str(change.get("from_path") or "")
        try:
            if to_path and from_path and to_path != from_path and exists(to_path):
                if exists(from_path):
                    raise RuntimeError("Original path is occupied — cannot undo rename")
                rename(to_path, from_path)
            remap_fn(
                settings,
                file_id=int(change.get("file_id") or 0),
                series_id=int(change.get("series_id") or 0),
                from_path=to_path or from_path,
                to_path=from_path or to_path,
                target_episode_id=int(change.get("from_episode_id") or 0) or None,
            )
            restored += 1
        except Exception as error:  # noqa: BLE001
            failed.append({"id": change.get("id"), "error": str(error)[:400]})
    if restored:
        refresh = plex_refresh or refresh_plex_tv
        try:
            refresh(settings)
        except Exception as error:  # noqa: BLE001
            logger.info("plex refresh after investigate undo: %s", error)
    return {
        "apply_id": str(record.get("apply_id") or ""),
        "restored": restored,
        "failed": len(failed),
        "failed_rows": failed,
    }


def remap_sonarr_episode_file(
    settings: Any,
    *,
    file_id: int,
    series_id: int,
    from_path: str,
    to_path: str,
    target_episode_id: Optional[int],
) -> Dict[str, Any]:
    """Unlink the file record (keep disk) and ManualImport onto the target episode."""
    base = str(getattr(settings, "sonarr_url", "") or "").rstrip("/")
    key = str(getattr(settings, "sonarr_api_key", "") or "").strip()
    if not base or not key:
        return {"ok": False, "error": "Sonarr is not configured"}
    headers = {"X-Api-Key": key}
    if file_id:
        try:
            request_json(
                f"{base}/api/v3/episodefile/{int(file_id)}?deleteFile=false",
                method="DELETE",
                headers=headers,
                timeout=30,
            )
        except Exception as error:  # noqa: BLE001
            logger.info("sonarr unlink episodefile=%s: %s", file_id, error)
    if series_id and target_episode_id and to_path:
        folder = str(Path(to_path).parent)
        quality: Dict[str, Any] = {"quality": {"id": 1}, "revision": {"version": 1, "real": 0}}
        languages: List[Dict[str, Any]] = [{"id": 1}]
        try:
            candidates = request_json(
                f"{base}/api/v3/manualimport?folder={quote(folder)}",
                headers=headers,
                timeout=30,
            )
            if isinstance(candidates, list):
                match = next(
                    (
                        row
                        for row in candidates
                        if isinstance(row, Mapping)
                        and str(row.get("path") or "") in {to_path, from_path}
                    ),
                    None,
                )
                if isinstance(match, Mapping):
                    if isinstance(match.get("quality"), Mapping):
                        quality = dict(match["quality"])
                    if isinstance(match.get("languages"), list) and match["languages"]:
                        languages = list(match["languages"])
        except Exception as error:  # noqa: BLE001
            logger.info("sonarr manualimport probe: %s", error)
        try:
            request_json(
                f"{base}/api/v3/command",
                method="POST",
                headers=headers,
                body={
                    "name": "ManualImport",
                    "files": [
                        {
                            "path": to_path,
                            "folderName": folder,
                            "seriesId": int(series_id),
                            "episodeIds": [int(target_episode_id)],
                            "quality": quality,
                            "languages": languages,
                            "indexerFlags": 0,
                            "releaseGroup": "",
                        }
                    ],
                    "importMode": "auto",
                },
                timeout=60,
            )
            return {"ok": True, "mode": "manualimport"}
        except Exception as error:  # noqa: BLE001
            logger.info("sonarr manualimport failed: %s", error)
    if series_id:
        request_json(
            f"{base}/api/v3/command",
            method="POST",
            headers=headers,
            body={"name": "RescanSeries", "seriesId": int(series_id)},
            timeout=30,
        )
        return {"ok": True, "mode": "rescan"}
    return {"ok": False, "error": "No Sonarr series id"}


def refresh_plex_tv(settings: Any) -> None:
    url = str(getattr(settings, "plex_url", "") or "").strip()
    token = str(getattr(settings, "plex_token", "") or "").strip()
    section = str(getattr(settings, "plex_tv_section", "") or "").strip()
    if not url or not token or not section:
        return
    from projectionist.connectors.plex import PlexClient

    PlexClient(url, token).refresh_section(section)


def copy_still(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
