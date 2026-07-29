"""Channel recipe types and youth-safe playlist helpers.

Recipes describe *intent* Projectionist will later publish to Tunarr
(channels + programming + optional filler-lists). Pure data + filters —
no HTTP here.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from projectionist.youth.rating_gate import (
    filter_items_for_youth,
    resolve_youth_max_rating,
)


class ProgrammingMode(str, Enum):
    """How titles are ordered on the station.

    Maps toward Tunarr programming / schedule-slots:
    - sequential → ordered lineup
    - shuffle / chaos → random slot schedule
    """

    SEQUENTIAL = "sequential"
    SHUFFLE = "shuffle"
    CHAOS = "chaos"


@dataclass(frozen=True)
class ChannelRecipe:
    """A proposed or published Live Channel station."""

    name: str
    number: int
    source: str  # taste_cluster | motif | collection | chaos | youth
    programming_mode: ProgrammingMode = ProgrammingMode.SHUFFLE
    cluster_tag: str = ""
    motif: str = ""
    collection_id: str = ""
    collection_title: str = ""
    youth_safe: bool = False
    summary: str = ""
    item_hints: tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["programming_mode"] = self.programming_mode.value
        payload["item_hints"] = list(self.item_hints)
        return payload


def apply_youth_gate_to_items(
    items: Sequence[Mapping[str, Any]] | Iterable[Mapping[str, Any]],
    *,
    settings: Any = None,
    max_rating: Optional[str] = None,
    rating_key: str = "content_rating",
) -> List[Dict[str, Any]]:
    """Filter playlist candidates with the existing youth rating gate.

    Prefer an explicit ``max_rating``; otherwise resolve from ``settings.youth``.
    """
    ceiling = str(max_rating or "").strip()
    if not ceiling and settings is not None:
        ceiling = resolve_youth_max_rating(settings)
    if not ceiling:
        return [dict(item) for item in items if isinstance(item, Mapping)]
    return filter_items_for_youth(items, max_rating=ceiling, rating_key=rating_key)


def recipe_from_mapping(data: Mapping[str, Any]) -> ChannelRecipe:
    """Build a recipe from a plain dict (API / tests)."""
    mode_raw = str(data.get("programming_mode") or ProgrammingMode.SHUFFLE.value).lower()
    try:
        mode = ProgrammingMode(mode_raw)
    except ValueError:
        mode = ProgrammingMode.SHUFFLE
    hints = data.get("item_hints") or ()
    if isinstance(hints, str):
        hint_tuple = (hints,)
    else:
        hint_tuple = tuple(str(h) for h in hints if str(h).strip())
    return ChannelRecipe(
        name=str(data.get("name") or "Untitled").strip() or "Untitled",
        number=int(data.get("number") or 0),
        source=str(data.get("source") or "chaos").strip() or "chaos",
        programming_mode=mode,
        cluster_tag=str(data.get("cluster_tag") or "").strip(),
        motif=str(data.get("motif") or "").strip(),
        collection_id=str(data.get("collection_id") or "").strip(),
        collection_title=str(data.get("collection_title") or "").strip(),
        youth_safe=bool(data.get("youth_safe")),
        summary=str(data.get("summary") or "").strip(),
        item_hints=hint_tuple,
    )
