"""Taste cluster tag validation and free-text tokenization.

``taste_refresh`` used to whitespace-split preference / feedback prose into
cluster tags, which produced junk like ``you've``, ``of``, ``in.``, and ``-``.
These helpers keep only contentful tags suitable for Settings → Taste.
"""

from __future__ import annotations

import re
from typing import Iterable, List

# Leading letter, then letters / digits / internal hyphens / apostrophes.
_TOKEN_RE = re.compile(r"[a-z][a-z0-9']*(?:-[a-z0-9]+)*")
# you've / here's / don't / i'm — contractions are never taste clusters.
_CONTRACTION_RE = re.compile(
    r"^(?:[a-z]+'(?:s|re|ve|ll|d|m)|[a-z]+n't)$"
)
# Apostrophe-stripped contraction leftovers after normalize.
_CONTRACTION_FORMS = frozenset(
    {
        "youve",
        "youre",
        "youll",
        "youd",
        "im",
        "ive",
        "ill",
        "id",
        "hes",
        "shes",
        "its",  # ambiguous; treat bare "its" as filler (genre "sci-fi" still ok)
        "were",  # we're → were after strip; also English "were"
        "weve",
        "well",  # we'll; also English "well" — low-value as a cluster
        "wed",
        "theyre",
        "theyve",
        "theyll",
        "theyd",
        "heres",
        "theres",
        "thats",
        "whats",
        "whos",
        "wheres",
        "hows",
        "dont",
        "doesnt",
        "didnt",
        "isnt",
        "arent",
        "wasnt",
        "werent",
        "hasnt",
        "havent",
        "hadnt",
        "wont",
        "wouldnt",
        "couldnt",
        "shouldnt",
        "cant",
        "lets",
    }
)

# Function words + ultra-common prose leftovers that survive naive splits.
# Keep this independent of Plot Lab motif STOPWORDS so taste can be stricter.
STOPWORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "nor",
        "but",
        "if",
        "then",
        "than",
        "so",
        "as",
        "of",
        "in",
        "on",
        "at",
        "to",
        "for",
        "from",
        "by",
        "with",
        "without",
        "into",
        "onto",
        "about",
        "after",
        "before",
        "between",
        "through",
        "over",
        "under",
        "up",
        "down",
        "out",
        "off",
        "all",
        "any",
        "each",
        "both",
        "few",
        "many",
        "much",
        "more",
        "most",
        "some",
        "such",
        "other",
        "own",
        "same",
        "only",
        "just",
        "also",
        "very",
        "too",
        "not",
        "no",
        "yes",
        "do",
        "does",
        "did",
        "done",
        "doing",
        "be",
        "am",
        "is",
        "are",
        "was",
        "were",
        "been",
        "being",
        "have",
        "has",
        "had",
        "having",
        "will",
        "would",
        "could",
        "should",
        "must",
        "can",
        "may",
        "might",
        "shall",
        "i",
        "me",
        "my",
        "mine",
        "we",
        "us",
        "our",
        "ours",
        "you",
        "your",
        "yours",
        "he",
        "him",
        "his",
        "she",
        "her",
        "hers",
        "it",
        "its",
        "they",
        "them",
        "their",
        "theirs",
        "this",
        "that",
        "these",
        "those",
        "who",
        "whom",
        "whose",
        "what",
        "which",
        "when",
        "where",
        "why",
        "how",
        "here",
        "there",
        "now",
        "then",
        "got",
        "get",
        "gets",
        "getting",
        "gotten",
        "see",
        "sees",
        "saw",
        "seen",
        "look",
        "looks",
        "looking",
        "make",
        "makes",
        "made",
        "take",
        "takes",
        "took",
        "taken",
        "come",
        "comes",
        "came",
        "give",
        "gives",
        "gave",
        "given",
        "know",
        "knows",
        "knew",
        "known",
        "think",
        "thinks",
        "thought",
        "feel",
        "feels",
        "felt",
        "like",
        "likes",
        "liked",
        "love",
        "loves",
        "loved",
        "want",
        "wants",
        "wanted",
        "need",
        "needs",
        "needed",
        "really",
        "quite",
        "rather",
        "even",
        "still",
        "already",
        "always",
        "never",
        "often",
        "sometimes",
        "please",
        "thanks",
        "thank",
        "hey",
        "hi",
        "hello",
        "ok",
        "okay",
        "well",
        "yeah",
        "yep",
        "nope",
        "one",
        "two",
        "new",
        "old",
        "way",
        "back",
        "time",
        "year",
        "years",
        "day",
        "days",
        "first",
        "last",
        "next",
        "film",
        "movie",
        "movies",
        "show",
        "shows",
        "series",
        "season",
        "episode",
        "story",
        "watch",
        "watched",
        "watching",
        "recommend",
        "recommended",
        "something",
        "anything",
        "everything",
        "nothing",
        "someone",
        "anyone",
        "everyone",
        "heres",
        "youve",
        "youre",
    }
)

_MIN_LETTER_COUNT = 3
_MAX_TAG_LEN = 80
_MAX_WORDS = 4


def normalize_cluster_tag(raw: str) -> str:
    """Lowercase, strip edge punctuation, collapse whitespace."""
    text = str(raw or "").strip().lower()
    if not text:
        return ""
    # Drop surrounding junk (``in.`` → ``in``, ``-`` → ````).
    text = re.sub(r"^[^\w]+|[^\w]+$", "", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:_MAX_TAG_LEN]


def is_valid_cluster_tag(raw: str) -> bool:
    """Return True when ``raw`` is a contentful taste cluster label."""
    tag = normalize_cluster_tag(raw)
    if not tag:
        return False
    if len(tag) > _MAX_TAG_LEN:
        return False
    if tag in STOPWORDS or tag in _CONTRACTION_FORMS:
        return False
    if "'" in tag or _CONTRACTION_RE.match(tag):
        return False
    if not re.search(r"[a-z]", tag):
        return False
    # Only letters, digits, spaces, and hyphens after normalize.
    if not re.fullmatch(r"[a-z0-9]+(?:[\s\-][a-z0-9]+)*", tag):
        return False
    letters = re.sub(r"[^a-z]", "", tag)
    if len(letters) < _MIN_LETTER_COUNT:
        return False
    parts = [p for p in re.split(r"[\s\-]+", tag) if p]
    if len(parts) > _MAX_WORDS:
        return False
    content = [
        p
        for p in parts
        if p not in STOPWORDS
        and p not in _CONTRACTION_FORMS
        and len(re.sub(r"[^a-z]", "", p)) >= _MIN_LETTER_COUNT
    ]
    return bool(content)


def cluster_tokens_from_text(text: str) -> List[str]:
    """Extract valid cluster tags from free-text preference / feedback prose."""
    out: List[str] = []
    seen: set[str] = set()
    for match in _TOKEN_RE.findall(str(text or "").lower()):
        if not is_valid_cluster_tag(match):
            continue
        tag = normalize_cluster_tag(match)
        # Prefer apostrophe-free form for storage (bride's → already rejected;
        # sci-fi stays).
        tag = tag.replace("'", "")
        if not is_valid_cluster_tag(tag):
            continue
        if tag in seen:
            continue
        seen.add(tag)
        out.append(tag)
    return out


def filter_cluster_tags(tags: Iterable[str]) -> List[str]:
    """Normalize and drop invalid tags from a structured list (genres/keywords)."""
    out: List[str] = []
    seen: set[str] = set()
    for raw in tags:
        if not is_valid_cluster_tag(raw):
            continue
        tag = normalize_cluster_tag(raw)
        if tag in seen:
            continue
        seen.add(tag)
        out.append(tag)
    return out
