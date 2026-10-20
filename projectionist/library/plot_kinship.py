"""Name a surprising plot link, or refuse one that is only missing shelf labels.

Surprising means a story kinship the shelf would not suggest. Low genre,
keyword, or credit overlap is not itself a reason to recommend a title.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Mapping, Optional, Sequence, Set

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
        # Abstract craft and shelf words. A shared phrase made only of these
        # ("creative arts") is not a story someone would recognize.
        "creative",
        "arts",
        "art",
        "artist",
        "artists",
        "artistic",
        "design",
        "designer",
        "culture",
        "cultural",
        "history",
        "historical",
        "science",
        "scientific",
        "company",
        "project",
        "projects",
        "build",
        "building",
        "built",
        "work",
        "works",
        "working",
        "documentary",
        "reality",
        "based",
        "story",
        "stories",
        "film",
        "movie",
        "modern",
        "visual",
        "fine",
        "performing",
        "human",
        "humans",
        "technology",
        "future",
        "business",
        "create",
        "creating",
        "creation",
        "discover",
        "discovery",
        "explore",
        "exploration",
        "adventure",
        "journey",
        "famous",
        "known",
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
        # A shelf word inside a longer phrase ("museum" in "museum exhibits")
        # does not erase the subject. Drop the phrase only when it is itself
        # a shelf label, or both words already are.
        if token in blocked or (left in blocked and right in blocked):
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


def build_explanation(
    *,
    kind: str,
    sentence: str,
    terms: Optional[Sequence[str]] = None,
    seed_ids: Optional[Sequence[int]] = None,
    peer_id: Optional[int] = None,
    evidence: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Shared explanation object for relations, More Like This, and inbox bridges.

    ``kind`` is one of ``plot_link``, ``shared_crew``, ``collection``
    (and later ``watched_bridge``). Cosine proximity alone is never a kind.
    """
    cleaned_kind = str(kind or "").strip().lower() or "plot_link"
    payload: Dict[str, Any] = {
        "kind": cleaned_kind,
        "sentence": " ".join(str(sentence or "").split()),
        "terms": [str(term).strip() for term in (terms or []) if str(term).strip()],
        "evidence": dict(evidence or {}),
    }
    if seed_ids is not None:
        payload["seed_ids"] = [int(item_id) for item_id in seed_ids]
    if peer_id is not None:
        payload["peer_id"] = int(peer_id)
    return payload


def explanation_from_plot_link(
    link: Mapping[str, Any],
    *,
    peer_id: Optional[int] = None,
    seed_ids: Optional[Sequence[int]] = None,
    evidence: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Wrap a ``specific_plot_link`` result as a shared explanation object."""
    extra = dict(evidence or {})
    if "shelf_note" in link and link.get("shelf_note"):
        extra.setdefault("shelf_note", link["shelf_note"])
    return build_explanation(
        kind="plot_link",
        sentence=str(link.get("sentence") or ""),
        terms=[str(term) for term in (link.get("terms") or [])],
        seed_ids=seed_ids,
        peer_id=peer_id,
        evidence=extra,
    )


def plot_link_json(link: Optional[Mapping[str, Any]]) -> Optional[str]:
    """Serialize a plot-link dict for ``item_neighbors.plot_link_json``."""
    if not link:
        return None
    sentence = str(link.get("sentence") or "").strip()
    if not sentence:
        return None
    return json.dumps(
        {
            "sentence": sentence,
            "terms": [str(term) for term in (link.get("terms") or [])][:3],
        },
        separators=(",", ":"),
    )


def parse_plot_link_json(raw: Any) -> Optional[Dict[str, Any]]:
    """Parse stored ``plot_link_json`` back into ``{sentence, terms}``."""
    if raw is None:
        return None
    if isinstance(raw, dict):
        sentence = str(raw.get("sentence") or "").strip()
        if not sentence:
            return None
        return {
            "sentence": sentence,
            "terms": [str(term) for term in (raw.get("terms") or [])][:3],
        }
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(parsed, dict):
        return None
    return parse_plot_link_json(parsed)


def specific_plot_link(
    *,
    seed_text: str,
    peer_text: str,
    shelf_labels: Optional[Set[str]] = None,
) -> Optional[dict[str, Any]]:
    """Name a shared story or subject, or refuse a generic or empty overlap.

    Cosine proximity is not an input. A neighbor is honest only when the plots
    share a concrete phrase (``museum exhibits``), not a vague one
    (``creative arts``) and not embeddings alone.
    """
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
    terms = sorted(shared, key=lambda term: (-len(term), term))
    sentence = _sentence(terms)
    if not sentence:
        return None
    return {"sentence": sentence, "terms": terms[:3]}


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

    link = specific_plot_link(
        seed_text=seed_text,
        peer_text=peer_text,
        shelf_labels=shelf_labels,
    )
    if not link:
        return None
    return {
        "sentence": link["sentence"],
        "terms": list(link["terms"]),
        "shelf_note": "Shelf labels barely overlap",
    }
