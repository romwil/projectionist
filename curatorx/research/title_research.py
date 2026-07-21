"""Configured, provenance-aware media research for agent tools.

Only official JSON APIs are used here.  This is intentionally not a web browser.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Mapping, Optional

from curatorx.config_store import Settings
from curatorx.connectors.omdb import OMDbClient
from curatorx.connectors.tmdb import TMDBClient
from curatorx.connectors.tvdb import TVDBClient
from curatorx.connectors.wikipedia import fetch_extract
from curatorx.library.db import Database

logger = logging.getLogger(__name__)


def _source(status: str, **values: Any) -> Dict[str, Any]:
    return {"status": status, **values}


def _persist_research(
    result: Dict[str, Any],
    db: Optional[Database],
    *,
    entity_type: str,
    name: str,
    external_ids: Mapping[str, Any],
    library_item_id: Optional[int] = None,
) -> None:
    """Persist research opportunistically without losing a usable provider result."""
    if db is None or not name:
        return
    try:
        result["memory"] = db.save_repository_research(
            entity_type=entity_type,
            name=name,
            payload=result,
            external_ids=external_ids,
            library_item_id=library_item_id,
        )
    except Exception:
        logger.exception("Could not persist %s research for %r", entity_type, name)
        result["warnings"].append("Research was returned but could not be saved to repository memory.")


def _clean_credits(details: Mapping[str, Any]) -> Dict[str, list[Dict[str, str]]]:
    credits = details.get("credits") if isinstance(details.get("credits"), Mapping) else {}
    cast = [
        {"name": str(entry.get("name") or ""), "character": str(entry.get("character") or "")}
        for entry in credits.get("cast", [])[:12]
        if isinstance(entry, Mapping) and str(entry.get("name") or "").strip()
    ]
    crew = [
        {"name": str(entry.get("name") or ""), "job": str(entry.get("job") or "")}
        for entry in credits.get("crew", [])[:12]
        if isinstance(entry, Mapping) and str(entry.get("name") or "").strip()
    ]
    return {"cast": cast, "crew": crew}


def research_title(
    settings: Settings,
    *,
    title: str,
    year: Optional[int] = None,
    media_type: str = "movie",
    tmdb_id: Optional[int] = None,
    tvdb_id: Optional[int] = None,
    imdb_id: str = "",
    db: Optional[Database] = None,
    library_item_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Research one title through official providers and persist a safe repository snapshot."""
    kind = "show" if str(media_type).lower() == "show" else "movie"
    resolved_title = str(title or "").strip()
    result: Dict[str, Any] = {
        "identity": {
            "title": resolved_title,
            "year": year,
            "media_type": kind,
            "tmdb_id": tmdb_id,
            "tvdb_id": tvdb_id,
            "imdb_id": str(imdb_id or "").strip() or None,
        },
        "sources_checked": {
            "tmdb": _source("not_configured"),
            "wikipedia": _source("not_checked"),
            "omdb": _source("not_configured"),
            "tvdb": _source("not_configured"),
        },
        "plot": {},
        "credits": {"cast": [], "crew": []},
        "keywords": [],
        "images": {},
        "warnings": [],
    }

    if settings.tmdb_api_key:
        try:
            client = TMDBClient(settings.tmdb_api_key)
            details = (
                client.tv_details(int(tmdb_id))
                if tmdb_id and kind == "show"
                else client.movie_details(int(tmdb_id))
                if tmdb_id
                else {}
            )
            if details:
                actual_title = str(details.get("name") or details.get("title") or "").strip()
                if resolved_title and actual_title and resolved_title.casefold() != actual_title.casefold():
                    result["sources_checked"]["tmdb"] = _source("identity_mismatch")
                    result["warnings"].append(
                        f"TMDB id resolved to '{actual_title}', not requested title '{resolved_title}'."
                    )
                    details = {}
            if details:
                actual_title = str(details.get("name") or details.get("title") or "").strip()
                if actual_title:
                    result["identity"]["title"] = actual_title
                    resolved_title = actual_title
                result["identity"]["tmdb_id"] = int(details.get("id") or tmdb_id or 0) or None
                result["identity"]["imdb_id"] = (
                    str((details.get("external_ids") or {}).get("imdb_id") or imdb_id or "").strip() or None
                )
                result["plot"] = {
                    "tmdb_overview": str(details.get("overview") or "").strip(),
                    "tagline": str(details.get("tagline") or "").strip(),
                }
                result["credits"] = _clean_credits(details)
                keywords = details.get("keywords") if isinstance(details.get("keywords"), Mapping) else {}
                result["keywords"] = [
                    str(entry.get("name") or "")
                    for entry in keywords.get("keywords", [])
                    if isinstance(entry, Mapping) and str(entry.get("name") or "").strip()
                ][:20]
                result["images"] = {
                    "poster_path": str(details.get("poster_path") or ""),
                    "backdrop_path": str(details.get("backdrop_path") or ""),
                }
                result["sources_checked"]["tmdb"] = _source("ok")
            elif result["sources_checked"]["tmdb"]["status"] != "identity_mismatch":
                result["sources_checked"]["tmdb"] = _source("empty")
        except (RuntimeError, ValueError):
            result["sources_checked"]["tmdb"] = _source("unavailable")

    if resolved_title:
        try:
            extract = fetch_extract(resolved_title, year=year, media_type=kind)
            if extract:
                result["plot"]["wikipedia_extract"] = extract
                result["sources_checked"]["wikipedia"] = _source("ok")
            else:
                result["sources_checked"]["wikipedia"] = _source("empty")
        except RuntimeError:
            result["sources_checked"]["wikipedia"] = _source("unavailable")

    if settings.omdb_api_key:
        try:
            omdb = OMDbClient(settings.omdb_api_key)
            plot = omdb.plot_by_imdb(str(result["identity"]["imdb_id"] or "")) or omdb.plot_by_title(
                resolved_title, year=year
            )
            if plot:
                result["plot"]["omdb_plot"] = plot
                result["sources_checked"]["omdb"] = _source("ok")
            else:
                result["sources_checked"]["omdb"] = _source("empty")
        except RuntimeError:
            result["sources_checked"]["omdb"] = _source("unavailable")

    if settings.tvdb_api_key:
        if kind != "show" or not tvdb_id:
            result["sources_checked"]["tvdb"] = _source("not_applicable")
        else:
            try:
                details = TVDBClient(settings.tvdb_api_key).series(int(tvdb_id))
                result["sources_checked"]["tvdb"] = _source("ok" if details else "empty")
            except (RuntimeError, ValueError):
                result["sources_checked"]["tvdb"] = _source("unavailable")

    if not result["plot"]:
        result["warnings"].append("Configured research sources returned no plot text.")
    # Only provider-normalized metadata is stored. Caller-provided Plex paths,
    # tokens, and provider URLs are intentionally absent from this payload.
    _persist_research(
        result,
        db,
        entity_type="title",
        name=str(result["identity"]["title"] or resolved_title),
        external_ids={
            key: value for key, value in result["identity"].items()
            if key in {"tmdb_id", "tvdb_id", "imdb_id"} and value
        },
        library_item_id=library_item_id,
    )
    return result


def _filmography(credits: Mapping[str, Any]) -> list[Dict[str, Any]]:
    seen: set[tuple[str, int]] = set()
    entries: list[Dict[str, Any]] = []
    for credit_type in ("cast", "crew"):
        for entry in credits.get(credit_type, []) if isinstance(credits.get(credit_type), list) else []:
            if not isinstance(entry, Mapping) or entry.get("id") is None:
                continue
            media_type = str(entry.get("media_type") or "").lower()
            if media_type not in {"movie", "tv"}:
                continue
            key = (media_type, int(entry["id"]))
            if key in seen:
                continue
            seen.add(key)
            entries.append(
                {
                    "tmdb_id": int(entry["id"]),
                    "media_type": "show" if media_type == "tv" else "movie",
                    "title": str(entry.get("title") or entry.get("name") or ""),
                    "year": str(entry.get("release_date") or entry.get("first_air_date") or "")[:4],
                    "credit_type": credit_type,
                    "role": str(entry.get("character") or entry.get("job") or ""),
                }
            )
    return sorted(entries, key=lambda item: (item["year"], item["title"]), reverse=True)


def research_person(
    settings: Settings, *, name: str, tmdb_id: Optional[int] = None, db: Optional[Database] = None
) -> Dict[str, Any]:
    """Research a person through TMDB and retain only public, source-attributed facts."""
    result: Dict[str, Any] = {
        "identity": {"name": str(name).strip(), "tmdb_id": tmdb_id},
        "sources_checked": {"tmdb": _source("not_configured")},
        "profile": {},
        "filmography": [],
        "warnings": [],
    }
    if not settings.tmdb_api_key:
        return result
    try:
        client = TMDBClient(settings.tmdb_api_key)
        if not tmdb_id:
            matches = client.search_person(str(name))
            tmdb_id = int(matches[0]["id"]) if matches and matches[0].get("id") is not None else None
        details = client.person_details(int(tmdb_id), append_to_response="combined_credits") if tmdb_id else {}
        if not details:
            result["sources_checked"]["tmdb"] = _source("empty")
            return result
        result["identity"] = {"name": str(details.get("name") or name).strip(), "tmdb_id": int(details["id"])}
        result["profile"] = {
            "known_for_department": str(details.get("known_for_department") or ""),
            "biography": str(details.get("biography") or ""),
            "birthday": str(details.get("birthday") or ""),
            "place_of_birth": str(details.get("place_of_birth") or ""),
        }
        result["filmography"] = _filmography(details.get("combined_credits") or {})
        result["sources_checked"]["tmdb"] = _source("ok")
    except (RuntimeError, ValueError, KeyError):
        result["sources_checked"]["tmdb"] = _source("unavailable")
    _persist_research(
        result,
        db,
        entity_type="person",
        name=str(result["identity"]["name"]),
        external_ids={"tmdb_id": result["identity"]["tmdb_id"]} if result["identity"]["tmdb_id"] else {},
    )
    return result


def research_company(
    settings: Settings, *, name: str, tmdb_id: Optional[int] = None, db: Optional[Database] = None
) -> Dict[str, Any]:
    """Research a production company by its TMDB id without web scraping."""
    result: Dict[str, Any] = {
        "identity": {"name": str(name).strip(), "tmdb_id": tmdb_id},
        "sources_checked": {"tmdb": _source("not_configured")},
        "profile": {},
        "warnings": [],
    }
    if not settings.tmdb_api_key:
        return result
    if not tmdb_id:
        result["sources_checked"]["tmdb"] = _source("id_required")
        result["warnings"].append("TMDB company id is required; name-only company lookup is intentionally unsupported.")
        return result
    try:
        details = TMDBClient(settings.tmdb_api_key).company_details(int(tmdb_id))
        if not details:
            result["sources_checked"]["tmdb"] = _source("empty")
            return result
        result["identity"] = {"name": str(details.get("name") or name).strip(), "tmdb_id": int(details["id"])}
        result["profile"] = {
            "description": str(details.get("description") or ""),
            "headquarters": str(details.get("headquarters") or ""),
            "homepage": str(details.get("homepage") or ""),
            "origin_country": str(details.get("origin_country") or ""),
        }
        result["sources_checked"]["tmdb"] = _source("ok")
    except (RuntimeError, ValueError, KeyError):
        result["sources_checked"]["tmdb"] = _source("unavailable")
    _persist_research(
        result,
        db,
        entity_type="company",
        name=str(result["identity"]["name"]),
        external_ids={"tmdb_id": result["identity"]["tmdb_id"]} if result["identity"]["tmdb_id"] else {},
    )
    return result


def compare_filmographies(left: Mapping[str, Any], right: Mapping[str, Any]) -> Dict[str, Any]:
    """Compare two normalized research results without claiming subjective similarity."""
    left_titles = {(item["media_type"], item["tmdb_id"]) for item in left.get("filmography", [])}
    right_titles = {(item["media_type"], item["tmdb_id"]) for item in right.get("filmography", [])}
    return {
        "left": left.get("identity", {}),
        "right": right.get("identity", {}),
        "left_total": len(left_titles),
        "right_total": len(right_titles),
        "shared_credits": len(left_titles & right_titles),
        "left_only": len(left_titles - right_titles),
        "right_only": len(right_titles - left_titles),
    }
