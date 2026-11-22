"""Fixture media source for the automated playback test.

Set ``PROJECTIONIST_FIXTURE_MEDIA_DIR`` to a directory that contains
``catalog.json`` and the generated clips. This process then locates those
files itself. It does not call Plex, and it is not a household media source.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from dataclasses import asdict
from pathlib import Path
from typing import Any, Optional

from projectionist.config_store import Settings, load_merged_settings, save_settings
from projectionist.engine.probe import ProbeResult, probe_file
from projectionist.engine.source import MediaAsset, ProbeFn, source_transcode_offer
from projectionist.library.subtitle_cache import cache_path

logger = logging.getLogger(__name__)

FIXTURE_ENV = "PROJECTIONIST_FIXTURE_MEDIA_DIR"
_PROVIDER = "fixture"


class FixtureMediaError(RuntimeError):
    """The fixture directory was requested and cannot be used."""


def fixture_root() -> Optional[Path]:
    """The fixture directory, or None when this process is a normal server."""
    raw = os.environ.get(FIXTURE_ENV, "").strip()
    if not raw:
        return None
    return Path(raw).expanduser()


def try_fixture_media_source(*, probe: Optional[ProbeFn] = None):
    """The fixture source, or None when the env var is unset.

    A set env var that does not point at a catalog is an error. The server
    must not fall through to Plex after a fixture run was requested.
    """
    root = fixture_root()
    if root is None:
        return None
    catalog = root / "catalog.json"
    if not root.is_dir() or not catalog.is_file():
        raise FixtureMediaError(
            f"{FIXTURE_ENV} is set, but catalog.json is not in that directory"
        )
    return FixtureMediaSource(root, probe=probe)


class FixtureMediaSource:
    """Titles named by ``catalog.json``. Files stay inside the fixture directory."""

    def __init__(self, root: Path, *, probe: Optional[ProbeFn] = None) -> None:
        self.root = Path(root)
        self.probe: ProbeFn = probe if probe is not None else probe_file
        self._titles = _load_catalog(self.root)

    def source_transcode(self, *, reason: str, source_reason: str) -> dict[str, Any]:
        """Record the tier. This source does not transcode, and it is not Plex."""
        return source_transcode_offer(
            provider=_PROVIDER,
            reason=reason,
            source_reason=source_reason,
        )

    def locate(self, rating_key: str, **probe_kwargs: Any) -> MediaAsset:
        key = str(rating_key or "").strip()
        entry = self._titles.get(key)
        if entry is None:
            return MediaAsset(
                rating_key=key,
                readable=False,
                reason="Fixture media has no file for this title",
            )
        local = _file_inside(self.root, str(entry.get("file") or ""))
        if local is None or not local.is_file():
            return MediaAsset(
                rating_key=key,
                readable=False,
                reason="Fixture file is missing",
            )
        probe: Optional[ProbeResult] = None
        reason = ""
        try:
            probe = self.probe(str(local), **probe_kwargs) if probe_kwargs else self.probe(str(local))
        except Exception:  # noqa: BLE001 — a present file can still fail to probe
            reason = "Could not read streams for this file"
        return MediaAsset(
            rating_key=key,
            source_path=local.name,
            local_path=str(local),
            readable=True,
            reason=reason,
            probe=probe,
        )


def install_fixture_library(db: Any, data_dir: Path) -> int:
    """Insert the catalog into the library and turn on Play through Projectionist.

    Returns 0 when this process is not a fixture run. The subtitle file named
    by a title is copied into the household caption cache so Play can offer it
    without waiting on extraction.
    """
    source = try_fixture_media_source()
    if source is None:
        return 0
    root = source.root
    catalog = _read_catalog(root)
    titles = catalog.get("titles")
    if not isinstance(titles, list) or not titles:
        raise FixtureMediaError("Fixture catalog has no titles")
    for entry in titles:
        if not isinstance(entry, dict):
            raise FixtureMediaError("Fixture catalog title is not an object")
        key = str(entry.get("rating_key") or "").strip()
        if key not in source._titles:
            raise FixtureMediaError("Fixture catalog title failed the file check")
        duration_s = int(catalog.get("duration_s") or 0)
        db.upsert_library_item(
            {
                "rating_key": key,
                "media_type": "movie",
                "title": str(entry.get("title") or key),
                "year": 2026,
                "summary": "",
                "original_language": str(entry.get("original_language") or "en"),
                "duration_ms": max(0, duration_s) * 1000,
                "runtime_minutes": max(1, duration_s // 60),
                "content_rating": "G",
                "view_offset_ms": 0,
                "genres": [],
                "cast": [],
                "directors": [],
            }
        )
        subtitle = str(entry.get("subtitle") or "").strip()
        if subtitle:
            _install_subtitle(root, key, subtitle, data_dir)
    _enable_engine(data_dir)
    logger.info("fixture media library ready titles=%s", len(titles))
    return len(titles)


def _enable_engine(data_dir: Path) -> None:
    settings = load_merged_settings(data_dir)
    if settings.engine.play_through_projectionist:
        return
    current = asdict(settings.engine)
    current["play_through_projectionist"] = True
    updated = Settings.from_mapping({**asdict(settings), "engine": current})
    save_settings(data_dir, updated)


def _install_subtitle(root: Path, rating_key: str, name: str, data_dir: Path) -> None:
    source = _file_inside(root, name)
    if source is None or not source.is_file():
        raise FixtureMediaError("Fixture subtitle file is missing")
    dest = cache_path(rating_key, "en", data_dir=data_dir)
    if dest is None:
        raise FixtureMediaError("Fixture subtitle cache path is not valid")
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, dest)


def _load_catalog(root: Path) -> dict[str, dict[str, Any]]:
    catalog = _read_catalog(root)
    titles = catalog.get("titles")
    if not isinstance(titles, list):
        raise FixtureMediaError("Fixture catalog has no titles")
    loaded: dict[str, dict[str, Any]] = {}
    for entry in titles:
        if not isinstance(entry, dict):
            continue
        key = str(entry.get("rating_key") or "").strip()
        if not key or key in loaded:
            continue
        if _file_inside(root, str(entry.get("file") or "")) is None:
            continue
        loaded[key] = entry
    if not loaded:
        raise FixtureMediaError("Fixture catalog has no usable titles")
    return loaded


def _read_catalog(root: Path) -> dict[str, Any]:
    try:
        payload = json.loads((root / "catalog.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise FixtureMediaError("Fixture catalog could not be read") from error
    if not isinstance(payload, dict):
        raise FixtureMediaError("Fixture catalog is not an object")
    return payload


def _file_inside(root: Path, name: str) -> Optional[Path]:
    """A basename inside the fixture directory. Rejects paths that escape it."""
    text = str(name or "").strip()
    if not text or text in {".", ".."} or "/" in text or "\\" in text:
        return None
    root_resolved = root.resolve()
    candidate = (root_resolved / text).resolve()
    if candidate.parent != root_resolved:
        return None
    return candidate
