"""Movie rematch studio — Plex GUID vs Radarr TMDB vs folder.

Reuses the 1.35.5 Radarr classifier. FileBot / Plex Match / Gracenote are
not investigators; this surface explains identity mismatches so an owner
can rematch, skip, or retry register.
"""

from __future__ import annotations

import json
import logging
import re
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


def repair_actions_for(*, kind: str, media_type: str = "movie") -> List[str]:
    cleaned = str(kind or "").strip().lower()
    media = str(media_type or "movie").strip().lower()
    if cleaned == KIND_NEEDS_PLEX_ID:
        return ["rematch", "skip"]
    if cleaned in {KIND_PATH_CONFLICT, KIND_TITLE_COLLISION}:
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
    same_title = _same_title(str(plex.get("title") or ""), str((radarr or {}).get("title") or ""))
    return {
        "id": int(plex["id"]),
        "title": plex.get("title") or "",
        "year": plex.get("year"),
        "media_type": media_type,
        "kind": kind,
        "message": humanize_operator_error(message),
        "same_title": same_title,
        "folder": folder or (radarr or {}).get("folder_path") or "",
        "plex": dict(plex),
        "radarr": dict(radarr) if radarr else None,
        "actions": repair_actions_for(kind=kind, media_type=media_type),
        "skipped": bool(skipped),
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
            return {
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
    if classified.kind == KIND_ALREADY:
        from projectionist.agent.tools import mark_in_radarr

        mark_in_radarr(db, int(tmdb_id), title=str(plex.get("title") or classified.occupant_title))
        return {
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
        repairs.append(
            {
                "id": raw.get("id"),
                "source": "radarr_register",
                "title": title,
                "kind": kind,
                "message": error,
                "media_type": "movie",
                "tmdb_id": raw.get("tmdb_id"),
                "actions": repair_actions_for(kind=kind, media_type="movie"),
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
