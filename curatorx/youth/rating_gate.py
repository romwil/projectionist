"""Fail-closed content-rating gate for Youth-mode accounts.

Hide empty / missing ``content_rating`` and anything above the owner-configured
maximum. Unrated titles never pass.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

DEFAULT_YOUTH_MAX_RATING = "PG-13"

# Unified rank ladder — movies and TV share one comparable scale.
# Higher number = more restrictive / mature.
_RATING_RANKS: dict[str, int] = {
    "G": 10,
    "TV-Y": 10,
    "TV-Y7": 15,
    "TV-G": 18,
    "PG": 20,
    "TV-PG": 25,
    "PG-13": 30,
    "TV-14": 35,
    "R": 40,
    "NC-17": 50,
    "TV-MA": 50,
    "X": 55,
}

# Labels we emit for SQL IN / LIKE allow-lists (canonical + common variants).
_CANONICAL_LABELS: dict[str, tuple[str, ...]] = {
    "G": ("G", "Rated G"),
    "TV-Y": ("TV-Y", "TVY"),
    "TV-Y7": ("TV-Y7", "TV-Y7-FV", "TVY7"),
    "TV-G": ("TV-G", "TVG"),
    "PG": ("PG", "Rated PG"),
    "TV-PG": ("TV-PG", "TVPG"),
    "PG-13": ("PG-13", "PG13", "Rated PG-13"),
    "TV-14": ("TV-14", "TV14"),
    "R": ("R", "Rated R"),
    "NC-17": ("NC-17", "NC17", "Rated NC-17"),
    "TV-MA": ("TV-MA", "TVMA"),
    "X": ("X",),
}


def normalize_content_rating(raw: Any) -> str:
    """Return a canonical rating key (e.g. ``PG-13``) or ``\"\"`` if unknown/empty."""
    text = str(raw or "").strip().upper()
    if not text:
        return ""
    text = text.replace("RATED ", "").replace("RATING:", "").strip()
    text = text.replace("_", "-").replace(" ", "")
    # Normalize common glued forms.
    aliases = {
        "PG13": "PG-13",
        "NC17": "NC-17",
        "TVY": "TV-Y",
        "TVY7": "TV-Y7",
        "TVY7FV": "TV-Y7",
        "TVG": "TV-G",
        "TVPG": "TV-PG",
        "TV14": "TV-14",
        "TVMA": "TV-MA",
        "NOTRATED": "",
        "NR": "",
        "UNRATED": "",
        "N/A": "",
        "NA": "",
        "NONE": "",
    }
    if text in aliases:
        return aliases[text]
    if text in _RATING_RANKS:
        return text
    # Soft match: starts with a known key.
    for key in sorted(_RATING_RANKS.keys(), key=len, reverse=True):
        compact_key = key.replace("-", "")
        if text == compact_key or text.startswith(key) or text.startswith(compact_key):
            return key
    return ""


def rating_rank(raw: Any) -> Optional[int]:
    """Numeric maturity rank, or ``None`` when unrated / unrecognized (fail-closed)."""
    key = normalize_content_rating(raw)
    if not key:
        return None
    return _RATING_RANKS.get(key)


def content_rating_allowed(raw: Any, *, max_rating: str) -> bool:
    """True only when the title has a known rating at or below ``max_rating``."""
    rank = rating_rank(raw)
    if rank is None:
        return False
    max_rank = rating_rank(max_rating)
    if max_rank is None:
        max_rank = _RATING_RANKS[DEFAULT_YOUTH_MAX_RATING]
    return rank <= max_rank


def allowed_rating_labels(max_rating: str) -> List[str]:
    """Canonical labels at or below ``max_rating`` (for SQL filters / tests)."""
    max_rank = rating_rank(max_rating)
    if max_rank is None:
        max_rank = _RATING_RANKS[DEFAULT_YOUTH_MAX_RATING]
    out: List[str] = []
    for key, rank in _RATING_RANKS.items():
        if rank <= max_rank:
            out.append(key)
            out.extend(_CANONICAL_LABELS.get(key, ()))
    # Dedupe preserving order
    seen = set()
    unique: List[str] = []
    for label in out:
        low = label.lower()
        if low in seen:
            continue
        seen.add(low)
        unique.append(label)
    return unique


def resolve_youth_max_rating(settings: Any) -> str:
    """Owner-configured max, falling back to PG-13."""
    youth = getattr(settings, "youth", None)
    raw = ""
    if youth is not None:
        raw = str(getattr(youth, "max_content_rating", "") or "").strip()
    if not raw:
        raw = str(getattr(settings, "youth_max_content_rating", "") or "").strip()
    key = normalize_content_rating(raw) if raw else ""
    return key or DEFAULT_YOUTH_MAX_RATING


def youth_gate_active(user: Any) -> bool:
    """Youth gate applies when the signed-in account is flagged Youth."""
    if user is None:
        return False
    return bool(getattr(user, "is_youth", False))


def filter_items_for_youth(
    items: Sequence[Mapping[str, Any]] | Iterable[Mapping[str, Any]],
    *,
    max_rating: str,
    rating_key: str = "content_rating",
) -> List[Dict[str, Any]]:
    """Drop unrated and over-max items (fail-closed)."""
    out: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        if content_rating_allowed(item.get(rating_key), max_rating=max_rating):
            out.append(dict(item))
    return out
