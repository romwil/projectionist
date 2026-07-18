"""Idle task: extract motif facets from plot summaries (Plot Lab data).

Tokenizes ``summary`` + ``tmdb_overview`` + ``tagline`` + optional ``llm_logline``,
normalizes possessives, extracts unigrams and high-signal bigrams, computes
document frequency, keeps terms that are uncommon but not hapax (df >= 2 and
df below a corpus fraction), and writes ``library_facets`` with
``facet_type='motif'``.

Per-title budget is split so keyword-stem overlaps are retained even when the
rare-DF ranking would crowd them out (historically an 8-slot hard cap hid
tokens like ``bride`` on Kill Bill).

Motif rows are preserved across sync facet rebuilds (see ``replace_library_facets``).

Default interval: 24 hours.
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from typing import Any, Callable, Dict, Iterable, List, Mapping, Set, Tuple

from curatorx.config_store import Settings
from curatorx.library.db import Database
from curatorx.scheduler.engine import IdleScheduler, TaskDefinition

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 86400  # 24 hours
TOKEN_RE = re.compile(r"[a-z][a-z']{1,}")
# Drop ultra-common English filler that survives DF thresholds in short blurbs.
# These terms are also disallowed in either position of a bigram: adjacent
# summary text such as "and Chloe" is syntax, not a discoverable motif.
STOPWORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "and",
        "or",
        "nor",
        "for",
        "with",
        "from",
        "that",
        "this",
        "when",
        "who",
        "what",
        "where",
        "while",
        "into",
        "onto",
        "about",
        "after",
        "before",
        "their",
        "they",
        "them",
        "his",
        "her",
        "hers",
        "are",
        "was",
        "were",
        "been",
        "being",
        "have",
        "has",
        "had",
        "will",
        "would",
        "could",
        "should",
        "must",
        "can",
        "may",
        "not",
        "but",
        "out",
        "all",
        "any",
        "one",
        "two",
        "new",
        "old",
        "man",
        "men",
        "woman",
        "women",
        "life",
        "world",
        "story",
        "film",
        "movie",
        "series",
        "season",
        "episode",
        "finds",
        "find",
        "takes",
        "take",
        "gets",
        "get",
        "set",
        "against",
        "between",
        "through",
        "over",
        "under",
        "only",
        "also",
        "just",
        "than",
        "then",
        "own",
        "other",
        "more",
        "most",
        "some",
        "such",
        "each",
        "both",
        "few",
        "many",
        "much",
        "very",
        "way",
        "back",
        "year",
        "years",
        "day",
        "days",
        "time",
        "first",
        "young",
        "becomes",
        "become",
        "begins",
        "begin",
        "tries",
        "try",
        "helps",
        "help",
        "family",
        "friend",
        "friends",
        "she",
        "him",
        "its",
        "our",
        "your",
        "you",
        "their",
        "these",
        "those",
        "whose",
        "save",
        "saves",
        "saved",
        "change",
        "changes",
    }
)
MAX_DF_FRACTION = 0.20
MIN_DF = 2
# Split budget: rare-DF unigrams/bigrams plus keyword-stem retention slots.
MAX_RARE_MOTIFS_PER_ITEM = 12
MAX_KEYWORD_BONUS_PER_ITEM = 6
MAX_MOTIFS_PER_ITEM = MAX_RARE_MOTIFS_PER_ITEM + MAX_KEYWORD_BONUS_PER_ITEM


def normalize_token(token: str) -> str:
    """Lowercase and strip light possessives (``bride's`` → ``bride``)."""
    text = str(token or "").lower().strip()
    if not text:
        return ""
    if text.endswith("'s") and len(text) > 3:
        text = text[:-2]
    elif text.endswith("s'") and len(text) > 3:
        text = text[:-2]
    # Drop leftover apostrophes (``rock 'n' roll`` fragments stay rare).
    text = text.replace("'", "")
    return text


def _ordered_tokens(text: str) -> List[str]:
    """Return normalized tokens in order (includes stopwords for bigram windows)."""
    out: List[str] = []
    for match in TOKEN_RE.findall(str(text or "").lower()):
        normalized = normalize_token(match)
        if len(normalized) < 3:
            continue
        out.append(normalized)
    return out


def _parse_keywords(raw: Any) -> List[str]:
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


def keyword_stems(keywords: Iterable[str]) -> Set[str]:
    """Unigram stems from TMDB keyword phrases (``martial arts`` → ``martial``, ``arts``)."""
    stems: Set[str] = set()
    for keyword in keywords:
        for token in _ordered_tokens(keyword):
            if token in STOPWORDS:
                continue
            stems.add(token)
        # Also keep full normalized keyword phrases as stems for phrase overlap.
        phrase = " ".join(_ordered_tokens(keyword))
        if phrase and " " in phrase:
            stems.add(phrase)
    return stems


def tokenize_plot_text(*parts: str) -> Set[str]:
    """Extract unigram + bigram motif candidates from layered plot text."""
    tokens: Set[str] = set()
    for part in parts:
        ordered = _ordered_tokens(part)
        if not ordered:
            continue
        for token in ordered:
            if token in STOPWORDS:
                continue
            tokens.add(token)
        for left, right in zip(ordered, ordered[1:]):
            # A bigram must be two content words.  Stopword-leading fragments
            # ("and Chloe", "its power") reflect grammar rather than a useful
            # Plot Lab concept, and stopword-ending fragments are no better.
            if left in STOPWORDS or right in STOPWORDS:
                continue
            tokens.add(f"{left} {right}")
    return tokens


def _motif_rank(token: str, df: Counter[str]) -> Tuple[int, int, str]:
    """Rank by rarity, then prefer a surviving content phrase to a unigram."""
    content_score = 2 if " " in token else 1
    return (df[token], -content_score, token)


def _row_plot_parts(row: Mapping[str, Any]) -> Tuple[str, str, str, str, str]:
    keys = row.keys() if hasattr(row, "keys") else row
    summary = str(row["summary"] or "") if "summary" in keys else ""
    overview = str(row["tmdb_overview"] or "") if "tmdb_overview" in keys else ""
    tagline = str(row["tagline"] or "") if "tagline" in keys else ""
    long_synopsis = str(row["long_synopsis"] or "") if "long_synopsis" in keys else ""
    logline = str(row["llm_logline"] or "") if "llm_logline" in keys else ""
    return summary, overview, tagline, long_synopsis, logline


def _select_motifs_for_item(
    tokens: Set[str],
    *,
    allowed: Set[str],
    df: Counter[str],
    keyword_stems_for_item: Set[str],
) -> List[str]:
    """Rank allowed tokens: rarer first, keyword-stem overlaps guaranteed."""
    candidates = [t for t in tokens if t in allowed]
    if not candidates:
        return []

    keyword_hits = [t for t in candidates if t in keyword_stems_for_item or any(
        stem == t or stem in t.split() or t in stem.split()
        for stem in keyword_stems_for_item
    )]
    # Prefer exact stem matches, then tokens whose unigram equals a keyword stem.
    keyword_exact = sorted(
        {t for t in candidates if t in keyword_stems_for_item},
        key=lambda t: _motif_rank(t, df),
    )
    keyword_related = sorted(
        (
            t
            for t in keyword_hits
            if t not in keyword_stems_for_item
        ),
        key=lambda t: _motif_rank(t, df),
    )
    guaranteed = (keyword_exact + keyword_related)[:MAX_KEYWORD_BONUS_PER_ITEM]
    guaranteed_set = set(guaranteed)

    rare = sorted(
        (t for t in candidates if t not in guaranteed_set),
        key=lambda t: _motif_rank(t, df),
    )[:MAX_RARE_MOTIFS_PER_ITEM]

    selected = rare + guaranteed
    # Stable unique, preserving rare-first then keyword bonus order.
    seen: Set[str] = set()
    ordered: List[str] = []
    for token in selected:
        if token in seen:
            continue
        seen.add(token)
        ordered.append(token)
        if len(ordered) >= MAX_MOTIFS_PER_ITEM:
            break
    return ordered


def extract_motif_rows(db: Database) -> List[Tuple[int, str, str]]:
    """Return ``(item_id, 'motif', token)`` rows after DF filtering."""
    docs: List[Tuple[int, Set[str], Set[str]]] = []
    for row in db.all_library_items():
        summary, overview, tagline, long_synopsis, logline = _row_plot_parts(row)
        tokens = tokenize_plot_text(summary, overview, tagline, long_synopsis, logline)
        if not tokens:
            continue
        keys = row.keys() if hasattr(row, "keys") else row
        raw_keywords = row["keywords"] if "keywords" in keys else []
        stems = keyword_stems(_parse_keywords(raw_keywords))
        docs.append((int(row["id"]), tokens, stems))

    if not docs:
        return []

    df: Counter[str] = Counter()
    for _, tokens, _ in docs:
        df.update(tokens)

    doc_count = len(docs)
    max_df = max(MIN_DF, int(doc_count * MAX_DF_FRACTION))
    allowed = {
        token
        for token, count in df.items()
        if count >= MIN_DF and count <= max_df
    }
    if not allowed:
        return []

    rows: List[Tuple[int, str, str]] = []
    for item_id, tokens, stems in docs:
        ranked = _select_motifs_for_item(
            tokens,
            allowed=allowed,
            df=df,
            keyword_stems_for_item=stems,
        )
        for token in ranked:
            rows.append((item_id, "motif", token))
    return rows


async def run(
    db: Database, settings: Settings, should_stop: Callable[[], bool]
) -> Dict[str, Any]:
    if should_stop():
        return {"status": "interrupted", "motifs": 0}

    rows = extract_motif_rows(db)
    if should_stop():
        return {"status": "interrupted", "motifs": 0}

    count = db.replace_facets_of_type("motif", rows)
    logger.info("Summary motifs: wrote %s motif facet rows", count)
    return {"status": "completed", "motifs": count, "unique_items": len({r[0] for r in rows})}


def register(scheduler: IdleScheduler) -> None:
    scheduler.register(
        TaskDefinition(
            name="summary_motifs",
            run_interval_seconds=INTERVAL_SECONDS,
            enabled=True,
            run_fn=run,
            description=(
                "Extracts motif facets from plot summaries across the whole library in "
                "one pass and writes them for Plot Lab / Explore motif walls."
            ),
        )
    )
