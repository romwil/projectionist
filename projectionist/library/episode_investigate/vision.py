"""Constrained vision identification — this series → household shows → unknown."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from projectionist.library.episode_investigate.capabilities import llm_accepts_images

logger = logging.getLogger(__name__)

SCOPES = frozenset({"this_series", "household", "unknown"})
JSON_RE = re.compile(r"\{.*\}", re.DOTALL)

VISION_SYSTEM = (
    "You identify a TV episode from still frames. Reply with JSON only. "
    "Do not trust filenames or scene-release names — they are not evidence. "
    "Scope must be this_series, household, or unknown."
)


def vision_user_prompt(*, this_series: str, household_shows: Sequence[str]) -> str:
    house = ", ".join(str(title).strip() for title in household_shows if str(title).strip())
    house = house or "(none listed)"
    return (
        f"This investigation is for the series: {this_series}.\n"
        f"Household shows (if the stills are a different series): {house}.\n"
        "Look at the stills. Return JSON:\n"
        '{"scope":"this_series|household|unknown","series_title":"",'
        '"season":null,"episode":null,"episode_title":"","confidence":0.0,"reason":""}\n'
        "If the stills are this series, scope=this_series and pick season/episode. "
        "If they match another household show, scope=household. Otherwise unknown."
    )


def parse_vision_json(text: str) -> Dict[str, Any]:
    raw = str(text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    match = JSON_RE.search(raw)
    payload: Mapping[str, Any] = {}
    if match:
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            parsed = {}
        if isinstance(parsed, Mapping):
            payload = parsed
    scope = str(payload.get("scope") or "unknown").strip().lower()
    if scope not in SCOPES:
        scope = "unknown"
    try:
        confidence = float(payload.get("confidence") or 0)
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    season = _opt_int(payload.get("season"))
    episode = _opt_int(payload.get("episode"))
    return {
        "scope": scope,
        "series_title": str(payload.get("series_title") or "").strip(),
        "season": season,
        "episode": episode,
        "episode_title": str(payload.get("episode_title") or "").strip(),
        "confidence": confidence,
        "reason": str(payload.get("reason") or "").strip(),
    }


def _opt_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _image_messages(
    settings: Any,
    still_paths: Sequence[Path],
    prompt: str,
) -> List[Dict[str, Any]]:
    provider = str(getattr(settings, "llm_provider", "") or "").strip().lower()
    parts: List[Dict[str, Any]] = []
    for path in still_paths[:3]:
        try:
            blob = Path(path).read_bytes()
        except OSError:
            continue
        if not blob:
            continue
        b64 = base64.b64encode(blob).decode("ascii")
        if provider == "anthropic":
            parts.append(
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/jpeg", "data": b64},
                }
            )
        else:
            parts.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                }
            )
    if provider == "anthropic":
        parts.append({"type": "text", "text": prompt})
    else:
        parts.insert(0, {"type": "text", "text": prompt})
    return [
        {"role": "system", "content": VISION_SYSTEM},
        {"role": "user", "content": parts},
    ]


def _assistant_text(payload: Mapping[str, Any]) -> str:
    choices = payload.get("choices") if isinstance(payload, Mapping) else None
    if isinstance(choices, list) and choices:
        message = choices[0].get("message") if isinstance(choices[0], Mapping) else None
        if isinstance(message, Mapping):
            return str(message.get("content") or "")
    return ""


async def identify_from_stills_async(
    settings: Any,
    still_paths: Sequence[Path],
    *,
    this_series: str,
    household_shows: Sequence[str],
    chat=None,
) -> Dict[str, Any]:
    if not still_paths or not llm_accepts_images(settings):
        return parse_vision_json("")
    prompt = vision_user_prompt(this_series=this_series, household_shows=household_shows)
    messages = _image_messages(settings, still_paths, prompt)
    if chat is None:
        from projectionist.agent.providers import get_chat_provider

        chat = get_chat_provider(settings).chat
    payload = await chat(messages)
    return parse_vision_json(_assistant_text(payload if isinstance(payload, Mapping) else {}))


def identify_from_stills(
    settings: Any,
    still_paths: Sequence[Path],
    *,
    this_series: str,
    household_shows: Sequence[str],
    chat=None,
) -> Dict[str, Any]:
    try:
        return asyncio.run(
            identify_from_stills_async(
                settings,
                still_paths,
                this_series=this_series,
                household_shows=household_shows,
                chat=chat,
            )
        )
    except Exception as error:  # noqa: BLE001 — vision miss does not fail the job
        logger.info("vision identify failed: %s", error)
        parsed = parse_vision_json("")
        parsed["reason"] = str(error)[:200]
        return parsed
