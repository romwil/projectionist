"""Publish starter recipes / collections to Tunarr via OpenAPI."""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence

from projectionist.connectors.tunarr import TunarrClient
from projectionist.live_channels.recipes import (
    ChannelRecipe,
    ProgrammingMode,
    recipe_from_mapping,
)

# Tunarr 1.3.x ``createChannelV2`` requires these channel fields (OpenAPI).
_DEFAULT_GROUP_TITLE = "Projectionist"
_DEFAULT_GUIDE_MINIMUM_DURATION_MS = 30_000
_DEFAULT_STREAM_MODE = "hls"


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


def channel_create_body(
    recipe: ChannelRecipe,
    *,
    transcode_config_id: str,
    channel_id: Optional[str] = None,
    start_time_ms: Optional[int] = None,
    group_title: str = _DEFAULT_GROUP_TITLE,
) -> Dict[str, Any]:
    """Tunarr ``POST /api/channels`` body for ``createChannelV2``.

    Tunarr 1.3.x rejects sparse bodies (HTTP 400). Required fields come from the
    live OpenAPI ``oneOf`` ``type=new`` branch — including a client-generated
    channel UUID and an existing ``transcodeConfigId``.
    """
    tcid = str(transcode_config_id or "").strip()
    if not tcid:
        raise ValueError("transcode_config_id is required to create a Tunarr channel")
    return {
        "type": "new",
        "channel": {
            "id": str(channel_id or uuid.uuid4()),
            "name": recipe.name,
            "number": int(recipe.number),
            "stealth": False,
            "duration": 0,
            "disableFillerOverlay": False,
            "groupTitle": str(group_title or _DEFAULT_GROUP_TITLE),
            "guideMinimumDuration": _DEFAULT_GUIDE_MINIMUM_DURATION_MS,
            "icon": {
                "path": "",
                "width": 0,
                "duration": 0,
                "position": "bottom-right",
            },
            "offline": {"mode": "pic"},
            "startTime": int(
                start_time_ms if start_time_ms is not None else time.time() * 1000
            ),
            "streamMode": _DEFAULT_STREAM_MODE,
            "transcodeConfigId": tcid,
            "subtitlesEnabled": False,
        },
    }


def programming_body_for_recipe(recipe: ChannelRecipe) -> Optional[Dict[str, Any]]:
    """Best-effort programming payload for ``POST …/programming``.

    Tunarr 1.3.x manual updates require ``lineup`` (array), not ``programs``.
    Full content entries need Tunarr program IDs from a scanned media source;
    until then we publish an empty (or flex-shell) lineup so create+set succeed.
    """
    # Flex shells are duration-only — OpenAPI has no ``title`` on flex items.
    # Item hints stay in the recipe summary until real program IDs exist.
    if recipe.item_hints:
        lineup = [
            {"type": "flex", "duration": 300_000}
            for _ in recipe.item_hints[:50]
        ]
        return {"type": "manual", "lineup": lineup}
    return {"type": "manual", "lineup": []}


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

    transcode_config_id = ""
    try:
        transcode_config_id = client.default_transcode_config_id()
    except Exception as error:  # noqa: BLE001
        return {
            "ok": False,
            "published": [],
            "skipped": [],
            "errors": [
                {
                    "name": "",
                    "number": 0,
                    "error": str(error)[:240],
                }
            ],
            "count_published": 0,
            "count_skipped": 0,
            "count_errors": 1,
            "published_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

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
            created = client.create_channel(
                channel_create_body(recipe, transcode_config_id=transcode_config_id)
            )
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
