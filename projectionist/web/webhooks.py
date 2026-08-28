"""Inbound webhooks for real-time watch completion detection."""

from __future__ import annotations

import json
import logging
import secrets
from typing import Any, Callable, Dict, Mapping, Optional

from fastapi import APIRouter, HTTPException, Request

from projectionist.config_store import Settings
from projectionist.library.db import Database
from projectionist.library.db_io import run_db
from projectionist.reviews.store import COMPLETION_THRESHOLD, queue_rating_prompt

logger = logging.getLogger(__name__)

router = APIRouter(tags=["webhooks"])

SUPPORTED_EVENTS = frozenset({"media.stop", "media.scrobble", "media.pause"})
SUPPORTED_MEDIA_TYPES = frozenset({"movie", "episode"})


def completion_from_plex_metadata(metadata: Mapping[str, Any]) -> Optional[float]:
    view_offset = metadata.get("viewOffset")
    duration = metadata.get("duration")
    if view_offset is None or duration is None:
        return None
    try:
        view_ms = int(view_offset)
        duration_ms = int(duration)
    except (TypeError, ValueError):
        return None
    if duration_ms <= 0:
        return None
    return min(100.0, (float(view_ms) / float(duration_ms)) * 100.0)


def title_from_plex_metadata(metadata: Mapping[str, Any]) -> str:
    media_type = str(metadata.get("type") or "").strip().lower()
    if media_type == "episode":
        show_title = str(metadata.get("grandparentTitle") or metadata.get("title") or "Unknown")
        season = int(metadata.get("parentIndex") or 0)
        episode = int(metadata.get("index") or 0)
        return f"{show_title} — S{season:02d}E{episode:02d}"
    return str(metadata.get("title") or "Unknown")


def media_type_from_plex_metadata(metadata: Mapping[str, Any]) -> str:
    media_type = str(metadata.get("type") or "").strip().lower()
    if media_type == "episode":
        return "show"
    return "movie"


async def parse_plex_webhook_payload(request: Request) -> Dict[str, Any]:
    content_type = str(request.headers.get("content-type") or "").lower()
    if "application/json" in content_type:
        payload = await request.json()
        if isinstance(payload, dict):
            return payload
        raise HTTPException(status_code=400, detail="Invalid Plex webhook JSON payload")

    form = await request.form()
    raw_payload = form.get("payload")
    if raw_payload is None:
        raise HTTPException(status_code=400, detail="Missing Plex webhook payload")
    try:
        payload = json.loads(str(raw_payload))
    except json.JSONDecodeError as error:
        raise HTTPException(status_code=400, detail="Invalid Plex webhook payload JSON") from error
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid Plex webhook payload")
    return payload


def handle_plex_webhook(db: Database, payload: Mapping[str, Any]) -> Dict[str, Any]:
    event = str(payload.get("event") or "").strip().lower()
    if event not in SUPPORTED_EVENTS:
        return {"handled": False, "reason": "ignored_event", "event": event}

    metadata = payload.get("Metadata")
    if not isinstance(metadata, dict):
        return {"handled": False, "reason": "missing_metadata", "event": event}

    plex_type = str(metadata.get("type") or "").strip().lower()
    if plex_type not in SUPPORTED_MEDIA_TYPES:
        return {"handled": False, "reason": "unsupported_media_type", "event": event, "type": plex_type}

    rating_key = str(metadata.get("ratingKey") or "").strip()
    if not rating_key:
        return {"handled": False, "reason": "missing_rating_key", "event": event}

    # Always attempt watch-tracker ingest for supported playback events (even below prompt gate).
    tracker_ingested = False
    try:
        from projectionist.watch_tracker.store import ingest_watch_events
        from projectionist.watch_tracker.webhook_adapter import webhook_to_watch_event

        server = payload.get("Server") if isinstance(payload.get("Server"), Mapping) else {}
        server_machine_id = str(
            server.get("uuid") or server.get("machineIdentifier") or "unknown"
        ).strip()
        watch_event = webhook_to_watch_event(payload, server_machine_id=server_machine_id)
        if watch_event is not None:
            ingest_result = ingest_watch_events(db, [watch_event])
            tracker_ingested = ingest_result.inserted > 0 or ingest_result.deduped > 0
    except Exception:  # noqa: BLE001
        logger.debug("Watch tracker webhook ingest failed", exc_info=True)

    completion_pct = completion_from_plex_metadata(metadata)
    if event == "media.scrobble" and (completion_pct is None or completion_pct < COMPLETION_THRESHOLD):
        completion_pct = 90.0
    if completion_pct is None or completion_pct < COMPLETION_THRESHOLD:
        return {
            "handled": False,
            "reason": "below_threshold",
            "event": event,
            "completion_pct": completion_pct,
            "tracker_ingested": tracker_ingested,
        }

    title = title_from_plex_metadata(metadata)
    media_type = media_type_from_plex_metadata(metadata)

    account = payload.get("Account") if isinstance(payload.get("Account"), Mapping) else {}
    plex_account_id = account.get("id")
    user_id: Optional[str] = None
    if plex_account_id is not None:
        row = db.get_user_by_plex_id(str(plex_account_id))
        if row is not None:
            user_id = str(row["id"])
    if not user_id:
        # Fail closed: never queue server-token / anonymous watches as personal nudges.
        return {
            "handled": True,
            "queued": False,
            "reason": "unattributed_account",
            "event": event,
            "rating_key": rating_key,
            "title": title,
            "completion_pct": completion_pct,
            "tracker_ingested": tracker_ingested,
        }

    queued = queue_rating_prompt(
        db,
        rating_key=rating_key,
        media_type=media_type,
        title=title,
        completion_pct=completion_pct,
        user_id=user_id,
    )
    return {
        "handled": True,
        "queued": queued,
        "event": event,
        "rating_key": rating_key,
        "title": title,
        "completion_pct": completion_pct,
        "user_id": user_id,
        "tracker_ingested": tracker_ingested,
    }


def register_webhook_routes(
    app,
    *,
    db_factory: Callable[[], Database],
    settings_factory: Callable[[], Settings],
) -> None:
    @router.post("/api/webhooks/plex")
    async def plex_webhook(request: Request) -> Dict[str, Any]:
        settings = settings_factory()
        secret = str(settings.webhook_secret or "").strip()
        provided = str(request.headers.get("X-Projectionist-Webhook-Secret") or "").strip()
        # Unconfigured and invalid both fail closed as generic 401 — no env names.
        if not secret or not provided or not secrets.compare_digest(provided, secret):
            raise HTTPException(status_code=401, detail="Unauthorized")
        payload = await parse_plex_webhook_payload(request)
        # Offload sync sqlite (user lookup + prompt enqueue) from the event loop.
        result = await run_db(handle_plex_webhook, db_factory(), payload)
        logger.info(
            "Plex webhook event=%s handled=%s queued=%s rating_key=%s",
            result.get("event") or payload.get("event"),
            result.get("handled"),
            result.get("queued"),
            result.get("rating_key"),
        )
        if result.get("handled"):
            try:
                from projectionist.telemetry import TelemetryIngester

                TelemetryIngester(db_factory()).record_playback_event(
                    event=str(result.get("event") or ""),
                    rating_key=str(result.get("rating_key") or ""),
                    completion_pct=result.get("completion_pct"),
                    media_type=result.get("media_type"),
                )
            except Exception:
                logger.debug("Telemetry playback record failed", exc_info=True)
        return result

    app.include_router(router)
