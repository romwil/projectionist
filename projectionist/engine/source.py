"""Media source: where is the file, what streams does it have, what is its identity.

Plex is the first source. A local path that is already visible in this
container needs no mapping. An explicit mapping that does not resolve to a
readable file does not fall through to the Plex path — that path belongs to
another machine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

from projectionist.engine.pathmap import map_plex_path
from projectionist.engine.probe import ProbeResult, probe_file

PathLookup = Callable[[str], Sequence[str]]
IsFileFn = Callable[[str], bool]
ProbeFn = Callable[..., ProbeResult]
IdentityLookup = Callable[[str], dict[str, Any]]


@dataclass
class MediaAsset:
    rating_key: str
    source_path: str = ""
    local_path: Optional[str] = None
    readable: bool = False
    reason: str = ""
    identity: dict[str, Any] = field(default_factory=dict)
    probe: Optional[ProbeResult] = None


def public_media(asset: MediaAsset) -> dict[str, Any]:
    """Client view. File paths and source URLs stay on the server."""
    probe = asset.probe
    identity = asset.identity or {}
    tmdb = identity.get("tmdb_id")
    try:
        tmdb_id = int(tmdb) if tmdb not in (None, "") else None
    except (TypeError, ValueError):
        tmdb_id = None
    return {
        "rating_key": asset.rating_key,
        "readable": bool(asset.readable),
        "probed": probe is not None,
        "reason": asset.reason or "",
        "container": probe.container if probe else "",
        "duration_s": probe.duration_s if probe else 0,
        "identity": {
            "tmdb_id": tmdb_id,
            "imdb_id": str(identity.get("imdb_id") or ""),
        },
        "streams": probe.as_public()["streams"] if probe else [],
    }


class PlexMediaSource:
    def __init__(
        self,
        *,
        mappings: Sequence[dict[str, str]],
        path_lookup: PathLookup,
        is_file: Optional[IsFileFn] = None,
        probe: Optional[ProbeFn] = None,
        identity_lookup: Optional[IdentityLookup] = None,
    ) -> None:
        self.mappings = list(mappings or [])
        self.path_lookup = path_lookup
        self.is_file = is_file or (lambda candidate: Path(candidate).is_file())
        self.probe = probe or probe_file
        self.identity_lookup = identity_lookup or (lambda _key: {})

    def _exists(self, path: str) -> bool:
        try:
            return bool(path) and bool(self.is_file(path))
        except OSError:
            return False

    def locate(self, rating_key: str, **probe_kwargs: Any) -> MediaAsset:
        key = str(rating_key or "").strip()
        try:
            identity = dict(self.identity_lookup(key) or {})
        except Exception:  # noqa: BLE001 — identity is optional
            identity = {}
        try:
            paths = [str(item).strip() for item in (self.path_lookup(key) or []) if str(item).strip()]
        except Exception:  # noqa: BLE001 — Plex failures become an unread file
            return MediaAsset(
                rating_key=key,
                readable=False,
                reason="Plex did not report a file for this title",
                identity=identity,
            )
        if not paths:
            return MediaAsset(
                rating_key=key,
                readable=False,
                reason="Plex did not report a file for this title",
                identity=identity,
            )
        source_path = paths[0]
        mapped = map_plex_path(source_path, self.mappings)
        if mapped is not None:
            local = mapped if self._exists(mapped) else None
            if local is None:
                return MediaAsset(
                    rating_key=key,
                    source_path=source_path,
                    local_path=None,
                    readable=False,
                    reason="No path mapping for this file",
                    identity=identity,
                )
        else:
            local = source_path if self._exists(source_path) else None
            if local is None:
                return MediaAsset(
                    rating_key=key,
                    source_path=source_path,
                    local_path=None,
                    readable=False,
                    reason="No path mapping for this file",
                    identity=identity,
                )
        probe: Optional[ProbeResult] = None
        reason = ""
        try:
            probe = self.probe(local, **probe_kwargs) if probe_kwargs else self.probe(local)
        except Exception:  # noqa: BLE001 — a readable file can still fail to probe
            reason = "Could not read streams for this file"
        return MediaAsset(
            rating_key=key,
            source_path=source_path,
            local_path=local,
            readable=True,
            reason=reason,
            identity=identity,
            probe=probe,
        )
