"""Shared helpers for Radarr/Sonarr validation errors."""

from __future__ import annotations

import json
from typing import Optional


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


def _extract_http_error_body(error: Exception) -> str:
    message = str(error)
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


def format_arr_http_error(error: Exception) -> str:
    if isinstance(error, ArrTitleExistsError):
        return str(error)
    if isinstance(error, ArrTitleNotFoundError):
        return str(error)
    message = str(error)
    if ": " in message:
        body = message.split(": ", 1)[-1].strip()
        for candidate in (body, body.split("\n", 1)[0].strip()):
            parsed = _parse_arr_error_payload(candidate)
            if parsed:
                return parsed.split("\n")[0].strip()
    first_line = message.split("\n", 1)[0].strip()
    if len(first_line) > 240:
        return first_line[:237] + "..."
    return first_line
