"""Local TMDB keyword → controlled theme vocabulary (no LLM).

Maps frequent keyword phrases onto a small curated theme set written as
``library_facets`` rows with ``facet_type='theme'``. Never invents themes
outside this table — unknown keywords are ignored.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Mapping, Set

# Controlled theme vocabulary (values written to library_facets).
CONTROLLED_THEMES = frozenset(
    {
        "revenge",
        "martial arts",
        "heist",
        "time travel",
        "found family",
        "coming of age",
        "survival",
        "dystopia",
        "space",
        "supernatural",
        "serial killer",
        "courtroom",
        "political intrigue",
        "war",
        "romance",
        "friendship",
        "betrayal",
        "identity",
        "memory",
        "grief",
        "redemption",
        "conspiracy",
        "body horror",
        "cyberpunk",
        "western",
        "road trip",
        "underdog",
        "chosen one",
        "artificial intelligence",
        "environmental",
    }
)

# Lowercased TMDB keyword / phrase → controlled theme.
# Prefer multi-word phrases; unigrams fill gaps for high-signal stems.
KEYWORD_TO_THEME: Dict[str, str] = {
    # revenge
    "revenge": "revenge",
    "vengeance": "revenge",
    "vendetta": "revenge",
    "payback": "revenge",
    "retribution": "revenge",
    # martial arts
    "martial arts": "martial arts",
    "kung fu": "martial arts",
    "karate": "martial arts",
    "samurai": "martial arts",
    "sword fight": "martial arts",
    "ninja": "martial arts",
    # heist
    "heist": "heist",
    "bank robbery": "heist",
    "robbery": "heist",
    "caper": "heist",
    "thief": "heist",
    # time travel
    "time travel": "time travel",
    "time machine": "time travel",
    "time loop": "time travel",
    "alternate timeline": "time travel",
    # found family
    "found family": "found family",
    "unlikely friendship": "found family",
    "team of misfits": "found family",
    # coming of age
    "coming of age": "coming of age",
    "teenager": "coming of age",
    "high school": "coming of age",
    "adolescence": "coming of age",
    # survival
    "survival": "survival",
    "stranded": "survival",
    "wilderness": "survival",
    "disaster": "survival",
    # dystopia
    "dystopia": "dystopia",
    "dystopian future": "dystopia",
    "post-apocalyptic": "dystopia",
    "post apocalyptic": "dystopia",
    "totalitarian": "dystopia",
    # space
    "space": "space",
    "outer space": "space",
    "spaceship": "space",
    "astronaut": "space",
    "alien": "space",
    "aliens": "space",
    # supernatural
    "supernatural": "supernatural",
    "ghost": "supernatural",
    "haunting": "supernatural",
    "demon": "supernatural",
    "witch": "supernatural",
    "vampire": "supernatural",
    "werewolf": "supernatural",
    # serial killer
    "serial killer": "serial killer",
    "slasher": "serial killer",
    # courtroom
    "courtroom": "courtroom",
    "lawyer": "courtroom",
    "trial": "courtroom",
    "legal drama": "courtroom",
    # political intrigue
    "politics": "political intrigue",
    "political intrigue": "political intrigue",
    "espionage": "political intrigue",
    "spy": "political intrigue",
    "cold war": "political intrigue",
    # war
    "war": "war",
    "world war ii": "war",
    "world war i": "war",
    "soldier": "war",
    "battlefield": "war",
    # romance
    "love": "romance",
    "romance": "romance",
    "romantic": "romance",
    "love triangle": "romance",
    # friendship
    "friendship": "friendship",
    "best friends": "friendship",
    # betrayal
    "betrayal": "betrayal",
    "traitor": "betrayal",
    # identity
    "identity": "identity",
    "secret identity": "identity",
    "mistaken identity": "identity",
    # memory
    "amnesia": "memory",
    "memory": "memory",
    "memory loss": "memory",
    # grief
    "grief": "grief",
    "loss of loved one": "grief",
    "mourning": "grief",
    # redemption
    "redemption": "redemption",
    "second chance": "redemption",
    # conspiracy
    "conspiracy": "conspiracy",
    "cover-up": "conspiracy",
    "cover up": "conspiracy",
    # body horror
    "body horror": "body horror",
    "mutation": "body horror",
    # cyberpunk
    "cyberpunk": "cyberpunk",
    "virtual reality": "cyberpunk",
    "hacker": "cyberpunk",
    # western
    "western": "western",
    "cowboy": "western",
    "outlaw": "western",
    # road trip
    "road trip": "road trip",
    "road movie": "road trip",
    # underdog
    "underdog": "underdog",
    "sports": "underdog",
    # chosen one
    "chosen one": "chosen one",
    "prophecy": "chosen one",
    # AI
    "artificial intelligence": "artificial intelligence",
    "ai": "artificial intelligence",
    "robot": "artificial intelligence",
    "android": "artificial intelligence",
    # environmental
    "climate change": "environmental",
    "environment": "environmental",
    "nature": "environmental",
}


def normalize_keyword(raw: str) -> str:
    return " ".join(str(raw or "").strip().lower().split())


def parse_keywords(raw: Any) -> List[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(v).strip() for v in raw if str(v).strip()]
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if isinstance(parsed, list):
            return [str(v).strip() for v in parsed if str(v).strip()]
    return []


def themes_from_keywords(keywords: Iterable[str]) -> List[str]:
    """Map keyword phrases onto the controlled theme set (stable order)."""
    found: Set[str] = set()
    for keyword in keywords:
        key = normalize_keyword(keyword)
        if not key:
            continue
        theme = KEYWORD_TO_THEME.get(key)
        if theme and theme in CONTROLLED_THEMES:
            found.add(theme)
            continue
        # Fallback: match any mapped phrase contained in the keyword or vice versa.
        for mapped_key, mapped_theme in KEYWORD_TO_THEME.items():
            if mapped_theme not in CONTROLLED_THEMES:
                continue
            if mapped_key == key or mapped_key in key or key in mapped_key:
                found.add(mapped_theme)
    return sorted(found)


def theme_rows_for_item(item_id: int, keywords_raw: Any) -> List[tuple[int, str, str]]:
    themes = themes_from_keywords(parse_keywords(keywords_raw))
    return [(int(item_id), "theme", theme) for theme in themes]


def extract_theme_rows(items: Iterable[Mapping[str, Any]]) -> List[tuple[int, str, str]]:
    """Build ``(item_id, 'theme', value)`` rows for a library snapshot."""
    rows: List[tuple[int, str, str]] = []
    for row in items:
        keys = row.keys() if hasattr(row, "keys") else row
        item_id = int(row["id"])
        raw = row["keywords"] if "keywords" in keys else []
        rows.extend(theme_rows_for_item(item_id, raw))
    return rows
