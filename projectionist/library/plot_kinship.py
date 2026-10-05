"""Name a surprising plot link, or refuse one that is only missing shelf labels.

Surprising means a story kinship the shelf would not suggest. Low genre,
keyword, or credit overlap is not itself a reason to recommend a title.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence, Set

# Cosine below "solid plot kinship" is too weak to explain as a story link.
MIN_SURPRISE_COSINE = 0.55
# At or below this Jaccard, shelf labels are not an obvious explanation.
MAX_SURPRISE_OVERLAP = 0.35
# Shorter blurbs are placeholders, boilerplate, or empty plots.
MIN_PLOT_UNIGRAMS = 4

_PLOT_FIELDS = ("summary", "tmdb_overview", "tagline", "long_synopsis", "llm_logline")
_PLACEHOLDER_BLOBS = frozenset(
    {
        "unknown",
        "n/a",
        "na",
        "none",
        "null",
        "no overview",
        "no overview available",
        "no plot",
        "no plot available",
        "plot unknown",
        "not available",
        "tba",
        "tbd",
        "unavailable",
    }
)
# Tokens that show up when a plot was never written.
_NOISE_TOKENS = frozenset(
    {
        "unknown",
        "untitled",
        "overview",
        "summary",
        "plot",
        "available",
        "description",
        "null",
        "none",
        "tba",
        "tbd",
        "unavailable",
        "n/a",
    }
)
# Bigrams made only of these words are not a premise you can recommend on.
_GENERIC_UNIGRAMS = frozenset(
    {
        "people",
        "person",
        "group",
        "team",
        "house",
        "home",
        "city",
        "town",
        "night",
        "morning",
        "father",
        "mother",
        "daughter",
        "son",
        "brother",
        "sister",
        "friend",
        "friends",
        "school",
        "police",
        "murder",
        "killer",
        "crime",
        "secret",
        "power",
        "death",
        "love",
        "war",
        "battle",
        "fight",
        "mission",
        "agent",
        "world",
        "life",
        "story",
        "true",
        "real",
        "best",
        "good",
        "evil",
        "dark",
        "light",
        "young",
        "little",
        "great",
        "american",
    }
)


def plot_blob(row: Optional[Mapping[str, Any]]) -> str:
    """Layered plot text, skipping empty and placeholder fields."""
    if row is None:
        return ""
    parts = []
    for field in _PLOT_FIELDS:
        try:
            value = row[field]
        except (KeyError, IndexError, TypeError):
            value = ""
        text = " ".join(str(value or "").split())
        if not text or text.casefold() in _PLACEHOLDER_BLOBS:
            continue
        parts.append(text)
    return "\n".join(parts)


def _tokenize(text: str) -> Set[str]:
    from projectionist.scheduler.tasks.summary_motifs import tokenize_plot_text

    return tokenize_plot_text(text)


def _content_unigrams(tokens: Set[str]) -> Set[str]:
    return {
        token
        for token in tokens
        if " " not in token and token not in _NOISE_TOKENS and len(token) >= 3
    }


def _blocklist(shelf_labels: Set[str]) -> Set[str]:
    blocked: Set[str] = set()
    for label in shelf_labels:
        text = str(label or "").strip().casefold()
        if not text or text.startswith("person:"):
            continue
        blocked.add(text)
        blocked.update(part for part in text.split() if part)
    return blocked


def _story_bigrams(tokens: Set[str], blocked: Set[str]) -> list[str]:
    found: list[str] = []
    for token in tokens:
        if " " not in token:
            continue
        left, right = token.split(" ", 1)
        if left in _NOISE_TOKENS or right in _NOISE_TOKENS:
            continue
        if left in _GENERIC_UNIGRAMS and right in _GENERIC_UNIGRAMS:
            continue
        if token in blocked or left in blocked or right in blocked:
            continue
        found.append(token)
    found.sort(key=lambda term: (-len(term), term))
    return found


def _phrase(term: str) -> str:
    words = term.split()
    if not words:
        return term
    # Plurals already read as a noun phrase ("amateur bakers").
    if words[-1].endswith("s") and not words[-1].endswith("ss"):
        return term
    article = "an" if words[0][:1] in "aeiou" else "a"
    return f"{article} {term}"


def _sentence(terms: Sequence[str]) -> str:
    chosen: list[str] = []
    used: Set[str] = set()
    for term in terms:
        words = set(term.split())
        if words & used:
            continue
        chosen.append(term)
        used |= words
        if len(chosen) == 2:
            break
    if not chosen:
        return ""
    if len(chosen) == 1:
        return f"Both stories turn on {_phrase(chosen[0])}."
    return f"Both stories turn on {_phrase(chosen[0])} and {_phrase(chosen[1])}."


def surprising_plot_link(
    *,
    cosine: float,
    overlap: Optional[float],
    seed_text: str,
    peer_text: str,
    shelf_labels: Optional[Set[str]] = None,
) -> Optional[dict[str, Any]]:
    """Return a named story link, or None when surprise would be circular.

    ``overlap`` is shelf Jaccard. ``None`` means the shelf was missing on at
    least one side — that is unknown, not "nothing in common."
    """
    try:
        cosine_value = float(cosine)
    except (TypeError, ValueError):
        return None
    if cosine_value < MIN_SURPRISE_COSINE:
        return None
    if overlap is None:
        return None
    try:
        overlap_value = float(overlap)
    except (TypeError, ValueError):
        return None
    if overlap_value > MAX_SURPRISE_OVERLAP:
        return None

    seed_tokens = _tokenize(seed_text)
    peer_tokens = _tokenize(peer_text)
    if len(_content_unigrams(seed_tokens)) < MIN_PLOT_UNIGRAMS:
        return None
    if len(_content_unigrams(peer_tokens)) < MIN_PLOT_UNIGRAMS:
        return None

    blocked = _blocklist(shelf_labels or set())
    shared = set(_story_bigrams(seed_tokens, blocked)) & set(
        _story_bigrams(peer_tokens, blocked)
    )
    sentence = _sentence(sorted(shared, key=lambda term: (-len(term), term)))
    if not sentence:
        return None
    return {
        "sentence": sentence,
        "terms": sorted(shared, key=lambda term: (-len(term), term))[:3],
        "shelf_note": "Shelf labels barely overlap",
    }
