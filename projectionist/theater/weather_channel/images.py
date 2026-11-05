"""Server-side copies of radar, satellite, and webcam images.

Browsers load map frames from Projectionist, not from the map hosts, so a
viewer's address never reaches them and many viewers share one fetch.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Dict, Optional

from projectionist.theater.weather_channel.http import Fetcher, WeatherFetchError, default_fetch, host_allowed

_TYPES = {b"\x89PNG": ("png", "image/png"), b"\xff\xd8\xff": ("jpg", "image/jpeg"), b"GIF8": ("gif", "image/gif"), b"RIFF": ("webp", "image/webp")}
MAX_AGE_S = 3 * 3600


@dataclass
class StoredImage:
    image_id: str
    path: Path
    content_type: str
    fetched_at: float
    last_modified: str = ""


def image_id_for(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]


def _sniff(body: bytes) -> Optional[tuple]:
    for magic, kind in _TYPES.items():
        if body.startswith(magic):
            return kind
    return None


class ImageStore:
    def __init__(self, data_dir: Path) -> None:
        self.root = data_dir / "weather" / "maps"
        self._index: Dict[str, StoredImage] = {}

    def put(self, url: str, *, fetch: Optional[Fetcher] = None, version: str = "") -> StoredImage:
        """Fetch once per URL. A fixed URL whose picture changes (satellite, webcam) passes ``version``."""
        if not host_allowed(url):
            raise WeatherFetchError(f"Image host is not listed: {url}")
        image_id = image_id_for(f"{url}#{version}" if version else url)
        known = self._index.get(image_id)
        if known and known.path.is_file():
            return known
        result = (fetch or default_fetch)(url, headers={"Accept": "image/*"})
        kind = _sniff(result.body)
        if kind is None:
            raise WeatherFetchError(f"Not an image: {url}")
        ext, content_type = kind
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / f"{image_id}.{ext}"
        tmp = path.with_suffix(f".{ext}.part")
        tmp.write_bytes(result.body)
        tmp.replace(path)
        last_modified = ""
        raw = (result.headers or {}).get("last-modified", "")
        if raw:
            try:
                last_modified = parsedate_to_datetime(raw).isoformat()
            except (TypeError, ValueError):
                last_modified = ""
        stored = StoredImage(image_id, path, content_type, time.time(), last_modified)
        self._index[image_id] = stored
        return stored

    def get(self, image_id: str) -> Optional[StoredImage]:
        stored = self._index.get(str(image_id or ""))
        if stored and stored.path.is_file():
            return stored
        return None

    def prune(self, *, now: Optional[float] = None) -> int:
        cutoff = (now or time.time()) - MAX_AGE_S
        removed = 0
        for image_id, stored in list(self._index.items()):
            if stored.fetched_at < cutoff:
                self._index.pop(image_id, None)
                try:
                    stored.path.unlink()
                    removed += 1
                except FileNotFoundError:
                    pass
        return removed
