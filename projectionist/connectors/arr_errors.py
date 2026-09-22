"""Shared helpers for Radarr/Sonarr validation errors."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Mapping, Optional


class ArrTitleExistsError(RuntimeError):
    """Raised when a title is already present in Radarr or Sonarr."""

    def __init__(
        self,
        service: str,
        *,
        title: str = "",
        external_id: int = 0,
        arr_id: Optional[int] = None,
    ) -> None:
        self.service = service
        self.title = title
        self.external_id = external_id
        self.arr_id = arr_id
        label = title or f"ID {external_id}" if external_id else "This title"
        super().__init__(f'"{label}" is already in {service}')


class ArrTitleNotFoundError(RuntimeError):
    """Raised when a title cannot be found in Radarr or Sonarr for removal."""

    def __init__(
        self,
        service: str,
        *,
        title: str = "",
        external_id: int = 0,
        arr_id: Optional[int] = None,
    ) -> None:
        self.service = service
        self.title = title
        self.external_id = external_id
        self.arr_id = arr_id
        label = title or (f"ID {external_id}" if external_id else (f"Radarr id {arr_id}" if arr_id else "This title"))
        super().__init__(f'"{label}" is not in {service}')


class ArrPathConflictError(RuntimeError):
    """Raised when Radarr already owns the folder under a different identity."""

    def __init__(
        self,
        *,
        path: str = "",
        intended_title: str = "",
        intended_tmdb_id: int = 0,
        occupant_title: str = "",
        occupant_tmdb_id: int = 0,
        occupant_arr_id: Optional[int] = None,
    ) -> None:
        self.path = path
        self.intended_title = intended_title
        self.intended_tmdb_id = intended_tmdb_id
        self.occupant_title = occupant_title
        self.occupant_tmdb_id = occupant_tmdb_id
        self.occupant_arr_id = occupant_arr_id
        super().__init__(
            format_path_conflict_message(
                path=path,
                intended_title=intended_title,
                intended_tmdb_id=intended_tmdb_id,
                occupant_title=occupant_title,
                occupant_tmdb_id=occupant_tmdb_id,
            )
        )


@dataclass(frozen=True)
class RadarrAddClass:
    """Honest outcome of an add/register attempt."""

    kind: str  # already | path_conflict | error
    message: str
    folder_path: str = ""
    occupant_tmdb_id: int = 0
    occupant_title: str = ""
    occupant_arr_id: Optional[int] = None


def format_already_in_radarr_message(*, title: str = "", path: str = "") -> str:
    if path:
        return f"Already in Radarr at {path}"
    if title:
        return f"Already in Radarr ({title})"
    return "Already in Radarr"


def format_path_conflict_message(
    *,
    path: str = "",
    intended_title: str = "",
    intended_tmdb_id: int = 0,
    occupant_title: str = "",
    occupant_tmdb_id: int = 0,
) -> str:
    folder = path or "that folder"
    occupant = occupant_title or "a different Radarr movie"
    plex_bit = f"Plex tmdb {intended_tmdb_id}" if intended_tmdb_id else (
        f"Plex title {intended_title}" if intended_title else "Plex"
    )
    radarr_bit = occupant
    if occupant_tmdb_id:
        radarr_bit = f"{occupant} (tmdb {occupant_tmdb_id})"
    return (
        f"Path conflict: Radarr already has {radarr_bit} at {folder}. "
        f"{plex_bit} is a different identity — rematch in Plex or Radarr."
    )


def _extract_http_error_body(error: Exception) -> str:
    """Return the JSON/text payload, not the ``http://`` prefix of the URL."""
    message = str(error)
    for idx, char in enumerate(message):
        if char in "[{":
            return message[idx:]
    if ": " in message:
        return message.split(": ", 1)[-1]
    return message


def arr_exists_error_code(body: str, *, movie: bool = True) -> bool:
    code = "MovieExistsValidator" if movie else "SeriesExistsValidator"
    if code in body:
        return True
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return False
    if isinstance(data, list):
        return any(
            isinstance(item, dict) and item.get("errorCode") == code for item in data
        )
    if isinstance(data, dict):
        return data.get("errorCode") == code
    return False


def is_arr_exists_error(error: Exception, *, movie: bool = True) -> bool:
    if isinstance(error, ArrTitleExistsError):
        return True
    return arr_exists_error_code(_extract_http_error_body(error), movie=movie)


def is_arr_path_conflict_error(error: Exception) -> bool:
    if isinstance(error, ArrPathConflictError):
        return True
    body = _extract_http_error_body(error)
    if "MoviePathValidator" in body:
        return True
    lowered = body.lower()
    return "already configured for an existing movie" in lowered


def _validation_items(body: str) -> list[dict[str, Any]]:
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return []
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def folder_path_from_arr_error(error: Exception) -> str:
    body = _extract_http_error_body(error)
    for item in _validation_items(body):
        if str(item.get("errorCode") or "") != "MoviePathValidator":
            attempted = item.get("attemptedValue")
            placeholders = item.get("formattedMessagePlaceholderValues")
            if isinstance(placeholders, Mapping) and placeholders.get("path"):
                return str(placeholders.get("path") or "").strip()
            if attempted and isinstance(attempted, str) and attempted.startswith("/"):
                return attempted.strip()
            continue
        placeholders = item.get("formattedMessagePlaceholderValues")
        if isinstance(placeholders, Mapping) and placeholders.get("path"):
            return str(placeholders.get("path") or "").strip()
        attempted = item.get("attemptedValue")
        if isinstance(attempted, str) and attempted.strip():
            return attempted.strip()
        message = str(item.get("errorMessage") or "")
        quoted = re.search(r"Path ['\"]([^'\"]+)['\"]", message)
        if quoted:
            return quoted.group(1)
    quoted = re.search(r"Path ['\"]([^'\"]+)['\"]", body)
    if quoted:
        return quoted.group(1)
    attempted = re.search(r'"attemptedValue":\s*"([^"]+)"', body)
    if attempted:
        return attempted.group(1)
    return ""


def _parse_arr_error_payload(body: str) -> Optional[str]:
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return None
    if isinstance(data, dict):
        message = data.get("message") or data.get("error") or data.get("title")
        return str(message) if message else None
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                message = item.get("message") or item.get("errorMessage")
                if message:
                    return str(message)
    return None


def is_arr_not_found_error(error: Exception) -> bool:
    if isinstance(error, ArrTitleNotFoundError):
        return True
    body = _extract_http_error_body(error).lower()
    if "does not exist" in body:
        return True
    if '"statuscode": 404' in body.replace(" ", ""):
        return True
    return "http 404" in str(error).lower()


def _scrub_operator_copy(text: str) -> str:
    cleaned = str(text or "").strip()
    if "formattedMessagePlaceholderValues" in cleaned or '"errorCode"' in cleaned:
        parsed = _parse_arr_error_payload(_extract_http_error_body(RuntimeError(cleaned)))
        if parsed:
            return parsed.split("\n")[0].strip()
        return "Radarr rejected this title."
    first_line = cleaned.split("\n", 1)[0].strip()
    if first_line.lower().startswith("http ") and "{" in first_line:
        parsed = _parse_arr_error_payload(_extract_http_error_body(RuntimeError(first_line)))
        if parsed:
            return parsed.split("\n")[0].strip()
        return "Radarr rejected this title."
    if len(first_line) > 240:
        return first_line[:237] + "..."
    return first_line


def format_arr_http_error(error: Exception) -> str:
    if isinstance(error, ArrTitleExistsError):
        return format_already_in_radarr_message(title=error.title)
    if isinstance(error, ArrPathConflictError):
        return str(error)
    if isinstance(error, ArrTitleNotFoundError):
        return str(error)
    body = _extract_http_error_body(error).strip()
    for candidate in (body, body.split("\n", 1)[0].strip()):
        parsed = _parse_arr_error_payload(candidate)
        if parsed:
            return _scrub_operator_copy(parsed.split("\n")[0].strip())
    return _scrub_operator_copy(str(error))


def _occupant_fields(occupant: Any) -> tuple[int, str, Optional[int], str]:
    if occupant is None:
        return 0, "", None, ""
    tmdb_id = int(getattr(occupant, "tmdb_id", 0) or 0)
    title = str(getattr(occupant, "title", "") or "")
    arr_id = getattr(occupant, "id", None)
    folder = str(
        getattr(occupant, "folder_path", "")
        or getattr(occupant, "file_path", "")
        or ""
    )
    try:
        arr_id_int = int(arr_id) if arr_id is not None else None
    except (TypeError, ValueError):
        arr_id_int = None
    return tmdb_id, title, arr_id_int, folder


def classify_radarr_catalog(
    *,
    intended_tmdb_id: int,
    intended_title: str = "",
    intended_path: str = "",
    by_tmdb: Any = None,
    by_path: Any = None,
) -> Optional[RadarrAddClass]:
    """Classify a pre-POST catalog match. ``None`` means proceed to add."""
    if by_tmdb is not None:
        tmdb_id, title, arr_id, folder = _occupant_fields(by_tmdb)
        path = intended_path or folder
        return RadarrAddClass(
            kind="already",
            message=format_already_in_radarr_message(
                title=title or intended_title,
                path=path,
            ),
            folder_path=path,
            occupant_tmdb_id=tmdb_id or intended_tmdb_id,
            occupant_title=title or intended_title,
            occupant_arr_id=arr_id,
        )
    if by_path is None:
        return None
    tmdb_id, title, arr_id, folder = _occupant_fields(by_path)
    path = intended_path or folder
    if tmdb_id and intended_tmdb_id and tmdb_id == intended_tmdb_id:
        return RadarrAddClass(
            kind="already",
            message=format_already_in_radarr_message(
                title=title or intended_title,
                path=path,
            ),
            folder_path=path,
            occupant_tmdb_id=tmdb_id,
            occupant_title=title or intended_title,
            occupant_arr_id=arr_id,
        )
    return RadarrAddClass(
        kind="path_conflict",
        message=format_path_conflict_message(
            path=path,
            intended_title=intended_title,
            intended_tmdb_id=intended_tmdb_id,
            occupant_title=title,
            occupant_tmdb_id=tmdb_id,
        ),
        folder_path=path,
        occupant_tmdb_id=tmdb_id,
        occupant_title=title,
        occupant_arr_id=arr_id,
    )


def classify_radarr_add_error(
    error: Exception,
    *,
    intended_tmdb_id: int = 0,
    intended_title: str = "",
    occupant: Any = None,
) -> RadarrAddClass:
    if isinstance(error, ArrTitleExistsError):
        return RadarrAddClass(
            kind="already",
            message=format_already_in_radarr_message(title=error.title or intended_title),
            occupant_tmdb_id=int(error.external_id or intended_tmdb_id or 0),
            occupant_title=error.title or intended_title,
            occupant_arr_id=error.arr_id,
        )
    if isinstance(error, ArrPathConflictError):
        return RadarrAddClass(
            kind="path_conflict",
            message=str(error),
            folder_path=error.path,
            occupant_tmdb_id=error.occupant_tmdb_id,
            occupant_title=error.occupant_title,
            occupant_arr_id=error.occupant_arr_id,
        )
    body = _extract_http_error_body(error)
    path = folder_path_from_arr_error(error)
    occ_tmdb, occ_title, occ_id, occ_folder = _occupant_fields(occupant)
    folder = path or occ_folder
    if arr_exists_error_code(body, movie=True):
        return RadarrAddClass(
            kind="already",
            message=format_already_in_radarr_message(
                title=occ_title or intended_title,
                path=folder,
            ),
            folder_path=folder,
            occupant_tmdb_id=occ_tmdb or intended_tmdb_id,
            occupant_title=occ_title or intended_title,
            occupant_arr_id=occ_id,
        )
    if is_arr_path_conflict_error(error):
        if occ_tmdb and intended_tmdb_id and occ_tmdb == intended_tmdb_id:
            return RadarrAddClass(
                kind="already",
                message=format_already_in_radarr_message(
                    title=occ_title or intended_title,
                    path=folder,
                ),
                folder_path=folder,
                occupant_tmdb_id=occ_tmdb,
                occupant_title=occ_title or intended_title,
                occupant_arr_id=occ_id,
            )
        return RadarrAddClass(
            kind="path_conflict",
            message=format_path_conflict_message(
                path=folder,
                intended_title=intended_title,
                intended_tmdb_id=intended_tmdb_id,
                occupant_title=occ_title,
                occupant_tmdb_id=occ_tmdb,
            ),
            folder_path=folder,
            occupant_tmdb_id=occ_tmdb,
            occupant_title=occ_title,
            occupant_arr_id=occ_id,
        )
    return RadarrAddClass(kind="error", message=format_arr_http_error(error))


def intended_movie_folder(*, root_folder: str, title: str, year: Any = None, lookup_path: str = "") -> str:
    cleaned_lookup = str(lookup_path or "").strip()
    if cleaned_lookup:
        return cleaned_lookup.rstrip("/")
    root = str(root_folder or "").rstrip("/")
    label = str(title or "").strip()
    if year not in (None, ""):
        label = f"{label} ({year})"
    if not root or not label:
        return label
    return f"{root}/{label}"
