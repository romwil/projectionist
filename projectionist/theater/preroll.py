"""Host preroll bumpers for Play movies + Live tune-in.

Media lives on the host (Automat default ``/mnt/user/data/media/preroll``),
bind-mounted into the container at ``/preroll``. Each browser session picks
independently — there is no shared preroll clock across clients.
"""

from __future__ import annotations

import hashlib
import logging
import mimetypes
import os
import random
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

logger = logging.getLogger(__name__)

_VIDEO_EXTS = frozenset({".mp4", ".m4v", ".webm", ".mov", ".mkv", ".avi"})
_AUDIO_EXTS = frozenset({".mp3", ".m4a", ".aac", ".ogg", ".wav", ".flac"})
_SAFE_ID = re.compile(r"^[a-f0-9]{8,64}$")

# Container + common host-path fallbacks when the bind is missing in tests.
_DEFAULT_CANDIDATES = (
    "/preroll",
    "/mnt/user/data/media/preroll",
    "/data/media/preroll",
)


def preroll_roots_from_env(environ: Optional[Any] = None) -> List[Path]:
    """Resolve searchable preroll roots (env first, then defaults that exist)."""
    env = environ if environ is not None else os.environ
    roots: List[Path] = []
    raw = str(env.get("PROJECTIONIST_PREROLL_MEDIA") or "").strip()
    if raw:
        roots.append(Path(raw))
    for candidate in _DEFAULT_CANDIDATES:
        path = Path(candidate)
        if path not in roots:
            roots.append(path)
    return roots


def resolve_preroll_root(environ: Optional[Any] = None) -> Optional[Path]:
    for root in preroll_roots_from_env(environ):
        try:
            if root.is_dir():
                return root.resolve()
        except OSError:
            continue
    return None


def _iter_media_files(root: Path, *, exts: frozenset) -> Iterable[Path]:
    try:
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            if path.name.startswith("."):
                continue
            if path.suffix.lower() in exts:
                yield path
    except OSError as exc:
        logger.warning("preroll scan failed under %s: %s", root, exc)


def asset_id_for_path(path: Path, *, root: Path) -> str:
    try:
        rel = str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        rel = str(path.resolve())
    return hashlib.sha256(rel.encode("utf-8")).hexdigest()[:24]


def list_preroll_videos(root: Optional[Path] = None) -> List[Dict[str, Any]]:
    base = root or resolve_preroll_root()
    if base is None:
        return []
    out: List[Dict[str, Any]] = []
    for path in _iter_media_files(base, exts=_VIDEO_EXTS):
        aid = asset_id_for_path(path, root=base)
        out.append(
            {
                "id": aid,
                "path": path,
                "title": path.stem.replace("_", " ").replace("-", " ").strip() or "Preroll",
                "media_type": "video",
                "content_type": mimetypes.guess_type(str(path))[0] or "video/mp4",
            }
        )
    return out


def list_preroll_audio(root: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Audio under preroll (muzak / weather beds), including weather/ subfolders."""
    base = root or resolve_preroll_root()
    if base is None:
        return []
    out: List[Dict[str, Any]] = []
    for path in _iter_media_files(base, exts=_AUDIO_EXTS):
        aid = asset_id_for_path(path, root=base)
        out.append(
            {
                "id": aid,
                "path": path,
                "title": path.stem.replace("_", " ").replace("-", " ").strip() or "Bed",
                "media_type": "audio",
                "content_type": mimetypes.guess_type(str(path))[0] or "audio/mpeg",
            }
        )
    return out


def pick_preroll(
    *,
    context: str = "movie",
    root: Optional[Path] = None,
    rng: Optional[random.Random] = None,
    exclude_ids: Optional[Sequence[str]] = None,
) -> Optional[Dict[str, Any]]:
    """Pick one video bumper for this client (independent of other viewers)."""
    _ = context  # reserved for future movie-vs-live folders
    items = list_preroll_videos(root)
    if not items:
        return None
    exclude = {str(x) for x in (exclude_ids or []) if x}
    pool = [i for i in items if i["id"] not in exclude] or items
    picker = rng if rng is not None else random.Random()
    chosen = picker.choice(pool)
    return {
        "id": chosen["id"],
        "title": chosen["title"],
        "media_type": "video",
        "url": f"/api/preroll/asset/{chosen['id']}",
        "content_type": chosen["content_type"],
    }


def resolve_asset(asset_id: str, *, root: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    aid = str(asset_id or "").strip().lower()
    if not _SAFE_ID.match(aid):
        return None
    base = root or resolve_preroll_root()
    if base is None:
        return None
    for collection in (list_preroll_videos(base), list_preroll_audio(base)):
        for item in collection:
            if item["id"] == aid:
                return item
    return None
