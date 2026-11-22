"""Media source: where is the file, what streams does it have, what is its identity.

Plex is the first source. A local path that is already visible in this
container needs no mapping. An explicit mapping that does not resolve to a
readable file does not fall through to the Plex path — that path belongs to
another machine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Protocol, Sequence

from projectionist.engine.pathmap import map_plex_path
from projectionist.engine.probe import ProbeResult, probe_file


def plex_lookup_reason(error: BaseException) -> str:
    """Name a failed Plex lookup. A timeout is not an empty Media/Part list."""
    text = str(error or "").lower()
    if "timeout" in text or "timed out" in text or "circuit open" in text:
        return "Plex timed out before it reported a file for this title"
    return "Plex did not report a file for this title"


PathLookup = Callable[[str], Sequence[str]]
IsFileFn = Callable[[str], bool]
ProbeFn = Callable[..., Any]
IdentityLookup = Callable[[str], dict[str, Any]]

# ENG-013. The engine does not transcode the picture. It asks the media
# source, records why, and leaves playback on that source's own path.
SOURCE_TRANSCODE_PLAN = "source-transcode"
SOURCE_REASONS = frozenset({"codec", "level", "bit_depth"})


def source_transcode_reason(answer: str) -> str:
    """The planner's video answer, as codec, level, or bit depth.

    An answer that is not one of those is empty. The offer then records
    ``codec``, which is the bucket the playability report already uses.
    """
    text = str(answer or "").lower()
    if "not in profile" in text:
        return "codec"
    if "bit" in text and "above" in text:
        return "bit_depth"
    if "level is above" in text:
        return "level"
    return ""


def source_transcode_offer(*, provider: str, reason: str, source_reason: str) -> dict[str, Any]:
    """One shape every source returns. This server does not play the result.

    ``playable`` stays false so a member keeps the source's existing playback.
    A source cannot opt this server into starting ffmpeg by setting it true.
    """
    kind = source_reason if source_reason in SOURCE_REASONS else "codec"
    return {
        "plan": SOURCE_TRANSCODE_PLAN,
        "reason": str(reason or ""),
        "source_reason": kind,
        "provider": str(provider or "plex"),
        "playable": False,
    }


class SourceTranscode(Protocol):
    """A media source that can be asked to transcode a picture it already has."""

    def source_transcode(self, *, reason: str, source_reason: str) -> Mapping[str, Any]:
        """Record that this source will transcode. Do not start ffmpeg."""


def normalize_source_transcode(
    offer: Mapping[str, Any],
    *,
    reason: str,
    source_reason: str,
) -> dict[str, Any]:
    """Force the public plan name. The source names itself; the tier does not change."""
    return source_transcode_offer(
        provider=str(offer.get("provider") or "plex"),
        reason=str(offer.get("reason") or reason),
        source_reason=str(offer.get("source_reason") or source_reason),
    )


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
        self.probe: ProbeFn = probe if probe is not None else probe_file
        self.identity_lookup = identity_lookup or (lambda _key: {})

    def source_transcode(self, *, reason: str, source_reason: str) -> dict[str, Any]:
        """Plex transcodes on its own playback path.

        Projectionist does not start ffmpeg and does not read the file again.
        A later source answers this same method with its own provider name.
        """
        return source_transcode_offer(provider="plex", reason=reason, source_reason=source_reason)

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
        except Exception as error:  # noqa: BLE001 — Plex failures become an unread file
            return MediaAsset(
                rating_key=key,
                readable=False,
                reason=plex_lookup_reason(error),
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
