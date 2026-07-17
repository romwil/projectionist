"""Idle task: extract motif facets from plot summaries (Plot Lab data).

Tokenizes ``summary`` + ``tmdb_overview``, computes document frequency, keeps
terms that are uncommon but not hapax (df >= 2 and df below a corpus fraction),
and writes ``library_facets`` with ``facet_type='motif'``.

Motif rows are preserved across sync facet rebuilds (see ``replace_library_facets``).

Default interval: 24 hours.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from typing import Any, Callable, Dict, List, Set, Tuple

from curatorx.config_store import Settings
from curatorx.library.db import Database
from curatorx.scheduler.engine import IdleScheduler, TaskDefinition

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 86400  # 24 hours
TOKEN_RE = re.compile(r"[a-z][a-z']{2,}")
# Drop ultra-common English filler that survives DF thresholds in short blurbs.
STOPWORDS = frozenset(
    {
        "the",
        "and",
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
        "must",
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
    }
)
MAX_DF_FRACTION = 0.20
MIN_DF = 2
MAX_MOTIFS_PER_ITEM = 8


def tokenize_plot_text(*parts: str) -> Set[str]:
    tokens: Set[str] = set()
    for part in parts:
        text = str(part or "").lower()
        for match in TOKEN_RE.findall(text):
            if match in STOPWORDS:
                continue
            tokens.add(match)
    return tokens


def extract_motif_rows(db: Database) -> List[Tuple[int, str, str]]:
    """Return ``(item_id, 'motif', token)`` rows after DF filtering."""
    docs: List[Tuple[int, Set[str]]] = []
    for row in db.all_library_items():
        tokens = tokenize_plot_text(
            str(row["summary"] or ""),
            str(row["tmdb_overview"] or "") if "tmdb_overview" in row.keys() else "",
        )
        if tokens:
            docs.append((int(row["id"]), tokens))

    if not docs:
        return []

    df: Counter[str] = Counter()
    for _, tokens in docs:
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
    for item_id, tokens in docs:
        # Prefer rarer motifs within the allowed band.
        ranked = sorted(
            (t for t in tokens if t in allowed),
            key=lambda t: (df[t], t),
        )[:MAX_MOTIFS_PER_ITEM]
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
