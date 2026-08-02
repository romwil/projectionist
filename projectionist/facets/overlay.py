"""DATA_DIR taxonomy overlay writers (Admin promote only — never seed).

Writes merge into ``$DATA_DIR/taxonomy.json`` (layered aliases/concepts/packs).
Packaged ``projectionist/facets/data/taxonomy.json`` is never modified.
Baked ``tmdb_genre_ids`` / discover id fields are stripped on write.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Mapping, MutableMapping, Optional

from projectionist.facets.registry import reload_registry

logger = logging.getLogger(__name__)

_STRIP_KEYS = frozenset(
    {
        "tmdb_genre_ids",
        "keep_genre_ids",
        "reject_genre_ids",
        "genre_ids",
    }
)


def data_dir_path(explicit: Optional[Path] = None) -> Path:
    if explicit is not None:
        return Path(explicit).expanduser()
    env = str(os.environ.get("DATA_DIR") or "").strip()
    if not env:
        raise ValueError("DATA_DIR is not set; cannot write taxonomy overlay")
    return Path(env).expanduser()


def overlay_taxonomy_path(data_dir: Optional[Path] = None) -> Path:
    return data_dir_path(data_dir) / "taxonomy.json"


def _strip_baked_ids(value: Any) -> Any:
    if isinstance(value, Mapping):
        out: Dict[str, Any] = {}
        for key, nested in value.items():
            if str(key) in _STRIP_KEYS:
                continue
            out[str(key)] = _strip_baked_ids(nested)
        return out
    if isinstance(value, list):
        return [_strip_baked_ids(item) for item in value]
    return value


def _deep_merge(base: MutableMapping[str, Any], overlay: Mapping[str, Any]) -> Dict[str, Any]:
    merged: Dict[str, Any] = dict(base)
    for key, value in overlay.items():
        if (
            key in merged
            and isinstance(merged[key], MutableMapping)
            and isinstance(value, Mapping)
        ):
            merged[key] = _deep_merge(merged[key], value)  # type: ignore[arg-type]
        else:
            merged[key] = value
    return merged


def _load_overlay(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {"version": 2}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return {"version": 2}
    if not isinstance(payload, dict):
        return {"version": 2}
    return _strip_baked_ids(payload)


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(prefix=".taxonomy-", suffix=".json", dir=str(path.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def promote_facet_alias_to_overlay(
    *,
    alias: str,
    concept_id: Optional[str] = None,
    canonical_name: Optional[str] = None,
    data_dir: Optional[Path] = None,
    reload: bool = True,
) -> Dict[str, Any]:
    """Merge one alias into ``DATA_DIR/taxonomy.json`` and optionally reload registry.

    Prefers layered ``aliases`` → ``concept_id``. When only a TMDB display name is
    known, writes flat ``genre_aliases`` (still boot-merged by the registry).
    Never writes baked genre ids.
    """
    token = str(alias or "").strip()
    if not token:
        raise ValueError("alias is required")
    cid = str(concept_id or "").strip()
    cname = str(canonical_name or "").strip()
    if not cid and not cname:
        raise ValueError("concept_id or canonical_name is required")

    path = overlay_taxonomy_path(data_dir)
    current = _load_overlay(path)
    patch: Dict[str, Any] = {"version": int(current.get("version") or 2)}

    if cid:
        aliases = dict(current.get("aliases") or {})
        aliases[token.casefold()] = cid
        patch["aliases"] = aliases
    else:
        genre_aliases = dict(current.get("genre_aliases") or {})
        genre_aliases[token] = cname
        # Also store casefolded key for resolve lookups that casefold.
        genre_aliases[token.casefold()] = cname
        patch["genre_aliases"] = genre_aliases

    merged = _strip_baked_ids(_deep_merge(current, patch))
    _atomic_write_json(path, merged)
    if reload:
        reload_registry()
    logger.info("Promoted facet alias %r into overlay %s", token, path)
    return {"path": str(path), "overlay": merged, "alias": token.casefold()}
