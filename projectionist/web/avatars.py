"""Local user avatar storage under DATA_DIR/avatars.

Plex thumb URLs are often brittle in browsers (tokenized / hotlink blocked).
We cache them at login when possible and also accept user uploads. Avatars are
served only through authenticated API endpoints — never via arbitrary paths.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_SAFE_USER_ID = re.compile(r"^[A-Za-z0-9_.:@-]{1,128}$")
_ALLOWED_CONTENT_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
_MAX_AVATAR_BYTES = 2 * 1024 * 1024  # 2 MiB
_LOCAL_AVATAR_API_PREFIX = "/api/auth/avatar/"


def data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", "/config"))


def avatars_dir(root: Optional[Path] = None) -> Path:
    path = (root or data_dir()) / "avatars"
    path.mkdir(parents=True, exist_ok=True)
    return path


def safe_user_id(user_id: str) -> str:
    cleaned = str(user_id or "").strip()
    if not _SAFE_USER_ID.fullmatch(cleaned):
        raise ValueError("Invalid user id")
    if ".." in cleaned or "/" in cleaned or "\\" in cleaned:
        raise ValueError("Invalid user id")
    return cleaned


def local_avatar_api_path(user_id: str) -> str:
    return f"{_LOCAL_AVATAR_API_PREFIX}{safe_user_id(user_id)}"


def is_local_avatar_url(url: Optional[str]) -> bool:
    return bool(url) and str(url).startswith(_LOCAL_AVATAR_API_PREFIX)


def find_local_avatar_file(user_id: str, *, root: Optional[Path] = None) -> Optional[Path]:
    uid = safe_user_id(user_id)
    base = avatars_dir(root)
    for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        candidate = base / f"{uid}{ext}"
        if candidate.is_file():
            # Resolve + ensure still under avatars dir (no symlink escape).
            resolved = candidate.resolve()
            if not str(resolved).startswith(str(base.resolve())):
                return None
            return resolved
    return None


def clear_local_avatar(user_id: str, *, root: Optional[Path] = None) -> None:
    uid = safe_user_id(user_id)
    base = avatars_dir(root)
    for path in base.glob(f"{uid}.*"):
        if path.is_file():
            try:
                path.unlink()
            except OSError:
                logger.debug("Could not remove avatar %s", path, exc_info=True)


def detect_avatar_extension(data: bytes, content_type: str = "") -> str:
    """Return a file extension for valid image bytes, or raise ValueError."""
    if len(data) > _MAX_AVATAR_BYTES:
        raise ValueError("Avatar must be 2MB or smaller")
    if len(data) < 32:
        raise ValueError("Avatar file is empty or too small")
    cleaned_type = (content_type or "").split(";")[0].strip().lower()
    ext = _ALLOWED_CONTENT_TYPES.get(cleaned_type)
    if ext:
        return ext
    # Sniff magic headers when browsers send octet-stream / omit type.
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"
    raise ValueError("Avatar must be a JPEG, PNG, WebP, or GIF image")


def save_avatar_bytes(
    user_id: str,
    data: bytes,
    content_type: str,
    *,
    root: Optional[Path] = None,
) -> str:
    """Persist avatar bytes; returns local API path for avatar_url storage."""
    ext = detect_avatar_extension(data, content_type)
    uid = safe_user_id(user_id)
    clear_local_avatar(uid, root=root)
    dest = avatars_dir(root) / f"{uid}{ext}"
    dest.write_bytes(data)
    return local_avatar_api_path(uid)


def media_type_for_avatar(path: Path) -> str:
    suffix = path.suffix.lower()
    mapping = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }
    return mapping.get(suffix, "application/octet-stream")


def cache_remote_avatar(
    user_id: str,
    remote_url: str,
    *,
    root: Optional[Path] = None,
    timeout: float = 8.0,
) -> Optional[str]:
    """Best-effort download of a remote (usually Plex) avatar into local storage."""
    url = str(remote_url or "").strip()
    if not url.startswith(("http://", "https://")):
        return None
    if find_local_avatar_file(user_id, root=root):
        # Preserve an existing upload / cache.
        return local_avatar_api_path(user_id)
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()
            content_type = response.headers.get("content-type") or ""
            return save_avatar_bytes(user_id, response.content, content_type, root=root)
    except Exception:
        logger.debug("Could not cache remote avatar for %s", user_id, exc_info=True)
        return None


def resolve_avatar_url(
    user_id: str,
    stored_url: Optional[str],
    *,
    root: Optional[Path] = None,
) -> Optional[str]:
    """Prefer a local avatar file when present; else return stored URL."""
    if find_local_avatar_file(user_id, root=root):
        return local_avatar_api_path(user_id)
    cleaned = str(stored_url or "").strip() or None
    return cleaned

