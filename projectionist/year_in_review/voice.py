"""Curator-voiced Year in Review copy via the household LLM path."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence

from projectionist.config_store import Settings, validate_llm_settings
from projectionist.library.db import Database
from projectionist.notifications.good_news import persona_from_db
from projectionist.persona.display import curator_display_name
from projectionist.persona.prompt import build_assembled_persona_prompt

logger = logging.getLogger(__name__)

_JSON_OBJECT_RE = re.compile(r"\{[\s\S]*\}")
_MAX_MEMORY_NOTES = 6
_MAX_CHAT_SNIPPETS = 4
_MAX_TITLE_FACTS = 12
_OVERVIEW_CHARS = 180


def _default_persona(db: Database, *, user_id: str) -> Dict[str, Any]:
    template_id = None
    try:
        template_id = db.get_user_default_persona_id(user_id)
    except Exception:  # noqa: BLE001
        template_id = None
    if template_id:
        try:
            row = db.get_persona_template(str(template_id))
            if isinstance(row, dict) and row:
                return row
        except Exception:  # noqa: BLE001
            pass
    try:
        for persona in db.list_persona_templates() or []:
            if isinstance(persona, dict) and persona.get("is_default"):
                return persona
        personas = db.list_persona_templates() or []
        if personas and isinstance(personas[0], dict):
            return personas[0]
    except Exception:  # noqa: BLE001
        pass
    return {}


def _title_facts(db: Database, reel: Mapping[str, Any]) -> List[Dict[str, str]]:
    keys: List[str] = []
    for chapter in reel.get("chapters") or []:
        if not isinstance(chapter, dict):
            continue
        for poster in chapter.get("posters") or []:
            if not isinstance(poster, dict):
                continue
            key = str(poster.get("rating_key") or "").strip()
            if key and key not in keys:
                keys.append(key)
            if len(keys) >= _MAX_TITLE_FACTS:
                break
        if len(keys) >= _MAX_TITLE_FACTS:
            break
    if not keys:
        return []
    facts: List[Dict[str, str]] = []
    with db.connect() as conn:
        placeholders = ",".join("?" for _ in keys)
        rows = conn.execute(
            f"""
            SELECT rating_key, title, year, directors, "cast" AS cast_json,
                   COALESCE(NULLIF(tmdb_overview, ''), NULLIF(summary, ''), NULLIF(llm_logline, '')) AS overview
            FROM library_items
            WHERE rating_key IN ({placeholders})
            """,
            tuple(keys),
        ).fetchall()
    by_key = {str(r["rating_key"]): r for r in rows}
    for key in keys:
        row = by_key.get(key)
        if row is None:
            continue
        overview = str(row["overview"] or "").strip()
        if len(overview) > _OVERVIEW_CHARS:
            overview = overview[: _OVERVIEW_CHARS - 1].rstrip() + "…"
        directors = ""
        cast = ""
        try:
            directors = ", ".join(json.loads(row["directors"] or "[]")[:2])
        except (TypeError, ValueError, json.JSONDecodeError):
            directors = ""
        try:
            cast = ", ".join(json.loads(row["cast_json"] or "[]")[:3])
        except (TypeError, ValueError, json.JSONDecodeError):
            cast = ""
        facts.append(
            {
                "title": str(row["title"] or ""),
                "year": str(row["year"] or ""),
                "overview": overview,
                "directors": directors,
                "cast": cast,
            }
        )
    return facts


def _safe_memory_notes(
    db: Database,
    *,
    user_id: str,
    year: int,
    is_youth: bool,
) -> List[str]:
    if is_youth:
        return []
    start = datetime(int(year), 1, 1, tzinfo=timezone.utc).timestamp()
    end = datetime(int(year) + 1, 1, 1, tzinfo=timezone.utc).timestamp()
    notes: List[str] = []
    try:
        from projectionist.memory.service import UserMemoryService

        rows = UserMemoryService(db).recall(
            caller_id=user_id, caller_role="member", target_id=user_id, limit=40
        )
    except Exception:  # noqa: BLE001
        try:
            rows = db.list_user_memory_notes(user_id, limit=40)
        except Exception:  # noqa: BLE001
            return []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        created = float(row.get("created_at") or 0)
        if created and (created < start or created >= end):
            continue
        text = str(row.get("text") or "").strip()
        if not text:
            continue
        notes.append(text[:160])
        if len(notes) >= _MAX_MEMORY_NOTES:
            break
    return notes


def _safe_chat_snippets(
    db: Database,
    *,
    user_id: str,
    year: int,
    is_youth: bool,
) -> List[str]:
    if is_youth:
        return []
    start = datetime(int(year), 1, 1, tzinfo=timezone.utc).timestamp()
    end = datetime(int(year) + 1, 1, 1, tzinfo=timezone.utc).timestamp()
    snippets: List[str] = []
    try:
        threads = db.list_chat_threads(user_id=user_id, limit=12) or []
    except Exception:  # noqa: BLE001
        return []
    for thread in threads:
        if not isinstance(thread, dict):
            continue
        session_id = str(thread.get("id") or "").strip()
        if not session_id:
            continue
        try:
            messages = db.chat_history(session_id, limit=8) or []
        except Exception:  # noqa: BLE001
            continue
        for msg in messages:
            if not isinstance(msg, Mapping):
                continue
            if str(msg.get("role") or "") != "user":
                continue
            created = float(msg.get("created_at") or 0)
            if created and (created < start or created >= end):
                continue
            blocks = msg.get("blocks") or []
            texts = []
            for block in blocks if isinstance(blocks, list) else []:
                if isinstance(block, dict) and block.get("type") in (None, "text", "markdown"):
                    texts.append(str(block.get("text") or block.get("content") or "").strip())
            joined = " ".join(t for t in texts if t).strip()
            if not joined:
                continue
            snippets.append(joined[:140])
            if len(snippets) >= _MAX_CHAT_SNIPPETS:
                return snippets
    return snippets


def _response_text(response: Any) -> str:
    if response is None:
        return ""
    if isinstance(response, str):
        return response
    content = getattr(response, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text") or ""))
            else:
                parts.append(str(item))
        return "".join(parts)
    text = getattr(response, "text", None)
    if isinstance(text, str):
        return text
    return str(response)


def _extract_json_object(raw: str) -> Dict[str, Any]:
    text = str(raw or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        match = _JSON_OBJECT_RE.search(text)
        if not match:
            return {}
        try:
            parsed = json.loads(match.group(0))
            return parsed if isinstance(parsed, dict) else {}
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}


def _apply_voice_payload(reel: Dict[str, Any], payload: Mapping[str, Any]) -> None:
    chapters = list(reel.get("chapters") or [])
    by_id = {
        str(ch.get("id")): ch
        for ch in chapters
        if isinstance(ch, dict) and ch.get("id")
    }
    for item in payload.get("chapters") or []:
        if not isinstance(item, dict):
            continue
        chapter_id = str(item.get("id") or "").strip()
        body = str(item.get("body") or "").strip()
        title = str(item.get("title") or "").strip()
        target = by_id.get(chapter_id)
        if not target or not body:
            continue
        target["body"] = body
        if title:
            target["title"] = title
    recap = reel.get("recap")
    if isinstance(recap, dict):
        headline = str(payload.get("recap_headline") or "").strip()
        closing = str(payload.get("recap_closing") or "").strip()
        if headline:
            recap["headline"] = headline
        if closing:
            recap["curator_note"] = closing


async def _generate_voice_async(
    db: Database,
    settings: Settings,
    reel: Dict[str, Any],
    *,
    user_id: str,
    year: int,
    persona: Mapping[str, Any],
    title_facts: Sequence[Mapping[str, str]],
    memory_notes: Sequence[str],
    chat_snippets: Sequence[str],
) -> Dict[str, Any]:
    from projectionist.agent.providers import get_chat_provider
    from projectionist.telemetry import PURPOSE_YEAR_IN_REVIEW
    from projectionist.telemetry.llm_track import tracked_chat

    provider = get_chat_provider(settings)
    curator = curator_display_name(persona_from_db(db)[0], dict(persona) if persona else None)
    persona_prompt = ""
    try:
        if persona:
            persona_prompt = build_assembled_persona_prompt(dict(persona))
    except Exception:  # noqa: BLE001
        persona_prompt = ""

    chapter_lines = []
    for ch in reel.get("chapters") or []:
        if not isinstance(ch, dict):
            continue
        posters = ", ".join(
            str(p.get("title") or "")
            for p in (ch.get("posters") or [])[:8]
            if isinstance(p, dict)
        )
        chapter_lines.append(
            f"- id={ch.get('id')} kind={ch.get('kind')} title={ch.get('title')!r} "
            f"body={ch.get('body')!r} posters=[{posters}]"
        )
    facts_lines = []
    for fact in title_facts:
        bits = [fact.get("title") or ""]
        if fact.get("year"):
            bits.append(f"({fact['year']})")
        if fact.get("directors"):
            bits.append(f"dir: {fact['directors']}")
        if fact.get("cast"):
            bits.append(f"cast: {fact['cast']}")
        if fact.get("overview"):
            bits.append(fact["overview"])
        facts_lines.append(" · ".join(str(b) for b in bits if b))

    ratings = ((reel.get("rollup") or {}) if isinstance(reel.get("rollup"), dict) else {})
    # Prefer signals already on reel chapters / recap context via honesty — ratings live in chapters.
    rating_bits = []
    for ch in reel.get("chapters") or []:
        if isinstance(ch, dict) and ch.get("kind") == "ratings":
            rating_bits.append(str(ch.get("body") or ""))
    del ratings

    system = (
        f"You are {curator}, the household's personal Projectionist curator. "
        "Rewrite Year in Review chapter copy so it feels warm, personal, and specific. "
        "Keep every factual claim honest — do not invent finishes, ratings, or titles. "
        "You may lightly reference plots/creators from the provided title facts. "
        "Prefer rated favorites over mere rewatches when both appear. "
        "Never mention Youth, private household members, or anything outside this member's year. "
        "Return ONLY JSON: "
        '{"chapters":[{"id":"...","title":"...","body":"..."}],'
        '"recap_headline":"...","recap_closing":"..."} '
        "Include an entry for every chapter id you were given."
    )
    if persona_prompt:
        system += f"\n\nPersona guidance:\n{persona_prompt[:2500]}"

    user_prompt = (
        f"Member display name: {reel.get('display_name') or 'friend'}\n"
        f"Year: {year}\n"
        f"Chapters:\n" + "\n".join(chapter_lines) + "\n"
    )
    if facts_lines:
        user_prompt += "Title facts:\n" + "\n".join(f"- {line}" for line in facts_lines) + "\n"
    if rating_bits:
        user_prompt += "Ratings beat:\n" + "\n".join(rating_bits) + "\n"
    if memory_notes:
        user_prompt += "Member notes from this year (use sparingly):\n"
        user_prompt += "\n".join(f"- {n}" for n in memory_notes) + "\n"
    if chat_snippets:
        user_prompt += "Chat snippets from this year (use sparingly, no quotes of other people):\n"
        user_prompt += "\n".join(f"- {n}" for n in chat_snippets) + "\n"

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_prompt},
    ]
    response = await tracked_chat(
        db,
        provider,
        messages,
        purpose=PURPOSE_YEAR_IN_REVIEW,
        meta={"year": int(year), "user_id": user_id},
    )
    return _extract_json_object(_response_text(response))


def enrich_reel_with_curator_voice(
    db: Database,
    settings: Optional[Settings],
    reel: Dict[str, Any],
    *,
    user_id: str,
    year: int,
) -> Dict[str, Any]:
    """Rewrite chapter/recap copy in the household curator voice when LLM is configured.

    Honest fallback: leave template chapter bodies untouched and label ``voice.source``.
    Youth accounts never receive memory or chat snippets in the prompt.
    """
    curator_name, _ = persona_from_db(db)
    persona = _default_persona(db, user_id=user_id)
    display = curator_display_name(curator_name, persona or None)
    voice_meta: Dict[str, Any] = {
        "source": "template",
        "curator_name": display,
    }
    reel["voice"] = voice_meta

    if settings is None:
        return reel
    config_error = validate_llm_settings(settings)
    if config_error:
        voice_meta["fallback_reason"] = "llm_not_configured"
        return reel

    user_row = db.get_user(user_id)
    user = db._row_to_user(user_row) if user_row is not None else {}
    is_youth = bool(user.get("is_youth"))

    title_facts = _title_facts(db, reel)
    memory_notes = _safe_memory_notes(db, user_id=user_id, year=year, is_youth=is_youth)
    chat_snippets = _safe_chat_snippets(db, user_id=user_id, year=year, is_youth=is_youth)

    try:
        payload = asyncio.run(
            _generate_voice_async(
                db,
                settings,
                reel,
                user_id=user_id,
                year=year,
                persona=persona,
                title_facts=title_facts,
                memory_notes=memory_notes,
                chat_snippets=chat_snippets,
            )
        )
    except RuntimeError as exc:
        # Nested event loop (rare) — skip voice rather than crash generate.
        logger.info("YIR curator voice skipped (event loop): %s", exc)
        voice_meta["fallback_reason"] = "event_loop"
        return reel
    except Exception:  # noqa: BLE001
        logger.exception("YIR curator voice failed for %s", user_id)
        voice_meta["fallback_reason"] = "llm_error"
        return reel

    if not payload.get("chapters"):
        voice_meta["fallback_reason"] = "empty_response"
        return reel

    _apply_voice_payload(reel, payload)
    voice_meta["source"] = "curator_llm"
    voice_meta["used_memory"] = bool(memory_notes)
    voice_meta["used_chat"] = bool(chat_snippets)
    voice_meta["used_title_facts"] = bool(title_facts)
    return reel
