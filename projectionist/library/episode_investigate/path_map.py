"""Translate a Sonarr episode path to a file visible in this container.

Sonarr often reports ``/tv/Show/Season/file.mkv`` while this process sees a
different root (``tv_root``, a Plex library Location, or a host tree that is
already mounted). Investigate stills, runtime, OSHash, and Identify use the
resolved path. ``library_items`` stores size, not a filesystem path.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Iterable, List, Optional, Sequence

from projectionist.config_store import normalize_root_path

logger = logging.getLogger(__name__)

# Sonarr / Radarr namespaces this image bind-mounts read-write.
CONTAINER_MEDIA_ROOTS = (
    "/tv",
    "/movies",
)

# Tried only when the directory already exists in *this* container.
HOST_HINT_ROOTS = (
    "/mnt/user/data/media/tv",
    "/mnt/user/data/media/movies",
    "/mnt/user/media/tv",
    "/mnt/user/media/movies",
    "/data/media/tv",
    "/data/media/movies",
    "/data/tv",
    "/data/movies",
    "/media/tv",
    "/media/movies",
)

IsFileFn = Callable[[Path], bool]


def _clean_root(value: Any) -> str:
    return normalize_root_path(str(value or ""))


def _dedupe(paths: Iterable[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for raw in paths:
        cleaned = _clean_root(raw)
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        out.append(cleaned)
    return out


def _posix(path: str) -> str:
    return str(path or "").replace("\\", "/").strip()


def implicit_sonarr_prefix(path: str) -> str:
    """First path component (``/tv/Show/...`` → ``/tv``)."""
    text = _posix(path)
    if not text.startswith("/"):
        return ""
    parts = [part for part in text.split("/") if part]
    return f"/{parts[0]}" if parts else ""


def configured_remote_roots(settings: Any) -> List[str]:
    """Roots as Sonarr / settings may name them (prefix side)."""
    return _dedupe(
        (
            getattr(settings, "sonarr_root_folder", ""),
            getattr(settings, "tv_root", ""),
        )
    )


def configured_local_roots(settings: Any) -> List[str]:
    """Configured roots that might be visible in this container.

    Settings ``tv_root`` / ``movies_root`` are first-class (env
    ``PROJECTIONIST_TV_MEDIA`` / ``PROJECTIONIST_MOVIE_MEDIA``), then *arr
    folders, then the Sonarr/Radarr container namespaces.
    """
    return _dedupe(
        (
            getattr(settings, "tv_root", ""),
            getattr(settings, "movies_root", ""),
            getattr(settings, "sonarr_root_folder", ""),
            getattr(settings, "radarr_root_folder", ""),
            *CONTAINER_MEDIA_ROOTS,
        )
    )


def existing_host_hint_roots(*, is_dir: Optional[Callable[[Path], bool]] = None) -> List[str]:
    check = is_dir or (lambda path: Path(path).is_dir())
    return [root for root in HOST_HINT_ROOTS if check(Path(root))]


def matching_remote_prefixes(path: str, settings: Any) -> List[str]:
    """Sonarr-side prefixes to strip, longest first."""
    text = _posix(path)
    prefixes = list(configured_remote_roots(settings))
    implied = implicit_sonarr_prefix(text)
    if implied:
        prefixes.append(implied)
    matched = [prefix for prefix in _dedupe(prefixes) if _has_prefix(text, prefix)]
    matched.sort(key=len, reverse=True)
    return matched


def _has_prefix(path: str, root: str) -> bool:
    text = _posix(path)
    prefix = _clean_root(root)
    if not prefix:
        return False
    return text == prefix or text.startswith(prefix + "/")


def replace_root_prefix(path: str, old_root: str, new_root: str) -> Optional[str]:
    text = _posix(path)
    old = _clean_root(old_root)
    new = _clean_root(new_root)
    if not text or not old or not new or old == new:
        return None
    if text == old:
        return new
    if text.startswith(old + "/"):
        return new + text[len(old) :]
    return None


def candidate_media_paths(
    path: str,
    settings: Any,
    *,
    extra_roots: Sequence[str] = (),
    include_host_hints: bool = True,
) -> List[str]:
    """Exact path, then each Sonarr prefix rewritten onto each known local root."""
    text = _posix(path)
    if not text:
        return []
    targets = _dedupe(
        list(configured_local_roots(settings))
        + list(extra_roots)
        + (existing_host_hint_roots() if include_host_hints else [])
    )
    candidates = [text]
    for prefix in matching_remote_prefixes(text, settings):
        for target in targets:
            mapped = replace_root_prefix(text, prefix, target)
            if mapped:
                candidates.append(mapped)
    return _dedupe(candidates)


def resolve_visible_media_path(
    path: str,
    settings: Any,
    *,
    extra_roots: Sequence[str] = (),
    include_host_hints: bool = True,
    is_file: Optional[IsFileFn] = None,
) -> Optional[str]:
    """First candidate that exists as a file. None if nothing is visible."""
    check = is_file or (lambda candidate: Path(candidate).is_file())
    for candidate in candidate_media_paths(
        path,
        settings,
        extra_roots=extra_roots,
        include_host_hints=include_host_hints,
    ):
        try:
            if check(Path(candidate)):
                return candidate
        except OSError:
            continue
    return None


def plex_library_locations(settings: Any, *, section_type: str = "show") -> List[str]:
    """Plex ``Location`` paths for TV (or movie) sections. Empty if Plex is down."""
    url = str(getattr(settings, "plex_url", "") or "").strip()
    token = str(getattr(settings, "plex_token", "") or "").strip()
    if not url or not token:
        return []
    try:
        from projectionist.connectors.plex import PlexClient

        client = PlexClient(url, token, timeout=10)
        mapped = ""
        if section_type in {"show", "tv"}:
            mapped = str(getattr(settings, "plex_tv_section", "") or "").strip()
        elif section_type == "movie":
            mapped = str(getattr(settings, "plex_movie_section", "") or "").strip()
        preferred: List[str] = []
        others: List[str] = []
        wanted_types = {"show", "tv"} if section_type in {"show", "tv"} else {section_type}
        for section in client.list_sections():
            if section.type not in wanted_types:
                continue
            locs = [str(item) for item in (section.locations or []) if str(item).strip()]
            if mapped and (section.key == mapped or section.title == mapped):
                preferred.extend(locs)
            else:
                others.extend(locs)
        return _dedupe(preferred + others)
    except Exception as error:  # noqa: BLE001 — mapping is best-effort
        logger.info("investigate path map: plex locations unavailable: %s", error)
        return []


def discover_media_roots(settings: Any) -> List[str]:
    """Local roots for one Investigate job (settings + Plex TV locations)."""
    return _dedupe(list(configured_local_roots(settings)) + plex_library_locations(settings))


class TranslationLog:
    """One log line per job — not per episode file."""

    def __init__(self) -> None:
        self._emitted = False

    def emit(self, sonarr_path: str, resolved: Optional[str]) -> None:
        if self._emitted:
            return
        self._emitted = True
        source = _posix(sonarr_path)
        if resolved and resolved != source:
            logger.info("investigate path map: %s -> %s", source, resolved)
        elif not resolved:
            logger.info("investigate path map: no visible file for %s", source or "(empty)")
