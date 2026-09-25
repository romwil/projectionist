"""Fuse runtime / OSHash / vision. Filename and Sonarr SxxEyy are never evidence."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

CERTAIN = "certain"
LIKELY = "likely"
UNCERTAIN = "uncertain"
RUNTIME_ABS_SLACK = 90.0
RUNTIME_REL_SLACK = 0.08


def runtime_matches(file_seconds: Optional[float], episode_minutes: Optional[int]) -> bool:
    if file_seconds is None or episode_minutes is None:
        return False
    try:
        expected = float(episode_minutes) * 60.0
        actual = float(file_seconds)
    except (TypeError, ValueError):
        return False
    if expected <= 0 or actual <= 0:
        return False
    slack = max(RUNTIME_ABS_SLACK, expected * RUNTIME_REL_SLACK)
    return abs(actual - expected) <= slack


def _se_key(season: Any, episode: Any) -> Optional[Tuple[int, int]]:
    try:
        if season is None or episode is None:
            return None
        return int(season), int(episode)
    except (TypeError, ValueError):
        return None


def default_selected(confidence: str) -> bool:
    return str(confidence or "").strip().lower() in {CERTAIN, LIKELY}


def same_show_proposal(show: Mapping[str, Any], proposed: Mapping[str, Any]) -> bool:
    """Apply this sprint is same-show only."""
    if str(proposed.get("scope") or "") != "this_series":
        return False
    show_tmdb = show.get("tmdb_id")
    prop_tmdb = proposed.get("tmdb_id")
    if show_tmdb and prop_tmdb:
        try:
            return int(show_tmdb) == int(prop_tmdb)
        except (TypeError, ValueError):
            pass
    show_title = str(show.get("title") or "").strip().lower()
    prop_title = str(proposed.get("series_title") or show.get("title") or "").strip().lower()
    return bool(show_title) and show_title == prop_title


def household_has_series(
    *,
    title: str = "",
    tmdb_id: Any = None,
    household_titles: Sequence[str] = (),
    household_tmdb_ids: Sequence[Any] = (),
) -> bool:
    needle = str(title or "").strip().lower()
    if needle and any(str(item).strip().lower() == needle for item in household_titles):
        return True
    if tmdb_id in (None, ""):
        return False
    try:
        wanted = int(tmdb_id)
    except (TypeError, ValueError):
        return False
    for item in household_tmdb_ids:
        try:
            if int(item) == wanted:
                return True
        except (TypeError, ValueError):
            continue
    return False


def fuse_row(
    *,
    show: Mapping[str, Any],
    catalog: Sequence[Mapping[str, Any]],
    runtime_seconds: Optional[float],
    opensubtitles: Optional[Mapping[str, Any]],
    vision: Optional[Mapping[str, Any]],
    household_titles: Sequence[str] = (),
    household_tmdb_ids: Sequence[Any] = (),
    identify: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Pick a proposed episode and confidence from independent evidence only."""
    catalog_by_se = {}
    for entry in catalog:
        key = _se_key(entry.get("season"), entry.get("episode"))
        if key:
            catalog_by_se[key] = entry

    runtime_hits = [
        entry
        for entry in catalog
        if runtime_matches(runtime_seconds, entry.get("runtime_minutes"))
    ]
    runtime_key = None
    if len(runtime_hits) == 1:
        runtime_key = _se_key(runtime_hits[0].get("season"), runtime_hits[0].get("episode"))

    os_key = None
    os_same_show = False
    if isinstance(opensubtitles, Mapping) and opensubtitles.get("found"):
        os_key = _se_key(opensubtitles.get("season"), opensubtitles.get("episode"))
        parent = str(opensubtitles.get("series_title") or "").strip().lower()
        show_title = str(show.get("title") or "").strip().lower()
        os_same_show = bool(os_key) and (not parent or parent == show_title) and os_key in catalog_by_se

    vision_map = vision if isinstance(vision, Mapping) else {}
    vision_scope = str(vision_map.get("scope") or "unknown")
    vision_key = _se_key(vision_map.get("season"), vision_map.get("episode"))
    try:
        vision_conf = float(vision_map.get("confidence") or 0)
    except (TypeError, ValueError):
        vision_conf = 0.0
    vision_this = vision_scope == "this_series" and vision_key is not None

    votes: List[Tuple[str, Tuple[int, int]]] = []
    reasons: List[str] = []
    if runtime_key:
        votes.append(("runtime", runtime_key))
        reasons.append(f"runtime matches { _label(*runtime_key)}")
    if os_same_show and os_key:
        votes.append(("oshash", os_key))
        reasons.append(f"OpenSubtitles hash points at {_label(*os_key)}")
    if vision_this and vision_key:
        votes.append(("vision", vision_key))
        reasons.append("vision says this series")

    agreed = _majority_key(votes)
    confidence = UNCERTAIN
    proposed_key = agreed
    scope = "unknown"

    if agreed and _independent_agree(votes, agreed) >= 2:
        confidence = CERTAIN
        scope = "this_series"
    elif vision_this and vision_conf >= 0.6 and vision_key:
        proposed_key = vision_key
        scope = "this_series"
        confidence = CERTAIN if _independent_agree(votes, vision_key) >= 2 else LIKELY
    elif os_same_show and os_key:
        proposed_key = os_key
        scope = "this_series"
        confidence = LIKELY
    elif runtime_key:
        proposed_key = runtime_key
        scope = "this_series"
        confidence = LIKELY
    elif vision_scope == "household":
        scope = "household"
        confidence = UNCERTAIN
        reasons.append("vision matched a household show, not this series")
    else:
        if vision_scope == "unknown" and vision_map.get("reason"):
            reasons.append(str(vision_map.get("reason")))
        if not reasons:
            reasons.append("not enough independent evidence")

    catalog_hit = catalog_by_se.get(proposed_key) if proposed_key else None
    series_title = str(show.get("title") or "")
    if scope == "household":
        series_title = str(vision_map.get("series_title") or "") or _guess_household(
            vision_map.get("series_title"), household_titles
        )

    proposed = {
        "scope": scope,
        "series_title": series_title,
        "tmdb_id": show.get("tmdb_id") if scope == "this_series" else None,
        "season": proposed_key[0] if proposed_key and scope == "this_series" else vision_map.get("season"),
        "episode": proposed_key[1] if proposed_key and scope == "this_series" else vision_map.get("episode"),
        "title": "",
        "sonarr_episode_id": None,
        "tvdb_id": show.get("tvdb_id") if scope == "this_series" else None,
    }
    if catalog_hit and scope == "this_series":
        proposed["title"] = str(catalog_hit.get("title") or "")
        proposed["season"] = catalog_hit.get("season")
        proposed["episode"] = catalog_hit.get("episode")
        proposed["sonarr_episode_id"] = catalog_hit.get("sonarr_episode_id")
    elif vision_this:
        proposed["title"] = str(vision_map.get("episode_title") or "")

    identify_map = identify if isinstance(identify, Mapping) else {}
    new_show = False
    create_attach = False
    identify_same = False
    if identify_map.get("found"):
        mapped_title = str(identify_map.get("series_title") or "").strip()
        mapped_tmdb = identify_map.get("tmdb_id")
        identify_same = _identify_same_show(show, identify_map)
        if identify_same:
            reasons.append("Identify heard this series")
        elif identify_map.get("mapped") and (mapped_title or mapped_tmdb):
            in_house = household_has_series(
                title=mapped_title,
                tmdb_id=mapped_tmdb,
                household_titles=household_titles,
                household_tmdb_ids=household_tmdb_ids,
            )
            if in_house:
                if scope == "unknown":
                    scope = "household"
                    proposed["scope"] = "household"
                    proposed["series_title"] = mapped_title or _guess_household(
                        mapped_title, household_titles
                    )
                    proposed["tmdb_id"] = mapped_tmdb
                    proposed["tvdb_id"] = identify_map.get("tvdb_id")
                    confidence = UNCERTAIN
                reasons.append("Identify heard a household show")
            else:
                new_show = True
                create_attach = True
                if scope == "unknown":
                    scope = "new_show"
                    proposed["scope"] = "new_show"
                    proposed["series_title"] = mapped_title
                    proposed["tmdb_id"] = mapped_tmdb
                    proposed["tvdb_id"] = identify_map.get("tvdb_id")
                    confidence = UNCERTAIN
                reasons.append(
                    "Identify heard a series that is not in Plex or Sonarr — "
                    "applying would create and attach it"
                )
        else:
            reasons.append(
                "Identify heard a title that is not a known series"
                + (f" ({identify_map.get('title')})" if identify_map.get("title") else "")
            )
            if scope == "unknown":
                confidence = UNCERTAIN

    same = same_show_proposal(show, proposed)
    return {
        "proposed": proposed,
        "confidence": confidence,
        "reasons": reasons,
        "selected_default": default_selected(confidence) and same and not new_show,
        "same_show": same,
        "new_show": new_show,
        "create_attach": create_attach,
        "create_opt_in_required": new_show,
        "signals": {
            "runtime_key": list(runtime_key) if runtime_key else None,
            "oshash_key": list(os_key) if os_same_show and os_key else None,
            "vision_key": list(vision_key) if vision_this and vision_key else None,
            "identify_same_show": identify_same,
            "identify_title": str(identify_map.get("title") or "") or None,
        },
    }


def _identify_same_show(show: Mapping[str, Any], identify: Mapping[str, Any]) -> bool:
    show_tmdb = show.get("tmdb_id")
    ident_tmdb = identify.get("tmdb_id")
    if show_tmdb and ident_tmdb:
        try:
            if int(show_tmdb) == int(ident_tmdb):
                return True
        except (TypeError, ValueError):
            pass
    show_title = str(show.get("title") or "").strip().lower()
    ident_title = str(identify.get("series_title") or "").strip().lower()
    return bool(show_title) and show_title == ident_title


def _label(season: int, episode: int) -> str:
    return f"S{season:02d}E{episode:02d}"


def _independent_agree(votes: Sequence[Tuple[str, Tuple[int, int]]], key: Tuple[int, int]) -> int:
    lanes = {lane for lane, vote in votes if vote == key}
    return len(lanes)


def _majority_key(votes: Sequence[Tuple[str, Tuple[int, int]]]) -> Optional[Tuple[int, int]]:
    counts: Dict[Tuple[int, int], int] = {}
    for _, key in votes:
        counts[key] = counts.get(key, 0) + 1
    if not counts:
        return None
    best = max(counts.items(), key=lambda item: item[1])
    winners = [key for key, count in counts.items() if count == best[1]]
    return winners[0] if len(winners) == 1 else best[0] if best[1] > 1 else None


def _guess_household(title: Any, household_titles: Sequence[str]) -> str:
    needle = str(title or "").strip().lower()
    if not needle:
        return str(title or "")
    for candidate in household_titles:
        if str(candidate).strip().lower() == needle:
            return str(candidate)
    return str(title or "")
