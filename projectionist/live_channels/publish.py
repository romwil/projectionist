"""Publish starter recipes / collections to Tunarr via OpenAPI."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence

from projectionist.connectors.tunarr import TunarrClient
from projectionist.live_channels.recipes import (
    ChannelRecipe,
    ProgrammingMode,
    recipe_from_mapping,
)


def wire_plex_media_source(
    client: TunarrClient,
    *,
    plex_url: str,
    plex_token: str,
    name: str = "Plex",
) -> Dict[str, Any]:
    """Ensure a Plex media source exists in Tunarr (idempotent best-effort)."""
    url = str(plex_url or "").strip().rstrip("/")
    token = str(plex_token or "").strip()
    if not url or not token:
        return {
            "ok": False,
            "created": False,
            "message": "Plex URL and token are required to wire a media source.",
        }
    existing = client.list_media_sources()
    for source in existing:
        stype = str(source.get("type") or source.get("sourceType") or "").lower()
        uri = str(source.get("uri") or source.get("url") or "").rstrip("/")
        if stype == "plex" and (not uri or uri == url):
            return {
                "ok": True,
                "created": False,
                "id": source.get("id") or source.get("uuid"),
                "message": "Plex media source already present in Tunarr.",
                "source": dict(source),
            }
    body = {
        "name": name,
        "type": "plex",
        "uri": url,
        "accessToken": token,
    }
    created = client.create_media_source(body)
    return {
        "ok": True,
        "created": True,
        "id": created.get("id") or created.get("uuid"),
        "message": "Wired Plex as a Tunarr media source.",
        "source": dict(created),
    }


def channel_create_body(recipe: ChannelRecipe) -> Dict[str, Any]:
    """Tunarr ``POST /channels`` body for a new station."""
    return {
        "type": "new",
        "channel": {
            "name": recipe.name,
            "number": int(recipe.number),
            "stealth": False,
            "duration": 0,
        },
    }


def programming_body_for_recipe(recipe: ChannelRecipe) -> Optional[Dict[str, Any]]:
    """Best-effort programming payload.

    Full lineup resolution needs Tunarr program IDs from a scanned media source.
    When we only have recipe intent, return a minimal manual lineup shell so the
    channel exists; owners can re-publish after library wire/scan.
    """
    # Empty manual lineup — channel is created; programming filled later.
    # Chaos/shuffle modes are noted in summary; schedule-slots land when OpenAPI
    # program IDs are available from Tunarr's index.
    if recipe.item_hints:
        programs = [
            {"type": "flex", "duration": 300_000, "title": hint}
            for hint in recipe.item_hints[:50]
        ]
        return {"type": "manual", "programs": programs}
    if recipe.programming_mode in {ProgrammingMode.CHAOS, ProgrammingMode.SHUFFLE}:
        return {"type": "manual", "programs": []}
    return {"type": "manual", "programs": []}


def publish_recipes(
    client: TunarrClient,
    recipes: Sequence[ChannelRecipe | Mapping[str, Any]],
    *,
    skip_existing_numbers: bool = True,
) -> Dict[str, Any]:
    """Create channels (+ programming) for each recipe. Additive; does not wipe."""
    existing = client.list_channels()
    by_number = {
        int(ch.get("number") or 0): ch
        for ch in existing
        if ch.get("number") is not None
    }
    by_name = {
        str(ch.get("name") or "").strip().lower(): ch
        for ch in existing
        if str(ch.get("name") or "").strip()
    }

    published: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []

    for raw in recipes:
        recipe = raw if isinstance(raw, ChannelRecipe) else recipe_from_mapping(raw)
        key_name = recipe.name.strip().lower()
        if skip_existing_numbers and (
            recipe.number in by_number or key_name in by_name
        ):
            match = by_number.get(recipe.number) or by_name.get(key_name) or {}
            skipped.append(
                {
                    "name": recipe.name,
                    "number": recipe.number,
                    "reason": "already_exists",
                    "channel_id": match.get("id") or match.get("uuid"),
                }
            )
            continue
        try:
            created = client.create_channel(channel_create_body(recipe))
            channel_id = str(created.get("id") or created.get("uuid") or "")
            prog_body = programming_body_for_recipe(recipe)
            programming: Mapping[str, Any] = {}
            if channel_id and prog_body is not None:
                try:
                    programming = client.set_channel_programming(channel_id, prog_body)
                except Exception as prog_error:  # noqa: BLE001
                    programming = {"error": str(prog_error)[:200]}
            published.append(
                {
                    "name": recipe.name,
                    "number": recipe.number,
                    "source": recipe.source,
                    "channel_id": channel_id,
                    "channel": dict(created),
                    "programming": dict(programming) if programming else {},
                }
            )
            if recipe.number:
                by_number[recipe.number] = created
            if key_name:
                by_name[key_name] = created
        except Exception as error:  # noqa: BLE001
            errors.append(
                {
                    "name": recipe.name,
                    "number": recipe.number,
                    "error": str(error)[:240],
                }
            )

    ok = bool(published) and not errors
    if published and errors:
        ok = False
    if not published and not errors and skipped:
        ok = True  # idempotent re-publish

    return {
        "ok": ok or (bool(published) and not errors),
        "published": published,
        "skipped": skipped,
        "errors": errors,
        "count_published": len(published),
        "count_skipped": len(skipped),
        "count_errors": len(errors),
        "published_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def publish_collection_channel(
    client: TunarrClient,
    *,
    collection_id: str = "",
    collection_title: str = "",
    channel_number: int = 0,
    name: str = "",
) -> Dict[str, Any]:
    """Create a sequential station from a published collection/list title."""
    title = str(collection_title or name or "Collection").strip() or "Collection"
    number = int(channel_number or 0)
    if number <= 0:
        existing = client.list_channels()
        numbers = [int(ch.get("number") or 0) for ch in existing]
        number = max(numbers) + 1 if numbers else 100
    recipe = ChannelRecipe(
        name=title[:48],
        number=number,
        source="collection",
        programming_mode=ProgrammingMode.SEQUENTIAL,
        collection_id=str(collection_id or "").strip(),
        collection_title=title,
        summary=f"Sequential channel from collection “{title}”",
    )
    result = publish_recipes(client, [recipe], skip_existing_numbers=True)
    result["recipe"] = recipe.to_dict()
    return result


def tunarr_client_from_settings(settings: Any) -> TunarrClient:
    tunarr = getattr(settings, "tunarr", None)
    url = str(getattr(tunarr, "url", "") or "").strip() if tunarr else ""
    if not url:
        raise ValueError("Tunarr URL is not configured")
    return TunarrClient(url)
