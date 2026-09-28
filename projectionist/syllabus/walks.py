"""Scholar walks — lineage, canon, map, compare, seminar, consented gaps.

Walks stay in chat. They reuse the syllabus resume pointer, village consults,
and the footnote sheet. Nothing is published. Gap lists wait for confirm.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

WALK_KIND_LINEAGE = "lineage"
WALK_KIND_CANON = "canon"
WALK_KIND_MAP = "map"
WALK_KIND_COMPARE = "compare_two_rated"
WALK_KIND_SEMINAR = "silent_seminar"
WALK_KIND_GAPS = "gap_reading_list"

WALK_SPECS: Dict[str, Dict[str, str]] = {
    WALK_KIND_LINEAGE: {
        "label": "Lineage walk",
        "why": (
            "We follow influence and craft ancestry through titles already on the "
            "shelf or in a published course — not a public page."
        ),
        "footnote_prefix": "lineage",
        "sheet_label": "Lineage",
    },
    WALK_KIND_CANON: {
        "label": "Canon walk",
        "why": (
            "We read a household canon as a argued set, then mark what you already "
            "own. The list stays in this room."
        ),
        "footnote_prefix": "canon",
        "sheet_label": "Canon",
    },
    WALK_KIND_MAP: {
        "label": "Map walk",
        "why": (
            "We sketch a thematic map of a corpus you already opened — years, "
            "sessions, neighbors — so the next stop has a reason."
        ),
        "footnote_prefix": "map",
        "sheet_label": "Map",
    },
    WALK_KIND_COMPARE: {
        "label": "Compare two rated",
        "why": (
            "We only compare titles you have already scored, so the argument sits "
            "on your judgment rather than a stranger's ranking."
        ),
        "footnote_prefix": "compare",
        "sheet_label": "Compare",
    },
    WALK_KIND_SEMINAR: {
        "label": "Silent seminar",
        "why": (
            "A household seminar: The Professor leads, siblings may be asked by "
            "name, and nothing is published."
        ),
        "footnote_prefix": "seminar",
        "sheet_label": "Seminar",
    },
    WALK_KIND_GAPS: {
        "label": "Gap reading list",
        "why": (
            "Titles a published course names that are not on the shelf. We will "
            "not request, search, or add anything until you confirm."
        ),
        "footnote_prefix": "gap",
        "sheet_label": "Gap list",
    },
}

_KIND_ALIASES = {
    "lineage": WALK_KIND_LINEAGE,
    "canon": WALK_KIND_CANON,
    "map": WALK_KIND_MAP,
    "compare": WALK_KIND_COMPARE,
    "compare_two_rated": WALK_KIND_COMPARE,
    "compare-two-rated": WALK_KIND_COMPARE,
    "compare two rated": WALK_KIND_COMPARE,
    "compare two": WALK_KIND_COMPARE,
    "seminar": WALK_KIND_SEMINAR,
    "silent_seminar": WALK_KIND_SEMINAR,
    "silent seminar": WALK_KIND_SEMINAR,
    "gap": WALK_KIND_GAPS,
    "gaps": WALK_KIND_GAPS,
    "gap_reading_list": WALK_KIND_GAPS,
    "gap reading list": WALK_KIND_GAPS,
    "reading list": WALK_KIND_GAPS,
}

_WALK_HINTS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    (WALK_KIND_COMPARE, ("compare two", "compare-two", "two rated", "compare the two")),
    (WALK_KIND_SEMINAR, ("silent seminar", "seminar")),
    (WALK_KIND_GAPS, ("gap reading", "reading list", "gap list", "consented gap")),
    (WALK_KIND_LINEAGE, ("lineage", "who influenced", "influence tree")),
    (WALK_KIND_CANON, ("canon",)),
    (WALK_KIND_MAP, ("map the", "film map", "thematic map", "map of")),
)


def normalize_walk_kind(raw: Any) -> Optional[str]:
    text = " ".join(str(raw or "").strip().split()).casefold()
    if not text:
        return None
    if text in _KIND_ALIASES:
        return _KIND_ALIASES[text]
    for alias, kind in _KIND_ALIASES.items():
        if " " in alias and alias in text:
            return kind
    return None


def detect_walk_kind(text: Any) -> Optional[str]:
    """Conservative walk intent from a household question."""
    blob = " ".join(str(text or "").split()).casefold()
    if not blob:
        return None
    explicit = normalize_walk_kind(blob)
    if explicit:
        return explicit
    for kind, hints in _WALK_HINTS:
        if any(hint in blob for hint in hints):
            return kind
    return None


def walk_spec(kind: str) -> Dict[str, str]:
    return dict(WALK_SPECS[kind])


def walk_label(kind: str) -> str:
    return str(WALK_SPECS.get(kind, {}).get("label") or "Scholar walk")


def walk_why(kind: str) -> str:
    return str(WALK_SPECS.get(kind, {}).get("why") or "")


def footnote_prefix(kind: str) -> str:
    return str(WALK_SPECS.get(kind, {}).get("footnote_prefix") or "walk")


def _clean_topic(topic: Any) -> str:
    return " ".join(str(topic or "").split()).strip()[:160]


def _title_key(title: Any, tmdb_id: Any = None) -> str:
    if tmdb_id is not None and str(tmdb_id).strip():
        return f"tmdb:{tmdb_id}"
    return " ".join(str(title or "").split()).casefold()


def _stop(
    *,
    title: str,
    note: str = "",
    source: str = "",
    tmdb_id: Any = None,
    owned: Optional[bool] = None,
    extra: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "title": " ".join(str(title or "").split()).strip()[:160],
        "note": " ".join(str(note or "").split()).strip()[:400],
        "source": str(source or "").strip()[:80],
    }
    if tmdb_id is not None:
        payload["tmdb_id"] = tmdb_id
    if owned is not None:
        payload["owned"] = bool(owned)
    if extra:
        payload.update(dict(extra))
    return payload


def _citation_from_stop(kind: str, index: int, stop: Mapping[str, Any]) -> Dict[str, Any]:
    prefix = footnote_prefix(kind)
    ref = str(stop.get("title") or stop.get("source") or "source").strip()
    note = str(stop.get("note") or "").strip()
    return {
        "id": f"{prefix}-{index}",
        "source": str(stop.get("source") or "household"),
        "ref": ref,
        "note": note[:200],
    }


def scholar_walk_footnotes(walk: Mapping[str, Any]) -> List[str]:
    lines: List[str] = []
    for cite in list(walk.get("citations") or [])[:8]:
        cid = str(cite.get("id") or "").strip()
        ref = str(cite.get("ref") or cite.get("source") or "").strip()
        note = str(cite.get("note") or "").strip()
        if not cid or not (ref or note):
            continue
        lines.append(f"[^{cid}]: {ref}" + (f" — {note}" if note else ""))
    return lines


def scholar_walk_chat_prompt(walk: Mapping[str, Any]) -> str:
    kind = str(walk.get("kind") or "")
    spec = WALK_SPECS.get(kind) or {}
    label = str(walk.get("label") or spec.get("label") or "Scholar walk")
    why = str(walk.get("why") or spec.get("why") or "")
    topic = str(walk.get("topic") or "this corpus")
    focus = str(walk.get("focus_note") or "")
    if walk.get("needs_confirm"):
        return (
            f"I asked for a {label} on {topic}. {why} "
            f"{walk.get('confirm_message') or 'Confirm before you write the list.'} "
            "Do not request, search, or publish anything."
        )
    body = (
        f"Open a {label} on {topic}. {why} "
        f"{focus} Teach with rigor. Cite sources as footnote-style markdown "
        f"using the assigned ids (claim[^{footnote_prefix(kind)}-1]). "
        "Keep this in chat — no public page. Confirm before any fleet write."
    )
    footnotes = "\n".join(scholar_walk_footnotes(walk))
    if footnotes:
        body += f"\n\nAssigned sources:\n{footnotes}"
    resume = walk.get("resume") or {}
    if resume.get("resume_label"):
        body += f"\n\nSyllabus pointer: {resume['resume_label']}."
    return body


def walk_specialty_summary(walk: Mapping[str, Any]) -> Dict[str, Any]:
    """Compact village specialty payload — no raw dump for the household."""
    stops = list(walk.get("stops") or [])
    return {
        "kind": walk.get("kind"),
        "label": walk.get("label"),
        "why": walk.get("why"),
        "topic": walk.get("topic"),
        "needs_confirm": bool(walk.get("needs_confirm")),
        "public": False,
        "confirm_message": walk.get("confirm_message") or "",
        "stop_titles": [str(s.get("title") or "") for s in stops[:6] if s.get("title")],
        "citation_ids": [str(c.get("id") or "") for c in list(walk.get("citations") or [])[:6]],
        "resume_label": (walk.get("resume") or {}).get("resume_label"),
        "village": walk.get("village") or {},
    }


def _matching_courses(db: Any, topic: str) -> List[Dict[str, Any]]:
    if not hasattr(db, "list_published_lists"):
        return []
    rows = list(db.list_published_lists() or [])
    needle = topic.casefold()
    scored: List[Tuple[int, Dict[str, Any]]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        name = str(row.get("name") or row.get("title") or "").strip()
        kind = str(row.get("list_kind") or "")
        score = 0
        if needle and needle in name.casefold():
            score += 2
        if kind == "course":
            score += 1
        if not needle:
            score += 1
        if score <= 0:
            continue
        full = row
        list_id = str(row.get("id") or "")
        if list_id and hasattr(db, "get_published_list"):
            loaded = db.get_published_list(list_id, include_items=True)
            if loaded:
                full = loaded
        scored.append((score, full))
    scored.sort(key=lambda pair: (-pair[0], str(pair[1].get("name") or "")))
    return [row for _, row in scored[:4]]


def _library_neighbors(db: Any, topic: str, *, limit: int = 8) -> List[Dict[str, Any]]:
    cleaned = _clean_topic(topic)
    if not cleaned or not hasattr(db, "connect"):
        return []
    like = f"%{cleaned}%"
    try:
        with db.connect() as conn:
            rows = conn.execute(
                """
                SELECT title, year, media_type, tmdb_id, directors
                FROM library_items
                WHERE title LIKE ? COLLATE NOCASE
                   OR directors LIKE ? COLLATE NOCASE
                   OR genres LIKE ? COLLATE NOCASE
                ORDER BY year ASC, title ASC
                LIMIT ?
                """,
                (like, like, like, max(1, min(limit, 12))),
            ).fetchall()
    except Exception:
        return []
    neighbors: List[Dict[str, Any]] = []
    for row in rows:
        title = str(row["title"] or "").strip()
        if not title:
            continue
        year = row["year"]
        directors = str(row["directors"] or "").strip()
        note = directors or (str(year) if year else "on the shelf")
        neighbors.append(
            _stop(
                title=title,
                note=note[:200],
                source="library",
                tmdb_id=row["tmdb_id"],
                owned=True,
                extra={"year": year, "media_type": str(row["media_type"] or "")},
            )
        )
    return neighbors


def _memory_neighbors(db: Any, topic: str, *, limit: int = 4) -> List[Dict[str, Any]]:
    if not topic or not hasattr(db, "search_repository_memory"):
        return []
    try:
        hits = db.search_repository_memory(topic, limit=limit) or []
    except Exception:
        return []
    neighbors: List[Dict[str, Any]] = []
    for hit in hits:
        if not isinstance(hit, Mapping):
            continue
        name = str(hit.get("name") or hit.get("entity_name") or hit.get("title") or "").strip()
        if not name:
            continue
        entity_id = str(hit.get("entity_id") or hit.get("id") or "")
        insight_note = ""
        if entity_id and hasattr(db, "list_repository_insights"):
            try:
                insights = db.list_repository_insights(entity_id) or []
                if insights:
                    insight_note = str(insights[0].get("insight") or "")[:200]
            except Exception:
                insight_note = ""
        neighbors.append(
            _stop(
                title=name,
                note=insight_note or "cited neighbor from shared notes",
                source="repository",
            )
        )
    return neighbors


def _course_stops(course: Mapping[str, Any], *, owned_only: Optional[bool] = None) -> List[Dict[str, Any]]:
    stops: List[Dict[str, Any]] = []
    for item in list(course.get("items") or []):
        if not isinstance(item, Mapping):
            continue
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        owned = item.get("library_item_id") is not None
        if owned_only is True and not owned:
            continue
        if owned_only is False and owned:
            continue
        note = str(item.get("note") or "").strip() or str(course.get("name") or "course")
        stops.append(
            _stop(
                title=title,
                note=note[:200],
                source="course",
                tmdb_id=item.get("tmdb_id"),
                owned=owned,
            )
        )
    return stops


def _attach_resume(db: Any, *, user_id: str, list_id: Optional[str], walk: Dict[str, Any]) -> None:
    try:
        from projectionist.syllabus import course_resume_pointer

        pointer = course_resume_pointer(db, user_id=user_id, list_id=list_id)
    except Exception:
        pointer = None
    if not pointer:
        return
    walk["resume"] = {
        "list_id": pointer.get("list_id"),
        "course_name": pointer.get("course_name"),
        "session_id": pointer.get("session_id"),
        "resume_label": pointer.get("resume_label"),
        "completed": pointer.get("completed"),
        "remaining_sessions": pointer.get("remaining_sessions"),
    }


def _finalize_walk(
    kind: str,
    *,
    topic: str,
    stops: Sequence[Mapping[str, Any]],
    focus_note: str,
    extra: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    spec = walk_spec(kind)
    limited = [dict(stop) for stop in list(stops)[:8] if stop.get("title")]
    citations = [
        _citation_from_stop(kind, index, stop)
        for index, stop in enumerate(limited, start=1)
    ]
    walk: Dict[str, Any] = {
        "ok": True,
        "kind": kind,
        "label": spec["label"],
        "why": spec["why"],
        "topic": topic or spec["label"],
        "title": f"{spec['label']}: {topic}" if topic else spec["label"],
        "focus_note": focus_note[:2000],
        "stops": limited,
        "citations": citations,
        "needs_confirm": False,
        "public": False,
        "confirm_message": "",
    }
    if extra:
        walk.update(dict(extra))
    walk["chat_prompt"] = scholar_walk_chat_prompt(walk)
    return walk


def _empty_walk(kind: str, *, topic: str, message: str) -> Dict[str, Any]:
    spec = walk_spec(kind)
    walk = {
        "ok": False,
        "kind": kind,
        "label": spec["label"],
        "why": spec["why"],
        "topic": topic or spec["label"],
        "title": spec["label"],
        "focus_note": message,
        "stops": [],
        "citations": [],
        "needs_confirm": False,
        "public": False,
        "confirm_message": "",
        "message": message,
    }
    walk["chat_prompt"] = scholar_walk_chat_prompt(walk)
    return walk


def _named_titles(titles: Iterable[Any]) -> List[str]:
    out: List[str] = []
    seen = set()
    for raw in titles:
        title = " ".join(str(raw or "").split()).strip()
        key = title.casefold()
        if not title or key in seen:
            continue
        seen.add(key)
        out.append(title)
    return out


def _build_lineage(db: Any, *, user_id: str, topic: str, titles: Sequence[str]) -> Dict[str, Any]:
    courses = _matching_courses(db, topic)
    course_stops: List[Dict[str, Any]] = []
    list_id = None
    if courses:
        course_stops = _course_stops(courses[0], owned_only=None)
        list_id = str(courses[0].get("id") or "") or None
    named = [_stop(title=title, note=f"Named for the {topic or 'lineage'} walk", source="request") for title in titles]
    neighbors = _library_neighbors(db, topic) + _memory_neighbors(db, topic)
    stops = _dedupe_stops(named + course_stops + neighbors)
    if not stops:
        return _empty_walk(
            WALK_KIND_LINEAGE,
            topic=topic,
            message=(
                f"No household lineage yet for {topic or 'that name'} — "
                "open a published course or name a title on the shelf."
            ),
        )
    focus = (
        f"Walk influence for {topic or 'this corpus'}. Start with "
        f"{stops[0]['title']} and keep each stop cited."
    )
    walk = _finalize_walk(WALK_KIND_LINEAGE, topic=topic, stops=stops, focus_note=focus)
    _attach_resume(db, user_id=user_id, list_id=list_id, walk=walk)
    walk["chat_prompt"] = scholar_walk_chat_prompt(walk)
    return walk


def _build_canon(db: Any, *, user_id: str, topic: str, titles: Sequence[str]) -> Dict[str, Any]:
    courses = _matching_courses(db, topic)
    if not courses:
        return _empty_walk(
            WALK_KIND_CANON,
            topic=topic,
            message=(
                f"No published course to treat as a canon for {topic or 'that topic'} yet."
            ),
        )
    course = courses[0]
    stops = _course_stops(course)
    for title in titles:
        if not any(s["title"].casefold() == title.casefold() for s in stops):
            stops.append(_stop(title=title, note="Named for the canon walk", source="request"))
    owned = sum(1 for stop in stops if stop.get("owned"))
    focus = (
        f"Treat “{course.get('name') or topic}” as a household canon. "
        f"{owned} of {len(stops)} stops are already on the shelf. Argue inclusion, "
        "do not publish a page."
    )
    walk = _finalize_walk(
        WALK_KIND_CANON,
        topic=topic or str(course.get("name") or ""),
        stops=stops,
        focus_note=focus,
        extra={"course_name": course.get("name"), "list_id": course.get("id"), "owned_count": owned},
    )
    _attach_resume(db, user_id=user_id, list_id=str(course.get("id") or "") or None, walk=walk)
    walk["chat_prompt"] = scholar_walk_chat_prompt(walk)
    return walk


def _build_map(db: Any, *, user_id: str, topic: str, titles: Sequence[str]) -> Dict[str, Any]:
    courses = _matching_courses(db, topic)
    list_id = None
    regions: List[Dict[str, Any]] = []
    if courses:
        list_id = str(courses[0].get("id") or "") or None
        items = list(courses[0].get("items") or [])
        if items:
            third = max(1, (len(items) + 2) // 3)
            labels = ("Origins", "Middle passage", "Late style")
            for index, label in enumerate(labels):
                chunk = items[index * third : (index + 1) * third]
                if not chunk:
                    continue
                names = [str(it.get("title") or "").strip() for it in chunk if it.get("title")]
                if not names:
                    continue
                regions.append(
                    _stop(
                        title=label,
                        note=", ".join(names[:4]),
                        source="course",
                        extra={"region": label, "titles": names[:6]},
                    )
                )
    if not regions:
        neighbors = _library_neighbors(db, topic, limit=9)
        if titles:
            neighbors = [_stop(title=t, note="Named map stop", source="request") for t in titles] + neighbors
        labels = ("Origins", "Middle passage", "Late style")
        if neighbors:
            third = max(1, (len(neighbors) + 2) // 3)
            for index, label in enumerate(labels):
                chunk = neighbors[index * third : (index + 1) * third]
                if not chunk:
                    continue
                names = [str(s.get("title") or "") for s in chunk]
                regions.append(
                    _stop(
                        title=label,
                        note=", ".join(names[:4]),
                        source="library",
                        extra={"region": label, "titles": names},
                    )
                )
    if not regions:
        return _empty_walk(
            WALK_KIND_MAP,
            topic=topic,
            message=f"Nothing to map yet for {topic or 'that corpus'}.",
        )
    focus = (
        f"Sketch a three-region map of {topic or 'this corpus'}. "
        "Name why a title sits in Origins, Middle passage, or Late style."
    )
    walk = _finalize_walk(WALK_KIND_MAP, topic=topic, stops=regions, focus_note=focus)
    _attach_resume(db, user_id=user_id, list_id=list_id, walk=walk)
    walk["chat_prompt"] = scholar_walk_chat_prompt(walk)
    return walk


def _reviews_for_compare(
    db: Any,
    *,
    user_id: str,
    titles: Sequence[str],
) -> List[Dict[str, Any]]:
    from projectionist.reviews.store import get_reviews

    reviews = get_reviews(db, user_id=user_id, limit=40)
    if titles:
        picked: List[Dict[str, Any]] = []
        for title in titles[:2]:
            needle = title.casefold()
            match = next(
                (
                    row
                    for row in reviews
                    if needle in str(row.get("title") or "").casefold()
                ),
                None,
            )
            if match:
                picked.append(match)
        if len(picked) >= 2:
            return picked[:2]
    return [row for row in reviews if row.get("stars") is not None][:2]


def _build_compare(db: Any, *, user_id: str, topic: str, titles: Sequence[str]) -> Dict[str, Any]:
    pair = _reviews_for_compare(db, user_id=user_id, titles=titles)
    if len(pair) < 2:
        return _empty_walk(
            WALK_KIND_COMPARE,
            topic=topic,
            message=(
                "Compare two rated needs two titles you have already scored. "
                "Rate a pair first — we will not invent a ranking."
            ),
        )
    stops = []
    for row in pair:
        stars = row.get("stars")
        text = str(row.get("review_text") or "").strip()
        note = f"{stars:g}★" if stars is not None else "rated"
        if text:
            note = f"{note} — {text[:160]}"
        stops.append(
            _stop(
                title=str(row.get("title") or "Untitled"),
                note=note,
                source="review",
                tmdb_id=row.get("tmdb_id"),
                extra={"stars": stars},
            )
        )
    left, right = stops[0]["title"], stops[1]["title"]
    focus = (
        f"Compare {left} and {right} from the ratings already on file. "
        "Explain the why — form, context, and what the scores disagree about."
    )
    return _finalize_walk(
        WALK_KIND_COMPARE,
        topic=topic or f"{left} / {right}",
        stops=stops,
        focus_note=focus,
        extra={"compared_titles": [left, right]},
    )


def _build_seminar(db: Any, *, user_id: str, topic: str, titles: Sequence[str]) -> Dict[str, Any]:
    courses = _matching_courses(db, topic)
    list_id = str((courses[0] or {}).get("id") or "") or None if courses else None
    agenda = _course_stops(courses[0]) if courses else []
    if titles:
        agenda = [_stop(title=t, note="Seminar prompt", source="request") for t in titles] + agenda
    if not agenda:
        agenda = _library_neighbors(db, topic, limit=4)
    if not agenda:
        agenda = [
            _stop(
                title=topic or "Open seminar",
                note="One cited question, then a sibling may be asked by name.",
                source="seminar",
            )
        ]
    focus = (
        f"Hold a silent seminar on {topic or 'this corpus'}. The Professor leads. "
        "If a sibling is needed, ask once and quote them. Do not publish a page."
    )
    walk = _finalize_walk(
        WALK_KIND_SEMINAR,
        topic=topic,
        stops=agenda[:6],
        focus_note=focus,
        extra={
            "village": {
                "lead": "The Professor",
                "invite": ["The Professor"],
                "quote": True,
                "public": False,
            }
        },
    )
    _attach_resume(db, user_id=user_id, list_id=list_id, walk=walk)
    walk["chat_prompt"] = scholar_walk_chat_prompt(walk)
    return walk


def _build_gaps(
    db: Any,
    *,
    user_id: str,
    topic: str,
    titles: Sequence[str],
    confirm: bool,
) -> Dict[str, Any]:
    courses = _matching_courses(db, topic)
    if not courses:
        return _empty_walk(
            WALK_KIND_GAPS,
            topic=topic,
            message=(
                f"No published course to read for gaps on {topic or 'that topic'}. "
                "We will not invent a shopping list."
            ),
        )
    course = courses[0]
    gaps = _course_stops(course, owned_only=False)
    named_missing = [
        _stop(title=title, note="Named gap", source="request", owned=False)
        for title in titles
        if not any(s["title"].casefold() == title.casefold() for s in _course_stops(course, owned_only=True))
    ]
    stops = _dedupe_stops(named_missing + gaps)
    spec = walk_spec(WALK_KIND_GAPS)
    confirm_message = (
        f"Draft a gap reading list of {len(stops)} title"
        f"{'' if len(stops) == 1 else 's'} from “{course.get('name') or topic}” "
        "that are not on the shelf? Confirm to write the list. "
        "This does not request, search, or add anything."
    )
    if not confirm:
        walk = {
            "ok": False,
            "kind": WALK_KIND_GAPS,
            "label": spec["label"],
            "why": spec["why"],
            "topic": topic or str(course.get("name") or ""),
            "title": spec["label"],
            "focus_note": spec["why"],
            "stops": [],
            "citations": [],
            "needs_confirm": True,
            "public": False,
            "proposed_count": len(stops),
            "course_name": course.get("name"),
            "list_id": course.get("id"),
            "confirm_message": confirm_message,
            "message": confirm_message,
        }
        walk["chat_prompt"] = scholar_walk_chat_prompt(walk)
        return walk
    if not stops:
        return _empty_walk(
            WALK_KIND_GAPS,
            topic=topic or str(course.get("name") or ""),
            message=f"“{course.get('name') or topic}” has no off-shelf titles to list.",
        )
    focus = (
        f"Consented gap list for “{course.get('name') or topic}”. "
        "These titles are named by the course and missing from the shelf. "
        "Do not request or search unless the household confirms a later fleet action."
    )
    walk = _finalize_walk(
        WALK_KIND_GAPS,
        topic=topic or str(course.get("name") or ""),
        stops=stops,
        focus_note=focus,
        extra={
            "needs_confirm": False,
            "course_name": course.get("name"),
            "list_id": course.get("id"),
            "proposed_count": len(stops),
        },
    )
    _attach_resume(db, user_id=user_id, list_id=str(course.get("id") or "") or None, walk=walk)
    walk["chat_prompt"] = scholar_walk_chat_prompt(walk)
    return walk


def _dedupe_stops(stops: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen = set()
    for stop in stops:
        title = str(stop.get("title") or "").strip()
        if not title:
            continue
        key = _title_key(title, stop.get("tmdb_id"))
        if key in seen:
            continue
        seen.add(key)
        out.append(dict(stop))
    return out


def build_scholar_walk(
    db: Any,
    *,
    user_id: str,
    kind: Any,
    topic: str = "",
    titles: Sequence[Any] = (),
    confirm: bool = False,
) -> Dict[str, Any]:
    """Build a household Scholar walk. Gap lists require ``confirm=True``."""
    normalized = normalize_walk_kind(kind) or detect_walk_kind(kind)
    if not normalized:
        return {
            "ok": False,
            "kind": None,
            "label": "Scholar walk",
            "why": "Walks stay in chat and wait for a named kind.",
            "topic": _clean_topic(topic),
            "stops": [],
            "citations": [],
            "needs_confirm": False,
            "public": False,
            "message": (
                "Name a walk: lineage, canon, map, compare-two-rated, "
                "silent seminar, or a consented gap reading list."
            ),
        }
    cleaned_topic = _clean_topic(topic)
    named = _named_titles(titles)
    if normalized == WALK_KIND_LINEAGE:
        return _build_lineage(db, user_id=user_id, topic=cleaned_topic, titles=named)
    if normalized == WALK_KIND_CANON:
        return _build_canon(db, user_id=user_id, topic=cleaned_topic, titles=named)
    if normalized == WALK_KIND_MAP:
        return _build_map(db, user_id=user_id, topic=cleaned_topic, titles=named)
    if normalized == WALK_KIND_COMPARE:
        return _build_compare(db, user_id=user_id, topic=cleaned_topic, titles=named)
    if normalized == WALK_KIND_SEMINAR:
        return _build_seminar(db, user_id=user_id, topic=cleaned_topic, titles=named)
    return _build_gaps(
        db,
        user_id=user_id,
        topic=cleaned_topic,
        titles=named,
        confirm=bool(confirm),
    )
