"""Movie rematch studio — Plex GUID vs Radarr TMDB vs folder.

Reuses the 1.35.5 Radarr classifier. FileBot / Plex Match / Gracenote are
not investigators; this surface explains identity mismatches so an owner
can rematch, skip, or retry register.
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import PurePosixPath
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set

from projectionist.config_store import (
    radarr_add_configuration_error,
    resolve_radarr_root_folder,
)
from projectionist.connectors.arr_errors import (
    classify_radarr_add_error,
    classify_radarr_catalog,
    folder_path_from_arr_error,
    format_already_in_radarr_message,
    format_arr_http_error,
    format_path_conflict_message,
    intended_movie_folder,
)
from projectionist.connectors.radarr import (
    RadarrClient,
    RadarrMovie,
    folder_path_for_movie,
    index_radarr_movies,
    movie_occupying_folder,
)
from projectionist.library.db import Database

logger = logging.getLogger(__name__)

SKIP_CONFIG_KEY = "rematch_skipped_ids"
KIND_PATH_CONFLICT = "path_conflict"
KIND_TITLE_COLLISION = "title_collision"
KIND_NEEDS_PLEX_ID = "needs_plex_id"
KIND_ALREADY = "already"
OUTCOME_ADOPTED_RADARR = "adopted_radarr"
OUTCOME_ADOPTED_PLEX = "adopted_plex"
OUTCOME_RECHECKED = "rechecked"

# Plex Match / Fix Match / Radarr "Change Movie" are not exposed as APIs we call.
# Safe automation is re-check + confirmed Projectionist/Radarr catalog writes only.
PLEX_RADARR_REMATCH_API_NOTE = (
    "Full auto-rematch in Plex or Radarr is not available via API here — "
    "Plex Fix Match and Radarr Change Movie stay manual. Projectionist can "
    "re-check after an external fix, adopt Radarr’s TMDB on the index "
    "(confirm), or replace the Radarr catalog entry with Plex’s TMDB without "
    "deleting files (confirm)."
)

_JSONISH = re.compile(r'(\{[^{}]*"errorCode"|formattedMessagePlaceholderValues|\[\s*\{\s*")')


def looks_like_json_dump(text: str) -> bool:
    cleaned = str(text or "").strip()
    if not cleaned:
        return False
    if "formattedMessagePlaceholderValues" in cleaned or '"errorCode"' in cleaned:
        return True
    if cleaned.startswith("{") or cleaned.startswith("["):
        return True
    if cleaned.lower().startswith("http ") and "{" in cleaned:
        return True
    return bool(_JSONISH.search(cleaned))


def humanize_operator_error(text: str) -> str:
    """Turn a failed search/register payload into one human line — no JSON dump."""
    cleaned = str(text or "").strip()
    if not cleaned:
        return "This title did not land. Rematch, skip, or retry."
    if looks_like_json_dump(cleaned):
        return format_arr_http_error(RuntimeError(cleaned))
    first = cleaned.split("\n", 1)[0].strip()
    if len(first) > 240:
        return first[:237] + "..."
    return first


_YEAR_SUFFIX = re.compile(r"\s*\(\d{4}\)\s*$")


def _title_core(title: str) -> str:
    return _YEAR_SUFFIX.sub("", str(title or "").strip()).casefold()


def soft_identity_match(
    *,
    plex_title: str,
    plex_year: Any = None,
    radarr_title: str,
    radarr_year: Any = None,
) -> bool:
    """True when title/year look like the same movie (path conflict rematch pattern)."""
    left = _title_core(plex_title)
    right = _title_core(radarr_title)
    if not left or not right or left != right:
        return False
    try:
        plex_y = int(plex_year) if plex_year not in (None, "") else None
    except (TypeError, ValueError):
        plex_y = None
    try:
        radarr_y = int(radarr_year) if radarr_year not in (None, "") else None
    except (TypeError, ValueError):
        radarr_y = None
    if plex_y is None or radarr_y is None:
        return True
    return plex_y == radarr_y


def repair_actions_for(
    *,
    kind: str,
    media_type: str = "movie",
    soft_match: bool = False,
) -> List[str]:
    cleaned = str(kind or "").strip().lower()
    media = str(media_type or "movie").strip().lower()
    if cleaned == KIND_NEEDS_PLEX_ID:
        return ["rematch", "skip"]
    if cleaned == KIND_PATH_CONFLICT:
        actions = ["retry", "rematch", "skip"]
        if soft_match:
            actions = ["use_radarr", "use_plex", "retry", "rematch", "skip"]
        return actions
    if cleaned == KIND_TITLE_COLLISION:
        return ["rematch", "skip", "retry"]
    if media in {"show", "episode", "tv"}:
        return ["retry", "investigate", "skip"]
    return ["retry", "skip", "rematch"]


def folder_basename(path: str) -> str:
    return str(PurePosixPath(str(path or "").strip().rstrip("/")).name).casefold()


def intended_folder_basename(*, title: str, year: Any = None) -> str:
    label = str(title or "").strip()
    if year not in (None, ""):
        try:
            label = f"{label} ({int(year)})"
        except (TypeError, ValueError):
            label = f"{label} ({year})"
    return label.casefold()


def occupant_by_basename(
    movies: Sequence[RadarrMovie],
    basename: str,
) -> Optional[RadarrMovie]:
    """Match Radarr folders when the root prefix differs from settings."""
    key = str(basename or "").casefold()
    if not key:
        return None
    for movie in movies:
        folder = folder_path_for_movie(movie)
        if folder_basename(folder) == key:
            return movie
    return None


def resolve_occupant(
    *,
    movies: Sequence[RadarrMovie],
    by_path: Mapping[str, RadarrMovie],
    intended_path: str,
    title: str,
    year: Any = None,
) -> Optional[RadarrMovie]:
    occupant = movie_occupying_folder(by_path, intended_path) if intended_path else None
    if occupant is not None:
        return occupant
    return occupant_by_basename(movies, intended_folder_basename(title=title, year=year))


def _title_key(title: str, year: Any = None) -> str:
    label = str(title or "").strip().casefold()
    if year not in (None, ""):
        try:
            label = f"{label}|{int(year)}"
        except (TypeError, ValueError):
            label = f"{label}|{year}"
    return label


def load_skipped_ids(db: Database) -> Set[int]:
    raw = db.get_config(SKIP_CONFIG_KEY) if hasattr(db, "get_config") else None
    if not raw:
        return set()
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return set()
    ids: Set[int] = set()
    if isinstance(payload, list):
        for item in payload:
            try:
                ids.add(int(item))
            except (TypeError, ValueError):
                continue
    return ids


def persist_skipped_ids(db: Database, ids: Iterable[int]) -> List[int]:
    cleaned = sorted({int(item) for item in ids})
    db.set_config(SKIP_CONFIG_KEY, json.dumps(cleaned))
    return cleaned


def set_skipped(db: Database, item_id: int, *, skipped: bool = True) -> List[int]:
    ids = load_skipped_ids(db)
    if skipped:
        ids.add(int(item_id))
    else:
        ids.discard(int(item_id))
    return persist_skipped_ids(db, ids)


def _movie_rows(db: Database, *, limit: int = 400) -> List[Mapping[str, Any]]:
    lim = min(max(1, int(limit or 400)), 800)
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT id, title, year, tmdb_id, rating_key, media_type, in_radarr
            FROM library_items
            WHERE media_type = 'movie'
            ORDER BY title COLLATE NOCASE
            LIMIT ?
            """,
            (lim,),
        ).fetchall()
    return list(rows)


def _plex_side(row: Mapping[str, Any]) -> Dict[str, Any]:
    year = row["year"] if "year" in row.keys() else row.get("year")
    tmdb = row["tmdb_id"] if "tmdb_id" in row.keys() else row.get("tmdb_id")
    try:
        tmdb_int = int(tmdb) if tmdb not in (None, "", 0, "0") else None
    except (TypeError, ValueError):
        tmdb_int = None
    try:
        year_int = int(year) if year not in (None, "") else None
    except (TypeError, ValueError):
        year_int = None
    return {
        "id": int(row["id"]),
        "title": str(row["title"] or ""),
        "year": year_int,
        "tmdb_id": tmdb_int,
        "rating_key": str(row["rating_key"] or "") if row["rating_key"] else None,
    }


def _radarr_side(movie: Optional[RadarrMovie]) -> Optional[Dict[str, Any]]:
    if movie is None:
        return None
    folder = str(movie.folder_path or "").strip() or None
    return {
        "arr_id": int(movie.id) if movie.id else None,
        "title": str(movie.title or ""),
        "year": int(movie.year) if movie.year not in (None, "") else None,
        "tmdb_id": int(movie.tmdb_id) if movie.tmdb_id else None,
        "folder_path": folder,
    }


def _same_title(plex_title: str, radarr_title: str) -> bool:
    left = str(plex_title or "").strip().casefold()
    right = str(radarr_title or "").strip().casefold()
    return bool(left and right and left == right)


def _row_payload(
    *,
    plex: Mapping[str, Any],
    kind: str,
    message: str,
    radarr: Optional[Mapping[str, Any]] = None,
    folder: str = "",
    skipped: bool = False,
) -> Dict[str, Any]:
    media_type = "movie"
    radarr_side = dict(radarr) if radarr else None
    same_title = _same_title(str(plex.get("title") or ""), str((radarr_side or {}).get("title") or ""))
    soft = bool(
        kind == KIND_PATH_CONFLICT
        and soft_identity_match(
            plex_title=str(plex.get("title") or ""),
            plex_year=plex.get("year"),
            radarr_title=str((radarr_side or {}).get("title") or ""),
            radarr_year=(radarr_side or {}).get("year"),
        )
    )
    return {
        "id": int(plex["id"]),
        "title": plex.get("title") or "",
        "year": plex.get("year"),
        "media_type": media_type,
        "kind": kind,
        "message": humanize_operator_error(message),
        "same_title": same_title,
        "soft_match": soft,
        "folder": folder or (radarr_side or {}).get("folder_path") or "",
        "plex": dict(plex),
        "radarr": radarr_side,
        "plex_tmdb_id": plex.get("tmdb_id"),
        "radarr_tmdb_id": (radarr_side or {}).get("tmdb_id"),
        "folder_path": folder or (radarr_side or {}).get("folder_path") or "",
        "actions": repair_actions_for(kind=kind, media_type=media_type, soft_match=soft),
        "skipped": bool(skipped),
        "side_effects": {
            "use_radarr": (
                "Updates Projectionist’s indexed TMDB id to Radarr’s and marks the title "
                "in Radarr. Does not change Plex GUID — rematch in Plex if the next sync "
                "should keep this identity."
            ),
            "use_plex": (
                "Removes the conflicting movie from Radarr’s catalog (files stay on disk), "
                "then registers under Plex’s TMDB id without a download search."
            ),
        }
        if soft
        else {},
    }


def _title_collision_message(*, plex: Mapping[str, Any], occupant: RadarrMovie) -> str:
    plex_bit = f"{plex.get('title') or 'Plex'}"
    if plex.get("tmdb_id"):
        plex_bit = f"{plex_bit} (tmdb {plex['tmdb_id']})"
    radarr_bit = occupant.title or "a Radarr movie"
    if occupant.tmdb_id:
        radarr_bit = f"{radarr_bit} (tmdb {occupant.tmdb_id})"
    return (
        f"Same title, different identity: Plex has {plex_bit}; "
        f"Radarr has {radarr_bit}. Rematch one side — FileBot is not an investigator here."
    )


def _needs_plex_message(plex: Mapping[str, Any], occupant: Optional[RadarrMovie] = None) -> str:
    title = plex.get("title") or "This title"
    year = plex.get("year")
    label = f"{title} ({year})" if year else title
    if occupant is not None and occupant.tmdb_id:
        return (
            f"{label} has no TMDB id from Plex, but Radarr already treats that folder as "
            f"{occupant.title or 'another movie'} (tmdb {occupant.tmdb_id}). "
            "Rematch the Plex listing — Plex Match and Gracenote are not investigators here."
        )
    return (
        f"{label} has no TMDB id from Plex, so we cannot tell which movie it is. "
        "Rematch the listing in Plex — FileBot and Plex Match are not investigators here."
    )


def scan_identity_mismatches(
    db: Database,
    settings: Any,
    *,
    catalog: Optional[Sequence[RadarrMovie]] = None,
    include_skipped: bool = False,
    limit: int = 400,
) -> Dict[str, Any]:
    """Compare Plex movie identity to Radarr TMDB + folder."""
    skipped = load_skipped_ids(db)
    movies = _movie_rows(db, limit=limit)
    config_error = radarr_add_configuration_error(settings)
    radarr_movies: List[RadarrMovie] = list(catalog or [])
    radarr_note = ""
    if catalog is None and not config_error:
        try:
            client = RadarrClient(settings.radarr_url, settings.radarr_api_key)
            radarr_movies = list(client.movies())
        except Exception as error:  # noqa: BLE001 — studio still lists Plex-only misses
            logger.warning("Rematch studio could not load Radarr catalog: %s", error)
            radarr_note = humanize_operator_error(str(error))
    elif config_error:
        radarr_note = config_error

    by_tmdb, by_path = index_radarr_movies(radarr_movies)
    by_title: Dict[str, List[RadarrMovie]] = {}
    for movie in radarr_movies:
        by_title.setdefault(_title_key(movie.title, movie.year), []).append(movie)

    root_folder = ""
    try:
        root_folder = resolve_radarr_root_folder(settings)
    except Exception:  # noqa: BLE001
        root_folder = str(getattr(settings, "radarr_root_folder", "") or getattr(settings, "movies_root", "") or "")

    items: List[Dict[str, Any]] = []
    for row in movies:
        plex = _plex_side(row)
        item_id = int(plex["id"])
        is_skipped = item_id in skipped
        if is_skipped and not include_skipped:
            continue
        intended_path = intended_movie_folder(
            root_folder=root_folder,
            title=str(plex.get("title") or ""),
            year=plex.get("year"),
        )
        occupant = resolve_occupant(
            movies=radarr_movies,
            by_path=by_path,
            intended_path=intended_path,
            title=str(plex.get("title") or ""),
            year=plex.get("year"),
        )
        tmdb_id = plex.get("tmdb_id")
        if not tmdb_id:
            items.append(
                _row_payload(
                    plex=plex,
                    kind=KIND_NEEDS_PLEX_ID,
                    message=_needs_plex_message(plex, occupant),
                    radarr=_radarr_side(occupant),
                    folder=intended_path or (occupant.folder_path if occupant else ""),
                    skipped=is_skipped,
                )
            )
            continue
        classified = classify_radarr_catalog(
            intended_tmdb_id=int(tmdb_id),
            intended_title=str(plex.get("title") or ""),
            intended_path=intended_path,
            by_tmdb=by_tmdb.get(int(tmdb_id)),
            by_path=occupant,
        )
        if classified is not None and classified.kind == KIND_PATH_CONFLICT:
            items.append(
                _row_payload(
                    plex=plex,
                    kind=KIND_PATH_CONFLICT,
                    message=classified.message or format_path_conflict_message(
                        path=classified.folder_path or intended_path,
                        intended_title=str(plex.get("title") or ""),
                        intended_tmdb_id=int(tmdb_id),
                        occupant_title=classified.occupant_title,
                        occupant_tmdb_id=classified.occupant_tmdb_id,
                    ),
                    radarr=_radarr_side(occupant) or {
                        "title": classified.occupant_title,
                        "tmdb_id": classified.occupant_tmdb_id or None,
                        "arr_id": classified.occupant_arr_id,
                        "folder_path": classified.folder_path or intended_path,
                    },
                    folder=classified.folder_path or intended_path,
                    skipped=is_skipped,
                )
            )
            continue
        collisions = [
            movie
            for movie in by_title.get(_title_key(str(plex.get("title") or ""), plex.get("year")), [])
            if movie.tmdb_id and int(movie.tmdb_id) != int(tmdb_id)
        ]
        if collisions:
            other = collisions[0]
            items.append(
                _row_payload(
                    plex=plex,
                    kind=KIND_TITLE_COLLISION,
                    message=_title_collision_message(plex=plex, occupant=other),
                    radarr=_radarr_side(other),
                    folder=other.folder_path or intended_path,
                    skipped=is_skipped,
                )
            )
    counts = {
        KIND_PATH_CONFLICT: 0,
        KIND_TITLE_COLLISION: 0,
        KIND_NEEDS_PLEX_ID: 0,
    }
    for item in items:
        kind = str(item.get("kind") or "")
        if kind in counts:
            counts[kind] += 1
    return {
        "items": items,
        "total": len(items),
        "skipped_count": len(skipped),
        "counts": counts,
        "radarr_note": radarr_note,
        "investigators_note": (
            "FileBot, Plex Match, and Gracenote are not investigators. "
            "Compare Plex GUID, Radarr TMDB, and the folder — then rematch by hand."
        ),
        "api_note": PLEX_RADARR_REMATCH_API_NOTE,
    }


def _set_library_item_tmdb(db: Database, item_id: int, tmdb_id: int) -> None:
    now = time.time()

    def _write() -> None:
        with db.connect() as conn:
            conn.execute(
                "UPDATE library_items SET tmdb_id = ?, updated_at = ? WHERE id = ?",
                (int(tmdb_id), now, int(item_id)),
            )

    if hasattr(db, "run_write"):
        db.run_write(_write, label="rematch_set_tmdb")
    else:
        _write()


def _path_conflict_context(
    db: Database,
    settings: Any,
    item_id: int,
    *,
    client: Any = None,
) -> Dict[str, Any]:
    config_error = radarr_add_configuration_error(settings)
    if config_error:
        raise ValueError(config_error)
    row = db.library_item_by_id(int(item_id))
    if row is None:
        raise ValueError("That title is not in the library index.")
    plex = _plex_side(row)
    radarr = client or RadarrClient(settings.radarr_url, settings.radarr_api_key)
    root_folder = resolve_radarr_root_folder(settings)
    intended_path = intended_movie_folder(
        root_folder=root_folder,
        title=str(plex.get("title") or ""),
        year=plex.get("year"),
    )
    catalog: List[RadarrMovie] = list(radarr.movies())
    by_tmdb, by_path = index_radarr_movies(catalog)
    occupant = resolve_occupant(
        movies=catalog,
        by_path=by_path,
        intended_path=intended_path,
        title=str(plex.get("title") or ""),
        year=plex.get("year"),
    )
    return {
        "plex": plex,
        "radarr_client": radarr,
        "root_folder": root_folder,
        "intended_path": intended_path,
        "catalog": catalog,
        "by_tmdb": by_tmdb,
        "by_path": by_path,
        "occupant": occupant,
    }


def adopt_radarr_identity(
    db: Database,
    settings: Any,
    item_id: int,
    *,
    confirm: bool = False,
    client: Any = None,
) -> Dict[str, Any]:
    """Point Projectionist’s index at Radarr’s TMDB for a soft path conflict."""
    if not confirm:
        raise ValueError("Confirm to adopt Radarr’s identity on the Projectionist index.")
    ctx = _path_conflict_context(db, settings, item_id, client=client)
    plex = ctx["plex"]
    occupant = ctx["occupant"]
    if occupant is None or not occupant.tmdb_id:
        raise ValueError("Radarr does not own that folder under a known TMDB id.")
    soft = soft_identity_match(
        plex_title=str(plex.get("title") or ""),
        plex_year=plex.get("year"),
        radarr_title=str(occupant.title or ""),
        radarr_year=occupant.year,
    )
    if not soft:
        raise ValueError(
            "Titles do not soft-match — rematch in Plex or Radarr instead of adopting."
        )
    plex_tmdb = plex.get("tmdb_id")
    if plex_tmdb and int(plex_tmdb) == int(occupant.tmdb_id):
        from projectionist.agent.tools import mark_in_radarr

        mark_in_radarr(db, int(occupant.tmdb_id), title=str(occupant.title or plex.get("title") or ""))
        return {
            "ok": True,
            "outcome": OUTCOME_RECHECKED,
            "message": "Plex and Radarr already share this TMDB id — marked in Radarr.",
            "item": _row_payload(
                plex={**plex, "tmdb_id": int(occupant.tmdb_id)},
                kind=KIND_ALREADY,
                message=format_already_in_radarr_message(
                    title=str(occupant.title or plex.get("title") or ""),
                    path=ctx["intended_path"],
                ),
                radarr=_radarr_side(occupant),
                folder=ctx["intended_path"],
            ),
        }
    _set_library_item_tmdb(db, int(item_id), int(occupant.tmdb_id))
    from projectionist.agent.tools import mark_in_radarr

    mark_in_radarr(db, int(occupant.tmdb_id), title=str(occupant.title or plex.get("title") or ""))
    updated = {**plex, "tmdb_id": int(occupant.tmdb_id)}
    return {
        "ok": True,
        "outcome": OUTCOME_ADOPTED_RADARR,
        "message": (
            f"Projectionist now indexes tmdb {occupant.tmdb_id} (Radarr). "
            "Rematch in Plex if the GUID still differs so the next sync keeps this identity."
        ),
        "changed_side": "projectionist_index",
        "plex_tmdb_id_before": plex_tmdb,
        "radarr_tmdb_id": int(occupant.tmdb_id),
        "item": _row_payload(
            plex=updated,
            kind=KIND_ALREADY,
            message=format_already_in_radarr_message(
                title=str(occupant.title or plex.get("title") or ""),
                path=ctx["intended_path"],
            ),
            radarr=_radarr_side(occupant),
            folder=ctx["intended_path"],
        ),
    }


def adopt_plex_identity(
    db: Database,
    settings: Any,
    item_id: int,
    *,
    confirm: bool = False,
    client: Any = None,
) -> Dict[str, Any]:
    """Replace Radarr’s catalog entry with Plex’s TMDB (files stay on disk)."""
    if not confirm:
        raise ValueError("Confirm to replace Radarr’s catalog identity (files stay on disk).")
    ctx = _path_conflict_context(db, settings, item_id, client=client)
    plex = ctx["plex"]
    occupant = ctx["occupant"]
    tmdb_id = plex.get("tmdb_id")
    if not tmdb_id:
        raise ValueError(_needs_plex_message(plex, occupant))
    if occupant is None or not occupant.id:
        raise ValueError("Radarr does not own that folder — Retry to register instead.")
    soft = soft_identity_match(
        plex_title=str(plex.get("title") or ""),
        plex_year=plex.get("year"),
        radarr_title=str(occupant.title or ""),
        radarr_year=occupant.year,
    )
    if not soft:
        raise ValueError(
            "Titles do not soft-match — rematch in Plex or Radarr instead of replacing."
        )
    if occupant.tmdb_id and int(occupant.tmdb_id) == int(tmdb_id):
        from projectionist.agent.tools import mark_in_radarr

        mark_in_radarr(db, int(tmdb_id), title=str(plex.get("title") or ""))
        return {
            "ok": True,
            "outcome": OUTCOME_RECHECKED,
            "message": "Radarr already uses Plex’s TMDB id.",
            "item": _row_payload(
                plex=plex,
                kind=KIND_ALREADY,
                message=format_already_in_radarr_message(
                    title=str(plex.get("title") or ""),
                    path=ctx["intended_path"],
                ),
                radarr=_radarr_side(occupant),
                folder=ctx["intended_path"],
            ),
        }
    radarr = ctx["radarr_client"]
    radarr.delete_movie(int(occupant.id), delete_files=False, add_exclusion=False)
    try:
        radarr.add_movie(
            int(tmdb_id),
            root_folder=ctx["root_folder"],
            quality_profile_id=getattr(settings, "radarr_quality_profile_id", None),
            search_for_movie=False,
        )
    except Exception as error:  # noqa: BLE001
        classified = classify_radarr_add_error(
            error,
            intended_tmdb_id=int(tmdb_id),
            intended_title=str(plex.get("title") or ""),
            occupant=None,
        )
        if classified.kind != KIND_ALREADY:
            raise ValueError(humanize_operator_error(classified.message)) from error
    from projectionist.agent.tools import mark_in_radarr

    mark_in_radarr(db, int(tmdb_id), title=str(plex.get("title") or ""))
    return {
        "ok": True,
        "outcome": OUTCOME_ADOPTED_PLEX,
        "message": (
            f"Radarr catalog now uses Plex tmdb {tmdb_id}. "
            "Files on disk were not deleted."
        ),
        "changed_side": "radarr_catalog",
        "plex_tmdb_id": int(tmdb_id),
        "radarr_tmdb_id_before": int(occupant.tmdb_id) if occupant.tmdb_id else None,
        "item": _row_payload(
            plex=plex,
            kind=KIND_ALREADY,
            message=format_already_in_radarr_message(
                title=str(plex.get("title") or ""),
                path=ctx["intended_path"],
            ),
            radarr={
                "tmdb_id": int(tmdb_id),
                "title": plex.get("title"),
                "folder_path": ctx["intended_path"],
            },
            folder=ctx["intended_path"],
        ),
    }


def _sync_register_item_outcome(item_id: int, *, outcome: str, message: str = "") -> None:
    try:
        from projectionist.library.admin_execution import store_for
        from projectionist.library.radarr_register import KIND as REGISTER_KIND

        store = store_for(REGISTER_KIND)
        status = "completed" if outcome in {
            "registered",
            KIND_ALREADY,
            OUTCOME_ADOPTED_RADARR,
            OUTCOME_ADOPTED_PLEX,
            OUTCOME_RECHECKED,
        } else "failed"
        if outcome == KIND_ALREADY:
            status = "skipped"
        store.set_item(
            int(item_id),
            status,
            outcome=outcome,
            message=message,
            error="" if status != "failed" else message,
        )
    except Exception:  # noqa: BLE001 — repair UI still reflects API result
        logger.debug("Could not sync radarr_register item %s", item_id, exc_info=True)


def recheck_path_conflicts(
    db: Database,
    settings: Any,
    item_ids: Optional[Sequence[int]] = None,
    *,
    client: Any = None,
) -> Dict[str, Any]:
    """Retry register for path-conflict titles after an external identity fix."""
    ids = [int(i) for i in (item_ids or []) if i is not None]
    if not ids:
        scan = scan_identity_mismatches(db, settings, catalog=None if client is None else list(client.movies()))
        ids = [
            int(row["id"])
            for row in scan.get("items") or []
            if str(row.get("kind") or "") == KIND_PATH_CONFLICT
        ]
    cleared: List[Dict[str, Any]] = []
    remaining: List[Dict[str, Any]] = []
    for item_id in ids:
        try:
            result = retry_register_title(db, settings, item_id, client=client)
        except ValueError as error:
            remaining.append(
                {
                    "id": item_id,
                    "ok": False,
                    "outcome": "error",
                    "message": str(error),
                }
            )
            continue
        if result.get("ok"):
            _sync_register_item_outcome(
                item_id,
                outcome=str(result.get("outcome") or OUTCOME_RECHECKED),
                message=str(result.get("message") or ""),
            )
            cleared.append(result)
        else:
            remaining.append(result)
    return {
        "ok": True,
        "cleared": len(cleared),
        "remaining": len(remaining),
        "results": cleared + remaining,
        "api_note": PLEX_RADARR_REMATCH_API_NOTE,
    }


def retry_register_title(
    db: Database,
    settings: Any,
    item_id: int,
    *,
    client: Any = None,
) -> Dict[str, Any]:
    """Retry a single Register-in-Radarr without a download search."""
    config_error = radarr_add_configuration_error(settings)
    if config_error:
        raise ValueError(config_error)
    row = db.library_item_by_id(int(item_id))
    if row is None:
        raise ValueError("That title is not in the library index.")
    plex = _plex_side(row)
    tmdb_id = plex.get("tmdb_id")
    if not tmdb_id:
        raise ValueError(_needs_plex_message(plex))
    radarr = client or RadarrClient(settings.radarr_url, settings.radarr_api_key)
    root_folder = resolve_radarr_root_folder(settings)
    intended_path = intended_movie_folder(
        root_folder=root_folder,
        title=str(plex.get("title") or ""),
        year=plex.get("year"),
    )
    catalog: List[RadarrMovie] = []
    try:
        catalog = list(radarr.movies())
    except Exception as error:  # noqa: BLE001
        logger.warning("Rematch retry could not load catalog: %s", error)
    by_tmdb, by_path = index_radarr_movies(catalog)
    occupant = resolve_occupant(
        movies=catalog,
        by_path=by_path,
        intended_path=intended_path,
        title=str(plex.get("title") or ""),
        year=plex.get("year"),
    )
    classified = classify_radarr_catalog(
        intended_tmdb_id=int(tmdb_id),
        intended_title=str(plex.get("title") or ""),
        intended_path=intended_path,
        by_tmdb=by_tmdb.get(int(tmdb_id)),
        by_path=occupant,
    )
    if classified is None:
        try:
            radarr.add_movie(
                int(tmdb_id),
                root_folder=root_folder,
                quality_profile_id=getattr(settings, "radarr_quality_profile_id", None),
                search_for_movie=False,
            )
        except Exception as error:  # noqa: BLE001
            occupant = movie_occupying_folder(
                by_path,
                folder_path_from_arr_error(error) or intended_path,
            )
            classified = classify_radarr_add_error(
                error,
                intended_tmdb_id=int(tmdb_id),
                intended_title=str(plex.get("title") or ""),
                occupant=occupant,
            )
        else:
            from projectionist.agent.tools import mark_in_radarr

            mark_in_radarr(db, int(tmdb_id), title=str(plex.get("title") or ""))
            result = {
                "ok": True,
                "outcome": "registered",
                "message": f'{plex.get("title") or "Title"} is registered in Radarr.',
                "item": _row_payload(
                    plex=plex,
                    kind=KIND_ALREADY,
                    message=format_already_in_radarr_message(
                        title=str(plex.get("title") or ""),
                        path=intended_path,
                    ),
                    radarr={"tmdb_id": int(tmdb_id), "title": plex.get("title"), "folder_path": intended_path},
                    folder=intended_path,
                ),
            }
            _sync_register_item_outcome(
                int(item_id),
                outcome="registered",
                message=str(result["message"]),
            )
            return result
    if classified.kind == KIND_ALREADY:
        from projectionist.agent.tools import mark_in_radarr

        mark_in_radarr(db, int(tmdb_id), title=str(plex.get("title") or classified.occupant_title))
        result = {
            "ok": True,
            "outcome": "already",
            "message": classified.message,
            "item": _row_payload(
                plex=plex,
                kind=KIND_ALREADY,
                message=classified.message,
                radarr=_radarr_side(occupant),
                folder=classified.folder_path or intended_path,
            ),
        }
        _sync_register_item_outcome(
            int(item_id),
            outcome=KIND_ALREADY,
            message=str(classified.message or ""),
        )
        return result
    return {
        "ok": False,
        "outcome": classified.kind,
        "message": humanize_operator_error(classified.message),
        "item": _row_payload(
            plex=plex,
            kind=classified.kind if classified.kind in {KIND_PATH_CONFLICT, KIND_TITLE_COLLISION} else KIND_PATH_CONFLICT,
            message=classified.message,
            radarr=_radarr_side(occupant),
            folder=classified.folder_path or intended_path,
        ),
    }


def collect_repair_misses(
    *,
    register_items: Optional[Sequence[Mapping[str, Any]]] = None,
    sonarr_status: Optional[Mapping[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Failed search/register rows with rematch / skip / retry / Investigate."""
    repairs: List[Dict[str, Any]] = []
    for raw in register_items or []:
        if not isinstance(raw, Mapping):
            continue
        status = str(raw.get("status") or "").lower()
        outcome = str(raw.get("outcome") or "").lower()
        if status not in {"failed", "error"} and outcome not in {KIND_PATH_CONFLICT, "failed", "error"}:
            continue
        kind = KIND_PATH_CONFLICT if outcome == KIND_PATH_CONFLICT else "failed"
        title = str(raw.get("title") or raw.get("name") or "This title")
        error = humanize_operator_error(str(raw.get("error") or raw.get("message") or ""))
        soft = bool(raw.get("soft_match"))
        if kind == KIND_PATH_CONFLICT and not soft:
            soft = soft_identity_match(
                plex_title=str(raw.get("plex_title") or title),
                plex_year=raw.get("year"),
                radarr_title=str(raw.get("radarr_title") or raw.get("occupant_title") or ""),
                radarr_year=raw.get("radarr_year"),
            )
        plex_tmdb = raw.get("plex_tmdb_id") if raw.get("plex_tmdb_id") is not None else raw.get("tmdb_id")
        repairs.append(
            {
                "id": raw.get("id"),
                "source": "radarr_register",
                "title": title,
                "year": raw.get("year"),
                "kind": kind,
                "message": error,
                "media_type": "movie",
                "tmdb_id": plex_tmdb,
                "plex_tmdb_id": plex_tmdb,
                "radarr_tmdb_id": raw.get("radarr_tmdb_id"),
                "folder_path": raw.get("folder_path") or raw.get("folder") or "",
                "soft_match": soft,
                "same_title": bool(raw.get("same_title")) or soft,
                "actions": repair_actions_for(kind=kind, media_type="movie", soft_match=soft),
            }
        )
    if isinstance(sonarr_status, Mapping):
        last_error = str(
            (sonarr_status.get("execution") or {}).get("last_error")
            or sonarr_status.get("error")
            or ""
        ).strip()
        current = (sonarr_status.get("execution") or {}).get("current") or sonarr_status.get("current")
        failed_count = int((sonarr_status.get("execution") or {}).get("failed") or 0)
        if last_error or failed_count:
            label = "Sonarr search"
            if isinstance(current, Mapping):
                label = str(current.get("name") or current.get("message") or label)
            repairs.append(
                {
                    "id": "sonarr-miss",
                    "source": "sonarr_missing",
                    "title": label,
                    "kind": "failed",
                    "message": humanize_operator_error(last_error or "A Sonarr search command failed."),
                    "media_type": "show",
                    "actions": repair_actions_for(kind="failed", media_type="show"),
                }
            )
    return repairs
