"""Rewrite a Plex part path onto a path this container can read.

Owners map a Plex prefix (what Plex puts in ``Part.file``) to the mount
Projectionist sees. The longest matching prefix wins. A prefix matches a
directory boundary, so ``/data/media`` does not claim ``/data/media-extra``.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence

MAX_MAPPINGS = 32


class PathMapError(ValueError):
    """A path mapping the owner sent cannot be stored."""


def _posix(value: Any) -> str:
    text = str(value or "").replace("\\", "/").strip()
    if "\x00" in text:
        raise PathMapError("Path mappings cannot contain null bytes.")
    if text != "/":
        text = text.rstrip("/")
    return text


def _require_absolute(path: str, *, label: str) -> str:
    if not path.startswith("/"):
        raise PathMapError(f"The {label} path must be an absolute path.")
    if any(part == ".." for part in path.split("/")):
        raise PathMapError("Path mappings cannot contain ..")
    return path


def normalize_one(item: Any) -> dict[str, str]:
    if not isinstance(item, Mapping):
        raise PathMapError("A path mapping needs a Plex prefix and a container prefix.")
    plex = _require_absolute(
        _posix(item.get("plex_prefix") or item.get("from") or ""),
        label="Plex",
    )
    container = _require_absolute(
        _posix(item.get("container_prefix") or item.get("to") or ""),
        label="container",
    )
    if plex == container:
        raise PathMapError("The Plex path and the container path must differ.")
    return {"plex_prefix": plex, "container_prefix": container}


def normalize_mappings(items: Any) -> list[dict[str, str]]:
    if items is None:
        return []
    if not isinstance(items, list):
        raise PathMapError("Path mappings must be a list.")
    if len(items) > MAX_MAPPINGS:
        raise PathMapError(f"At most {MAX_MAPPINGS} path mappings.")
    return [normalize_one(item) for item in items]


def salvage_mappings(items: Any) -> list[dict[str, str]]:
    """Keep valid rows when settings.json holds a bad entry. Never raise."""
    if not isinstance(items, list):
        return []
    kept: list[dict[str, str]] = []
    for item in items[:MAX_MAPPINGS]:
        try:
            kept.append(normalize_one(item))
        except PathMapError:
            continue
    return kept


def map_plex_path(plex_path: str, mappings: Sequence[Mapping[str, Any]]) -> Optional[str]:
    """Return the container path for ``plex_path``, or None when no prefix matches."""
    try:
        text = _posix(plex_path)
    except PathMapError:
        return None
    if not text.startswith("/"):
        return None
    ranked = sorted(
        list(mappings or []),
        key=lambda item: len(_posix(item.get("plex_prefix") or "")),
        reverse=True,
    )
    for mapping in ranked:
        try:
            prefix = _require_absolute(_posix(mapping.get("plex_prefix") or ""), label="Plex")
            target = _require_absolute(
                _posix(mapping.get("container_prefix") or ""),
                label="container",
            )
        except PathMapError:
            continue
        if text == prefix:
            return target
        if text.startswith(prefix + "/"):
            return target + text[len(prefix) :]
    return None
