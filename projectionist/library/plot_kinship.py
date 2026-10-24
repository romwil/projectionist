"""Name a surprising plot link, or refuse one that is only missing shelf labels.

Surprising means a story kinship the shelf would not suggest. Low genre,
keyword, or credit overlap is not itself a reason to recommend a title.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set

# Honest empty for More Like This / relations / privacy MCP graph wraps.
KINSHIP_CACHE_NOT_READY_NOTE = (
    "Named kinship cache not ready — not that nothing is related."
)

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
        "mansion",
        "manor",
    }
)
# Relative pronouns and wiki glue. "which premiered" is syntax, not a subject.
_FUNCTION_UNIGRAMS = frozenset(
    {
        "which",
        "whom",
        "whose",
        "how",
        "why",
        "whether",
        "although",
        "though",
        "however",
        "therefore",
        "thus",
        "hence",
        "because",
        "while",
        "where",
        "when",
        "there",
        "here",
    }
)
# Format / credit boilerplate from TMDB and Wikipedia long synopses.
_FORMAT_UNIGRAMS = frozenset(
    {
        "television",
        "tv",
        "cinema",
        "premiere",
        "premiered",
        "premieres",
        "broadcast",
        "streaming",
        "drama",
        "comedy",
        "thriller",
        "horror",
        "sitcom",
        "miniseries",
        "anthology",
        "starring",
        "created",
        "developed",
        "produced",
        "aired",
        "released",
    }
)
# A shared phrase with one of these in either slot is too vague to name.
_VAGUE_SUBJECTS = frozenset(
    {
        "people",
        "person",
        "persons",
        "ordinary",
        "various",
        "certain",
        "several",
        "things",
        "thing",
        "someone",
        "something",
        "anyone",
        "anything",
        "everyone",
        "everything",
        "climate",
        "climates",
        "weather",
    }
)
# Wikipedia/TMDB infobox leftovers — production, reception, geography, studio,
# and procedural glue. Either slot is enough: "pinewood studios" is not a plot
# subject, and "team investigates" is not a story engine.
_NON_PLOT_UNIGRAMS = frozenset(
    {
        # Production process / commercial boilerplate
        "photography",
        "filming",
        "filmed",
        "shooting",
        "budget",
        "gross",
        "grossing",
        "title",
        "box",
        # Reception
        "reviews",
        "review",
        "critic",
        "critics",
        "critical",
        "acclaim",
        "acclaimed",
        "reception",
        "following",
        # Geography / infobox locations ("new" is a stopword → "york city")
        "united",
        "states",
        "york",
        "hollywood",
        "britain",
        "british",
        "america",
        "countries",
        "country",
        # Studio / company
        "studios",
        "studio",
        "pictures",
        # Procedural glue
        "investigates",
        "investigation",
        "investigating",
        "investigator",
        # Period architecture that is not a shared story engine
        "victorian",
        "edwardian",
        "georgian",
        "elizabethan",
    }
)
_IRREGULAR_PLURALS = frozenset(
    {
        "people",
        "children",
        "men",
        "women",
        "feet",
        "teeth",
        "mice",
        "geese",
        "police",
        "series",
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


def _honest_subject(left: str, right: str) -> bool:
    """True when the bigram can be named as a plot subject without junk grammar."""
    if not left or not right or " " in right:
        return False
    if left in _NOISE_TOKENS or right in _NOISE_TOKENS:
        return False
    if left in _FUNCTION_UNIGRAMS or right in _FUNCTION_UNIGRAMS:
        return False
    if left in _FORMAT_UNIGRAMS or right in _FORMAT_UNIGRAMS:
        return False
    if left in _VAGUE_SUBJECTS or right in _VAGUE_SUBJECTS:
        return False
    if left in _NON_PLOT_UNIGRAMS or right in _NON_PLOT_UNIGRAMS:
        return False
    if left in _GENERIC_UNIGRAMS and right in _GENERIC_UNIGRAMS:
        return False
    return True


def _story_bigrams(tokens: Set[str], blocked: Set[str]) -> list[str]:
    found: list[str] = []
    for token in tokens:
        if " " not in token:
            continue
        left, right = token.split(" ", 1)
        if not _honest_subject(left, right):
            continue
        # A shelf word inside a longer phrase ("museum" in "museum exhibits")
        # does not erase the subject. Drop the phrase only when it is itself
        # a shelf label, or both words already are.
        if token in blocked or (left in blocked and right in blocked):
            continue
        found.append(token)
    found.sort(key=lambda term: (-len(term), term))
    return found


def distinctive_plot_phrases(text: str, *, limit: int = 3) -> list[str]:
    """Longest story bigrams from plot text — bounded search keys, not a KG."""
    tokens = _tokenize(text)
    return _story_bigrams(tokens, set())[: max(0, int(limit or 0))]


def _phrase(term: str) -> Optional[str]:
    words = [part for part in term.split() if part]
    if len(words) != 2 or not _honest_subject(words[0], words[1]):
        return None
    head = words[1]
    # Plurals already read as a noun phrase ("amateur bakers").
    if head in _IRREGULAR_PLURALS or (head.endswith("s") and not head.endswith("ss")):
        return term
    article = "an" if words[0][:1] in "aeiou" else "a"
    return f"{article} {term}"


def _sentence(terms: Sequence[str]) -> str:
    chosen: list[str] = []
    used: Set[str] = set()
    rendered: list[str] = []
    for term in terms:
        words = set(term.split())
        if words & used:
            continue
        phrase = _phrase(term)
        if not phrase:
            continue
        chosen.append(term)
        rendered.append(phrase)
        used |= words
        if len(chosen) == 2:
            break
    if not rendered:
        return ""
    if len(rendered) == 1:
        return f"Both stories turn on {rendered[0]}."
    return f"Both stories turn on {rendered[0]} and {rendered[1]}."


def peers_with_named_explanation(items: Sequence[Any]) -> List[Dict[str, Any]]:
    """Keep peers that carry an XC-01 ``explanation.sentence``; drop cosine-only rows."""
    kept: List[Dict[str, Any]] = []
    for item in items or []:
        if not isinstance(item, Mapping):
            continue
        explanation = item.get("explanation")
        if not isinstance(explanation, dict):
            why = item.get("why")
            if isinstance(why, dict):
                explanation = why.get("explanation")
        if not isinstance(explanation, dict):
            continue
        sentence = str(explanation.get("sentence") or "").strip()
        if not sentence:
            continue
        row = dict(item)
        row["explanation"] = dict(explanation)
        kept.append(row)
    return kept


def kinship_empty_payload(payload: Mapping[str, Any]) -> Dict[str, Any]:
    """Stamp the cache-not-ready note when a graph tool has no named peers."""
    items = list(payload.get("items") or [])
    out = dict(payload)
    out["items"] = items
    out["returned"] = len(items)
    if items:
        out["empty"] = False
        return out
    out["empty"] = True
    out["note"] = KINSHIP_CACHE_NOT_READY_NOTE
    return out


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

    ``kind`` is one of ``plot_link``, ``shared_crew``, ``directed_by``,
    ``written_by``, ``collection``, or ``watched_bridge`` (household seed
    + named peer link). Cosine proximity alone is never a kind.
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


def neighbor_identity(item: Any) -> str:
    """Stable peer key for Similar vs Surprising identity checks."""
    if isinstance(item, Mapping):
        nested = item.get("peer")
        if isinstance(nested, Mapping):
            nested_key = neighbor_identity(nested)
            if nested_key:
                return nested_key

    def _get(key: str) -> Any:
        if isinstance(item, Mapping):
            return item.get(key)
        try:
            return item[key]
        except (KeyError, IndexError, TypeError):
            return None

    rating = str(_get("rating_key") or "").strip()
    if rating:
        return f"rk:{rating}"
    for prefix, key in (("tmdb", "tmdb_id"), ("tvdb", "tvdb_id")):
        value = _get(key)
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            continue
        if parsed > 0:
            return f"{prefix}:{parsed}"
    for key in ("neighbor_id", "to_id", "library_item_id", "id"):
        value = _get(key)
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            continue
        if parsed > 0:
            return f"id:{parsed}"
    return ""


def surprising_items_if_distinct(
    similar_items: Sequence[Any],
    surprising_items: Sequence[Any],
) -> List[Any]:
    """Keep Surprising only when it is not a carbon copy of Similar.

    Same ordered identities → honest empty. Those titles already sit on
    Similar; duplicating the rail is not a story the shelf would not suggest.
    """
    surprising = [item for item in (surprising_items or []) if item is not None]
    if not surprising:
        return []
    similar_ids = [key for key in (neighbor_identity(item) for item in (similar_items or [])) if key]
    surprising_ids = [key for key in (neighbor_identity(item) for item in surprising) if key]
    if similar_ids and surprising_ids == similar_ids:
        return []
    return surprising


def honest_plot_link(link: Optional[Mapping[str, Any]]) -> Optional[dict[str, Any]]:
    """Rebuild a stored plot-link from honest terms, or refuse junk grammar.

    Empty is better than ``an ordinary people`` / ``a drama television`` /
    ``united states`` / ``principal photography``. Crew and collection links
    are a different kind.
    """
    if not link:
        return None
    raw_terms = [str(term).strip().casefold() for term in (link.get("terms") or [])]
    terms = []
    used: Set[str] = set()
    for term in raw_terms:
        words = term.split()
        if len(words) != 2 or not _honest_subject(words[0], words[1]):
            continue
        if set(words) & used:
            continue
        terms.append(term)
        used |= set(words)
        if len(terms) == 3:
            break
    sentence = _sentence(terms)
    if not sentence:
        return None
    return {"sentence": sentence, "terms": terms[:3]}


def specific_plot_link(
    *,
    seed_text: str,
    peer_text: str,
    shelf_labels: Optional[Set[str]] = None,
) -> Optional[dict[str, Any]]:
    """Name a shared story or subject, or refuse a generic or empty overlap.

    Cosine proximity is not an input. A neighbor is honest only when the plots
    share a concrete phrase (``museum exhibits``), not a vague one
    (``ordinary people``, ``creative arts``, ``drama television``) and not
    embeddings alone. Empty is better than junk grammar.
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
