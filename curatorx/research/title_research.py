"""Configured, provenance-aware media research for agent tools.

Only official JSON APIs are used here.  This is intentionally not a web browser.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

from curatorx.config_store import Settings
from curatorx.connectors.omdb import OMDbClient
from curatorx.connectors.tmdb import TMDBClient
from curatorx.connectors.tvdb import TVDBClient
from curatorx.connectors.wikipedia import fetch_extract
from curatorx.library.db import Database


def _source(status: str, **values: Any) -> Dict[str, Any]:
    return {"status": status, **values}


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
    if db is not None:
        # Only provider-normalized metadata is stored.  Caller-provided Plex paths,
        # tokens, and provider URLs are intentionally absent from this payload.
        result["memory"] = db.save_repository_research(
            entity_type="title",
            name=str(result["identity"]["title"] or resolved_title),
            payload=result,
            external_ids={
                key: value for key, value in result["identity"].items()
                if key in {"tmdb_id", "tvdb_id", "imdb_id"} and value
            },
            library_item_id=library_item_id,
        )
    return result
