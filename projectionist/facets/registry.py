"""Load and cache layered facet taxonomy (concepts / aliases / packs).

Seed lives in ``projectionist/facets/data/taxonomy.json``. Operators can extend
without touching tool registry code via:

* ``PROJECTIONIST_FACET_ALIASES`` — absolute path to a JSON overlay/replacement
* ``$DATA_DIR/taxonomy.json`` or ``$DATA_DIR/facet_aliases.json`` — deep-merged
  on top of the packaged seed

Seed stores **names / aliases / packs only** — never trusted baked TMDB discover
genre ids. Resolve against live TMDB genre lists at call time.
"""

from __future__ import annotations

import json
import os
import threading
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, MutableMapping, Optional, Sequence

_LOCK = threading.RLock()
_CACHED: Optional["FacetRegistry"] = None

_SEED_PATH = Path(__file__).resolve().parent / "data" / "taxonomy.json"


def _as_str_dict(raw: Any) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not isinstance(raw, Mapping):
        return out
    for key, value in raw.items():
        k = str(key or "").strip()
        v = str(value or "").strip()
        if k and v:
            out[k] = v
    return out


def _as_str_list_map(raw: Any) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    if not isinstance(raw, Mapping):
        return out
    for key, value in raw.items():
        k = str(key or "").strip()
        if not k:
            continue
        if isinstance(value, str):
            items = [value.strip()] if value.strip() else []
        elif isinstance(value, Sequence):
            items = [str(v).strip() for v in value if str(v).strip()]
        else:
            items = []
        if items:
            out[k] = items
    return out


def _deep_merge(base: MutableMapping[str, Any], overlay: Mapping[str, Any]) -> Dict[str, Any]:
    """Merge overlay onto base. Dicts recurse; lists/scalars replace."""
    merged: Dict[str, Any] = dict(base)
    for key, value in overlay.items():
        if (
            key in merged
            and isinstance(merged[key], MutableMapping)
            and isinstance(value, Mapping)
        ):
            merged[key] = _deep_merge(merged[key], value)  # type: ignore[arg-type]
        else:
            merged[key] = deepcopy(value)
    return merged


@dataclass(frozen=True)
class FacetConcept:
    """Canonical facet concept with ordered live-TMDB name candidates."""

    id: str
    label: str = ""
    names: tuple[str, ...] = ()


@dataclass(frozen=True)
class FacetPack:
    """Reusable discover enrichment for a conceptual facet (e.g. TV History)."""

    id: str
    label: str = ""
    concept_id: str = ""
    match_pattern: str = ""
    match_aliases: tuple[str, ...] = ()
    keyword_queries: tuple[str, ...] = ()
    theme_tokens: tuple[str, ...] = ()
    strong_theme_tokens: tuple[str, ...] = ()
    keep_genre_names: tuple[str, ...] = ()
    reject_genre_names: tuple[str, ...] = ()
    reject_overview_patterns: tuple[str, ...] = ()


@dataclass(frozen=True)
class IntentNegation:
    pattern: str
    without_genres: str = ""
    without_keywords: str = ""


@dataclass(frozen=True)
class IntentGenreHint:
    pattern: str
    genres: str
    prefer_media_type: str = ""


@dataclass(frozen=True)
class IntentTvTypeHint:
    pattern: str
    tv_type: str
    media_type: str = "show"


@dataclass(frozen=True)
class IntentRules:
    descriptive_ask_glue: frozenset[str] = frozenset()
    descriptive_ask_min_words: int = 5
    recent_years_lookback: int = 8
    theme_stopwords: frozenset[str] = frozenset()
    negations: tuple[IntentNegation, ...] = ()
    genre_hints: tuple[IntentGenreHint, ...] = ()
    tv_type_hints: tuple[IntentTvTypeHint, ...] = ()
    recent_pattern: str = r"\brecent\b"


@dataclass
class FacetRegistry:
    """In-memory view of layered facet taxonomy (+ overlays)."""

    version: int = 2
    concepts: Dict[str, FacetConcept] = field(default_factory=dict)
    aliases: Dict[str, str] = field(default_factory=dict)
    facet_packs: Dict[str, FacetPack] = field(default_factory=dict)
    tv_types: Dict[str, str] = field(default_factory=dict)
    intent: IntentRules = field(default_factory=IntentRules)
    motif_search_aliases: Dict[str, List[str]] = field(default_factory=dict)
    source_paths: tuple[str, ...] = ()

    # Flat views for callers / overlays that still speak genre_aliases.
    @property
    def genre_aliases(self) -> Dict[str, str]:
        """alias → primary TMDB name (derived from concepts)."""
        out: Dict[str, str] = {}
        for alias, concept_id in self.aliases.items():
            concept = self.concepts.get(concept_id)
            if not concept:
                continue
            primary = concept.names[0] if concept.names else concept.label
            if primary:
                out[alias] = primary
        return out

    @property
    def genre_crosswalk(self) -> Dict[str, List[str]]:
        """primary name → remaining candidate names (derived from concepts)."""
        out: Dict[str, List[str]] = {}
        for concept in self.concepts.values():
            if len(concept.names) < 2:
                continue
            primary = concept.names[0]
            out[primary] = list(concept.names[1:])
            for name in concept.names[1:]:
                siblings = [n for n in concept.names if n != name]
                if siblings:
                    out[name] = siblings
        return out

    def concept_for(self, raw: str) -> Optional[FacetConcept]:
        key = str(raw or "").strip().casefold()
        if not key:
            return None
        concept_id = self.aliases.get(key)
        if concept_id and concept_id in self.concepts:
            return self.concepts[concept_id]
        for concept in self.concepts.values():
            if concept.id.casefold() == key:
                return concept
            if concept.label.casefold() == key:
                return concept
            for name in concept.names:
                if name.casefold() == key:
                    return concept
        return None

    def alias_canonical(self, raw: str) -> Optional[str]:
        concept = self.concept_for(raw)
        if not concept:
            return None
        if concept.names:
            return concept.names[0]
        return concept.label or None

    def crosswalk_fallbacks(self, canonical: str) -> List[str]:
        name = str(canonical or "").strip()
        if not name:
            return []
        concept = self.concept_for(name)
        if not concept:
            return []
        return [n for n in concept.names if n.casefold() != name.casefold()]

    def lookup_names_for(self, wanted: str) -> List[str]:
        """Ordered candidate TMDB genre names for a user/agent facet token."""
        wanted = str(wanted or "").strip()
        if not wanted:
            return []
        names: List[str] = []
        concept = self.concept_for(wanted)
        if concept:
            for name in concept.names:
                if name not in names:
                    names.append(name)
        if wanted not in names:
            names.append(wanted)
        return names


def _parse_concepts(raw: Any) -> Dict[str, FacetConcept]:
    concepts: Dict[str, FacetConcept] = {}
    if not isinstance(raw, Mapping):
        return concepts
    for concept_id, body in raw.items():
        cid = str(concept_id or "").strip()
        if not cid or not isinstance(body, Mapping):
            continue
        names = tuple(
            str(v).strip() for v in (body.get("names") or []) if str(v).strip()
        )
        label = str(body.get("label") or (names[0] if names else cid)).strip()
        concepts[cid] = FacetConcept(id=cid, label=label, names=names)
    return concepts


def _concepts_from_flat(
    genre_aliases: Mapping[str, str],
    genre_crosswalk: Mapping[str, Sequence[str]],
) -> tuple[Dict[str, FacetConcept], Dict[str, str]]:
    """Normalize v1 genre_aliases + genre_crosswalk into concepts/aliases."""
    concepts: Dict[str, FacetConcept] = {}
    aliases: Dict[str, str] = {}
    # Group by canonical primary name.
    by_primary: Dict[str, List[str]] = {}
    for alias, canonical in genre_aliases.items():
        primary = str(canonical or "").strip()
        if not primary:
            continue
        by_primary.setdefault(primary, [])
        aliases[str(alias).strip().casefold()] = primary
    for primary, fallbacks in genre_crosswalk.items():
        key = str(primary or "").strip()
        if not key:
            continue
        by_primary.setdefault(key, [])
        for fb in fallbacks or []:
            name = str(fb or "").strip()
            if name and name not in by_primary[key]:
                by_primary[key].append(name)

    # Collapse crosswalk siblings that point at each other into one concept.
    # Use the first name as concept id slug.
    claimed: Dict[str, str] = {}  # name.casefold → concept_id
    for primary, extras in by_primary.items():
        names = [primary, *[e for e in extras if e.casefold() != primary.casefold()]]
        # Reuse concept if any name already claimed.
        concept_id = None
        for name in names:
            existing = claimed.get(name.casefold())
            if existing:
                concept_id = existing
                break
        if concept_id is None:
            slug = (
                primary.casefold()
                .replace("&", "and")
                .replace("/", " ")
                .replace("-", " ")
            )
            slug = "_".join(part for part in slug.split() if part)
            concept_id = slug or primary.casefold()
            base = concept_id
            n = 2
            while concept_id in concepts:
                concept_id = f"{base}_{n}"
                n += 1
            concepts[concept_id] = FacetConcept(
                id=concept_id, label=primary, names=tuple(names)
            )
        else:
            existing_concept = concepts[concept_id]
            merged = list(existing_concept.names)
            for name in names:
                if name not in merged:
                    merged.append(name)
            concepts[concept_id] = FacetConcept(
                id=concept_id,
                label=existing_concept.label or primary,
                names=tuple(merged),
            )
        for name in concepts[concept_id].names:
            claimed[name.casefold()] = concept_id

    # Point aliases at concept ids.
    alias_to_concept: Dict[str, str] = {}
    for alias_key, primary in aliases.items():
        concept_id = claimed.get(primary.casefold())
        if concept_id:
            alias_to_concept[alias_key] = concept_id
    # Also alias each concept name / label.
    for concept in concepts.values():
        alias_to_concept[concept.id.casefold()] = concept.id
        if concept.label:
            alias_to_concept[concept.label.casefold()] = concept.id
        for name in concept.names:
            alias_to_concept[name.casefold()] = concept.id
    return concepts, alias_to_concept


def _parse_packs(raw: Any) -> Dict[str, FacetPack]:
    packs: Dict[str, FacetPack] = {}
    if not isinstance(raw, Mapping):
        return packs
    for pack_id, body in raw.items():
        if not isinstance(body, Mapping):
            continue
        pid = str(pack_id or "").strip()
        if not pid:
            continue

        def _str_tuple(key: str) -> tuple[str, ...]:
            return tuple(
                str(v).strip() for v in (body.get(key) or []) if str(v).strip()
            )

        # Ignore any legacy keep_genre_ids / reject_genre_ids in overlays —
        # discover ids must come from live name resolve.
        packs[pid] = FacetPack(
            id=pid,
            label=str(body.get("label") or pid),
            concept_id=str(body.get("concept") or body.get("concept_id") or "").strip(),
            match_pattern=str(body.get("match_pattern") or ""),
            match_aliases=_str_tuple("match_aliases"),
            keyword_queries=_str_tuple("keyword_queries"),
            theme_tokens=_str_tuple("theme_tokens"),
            strong_theme_tokens=_str_tuple("strong_theme_tokens"),
            keep_genre_names=_str_tuple("keep_genre_names"),
            reject_genre_names=_str_tuple("reject_genre_names"),
            reject_overview_patterns=_str_tuple("reject_overview_patterns"),
        )
    return packs


def _parse_intent(raw: Any) -> IntentRules:
    if not isinstance(raw, Mapping):
        return IntentRules()
    negations: List[IntentNegation] = []
    for entry in raw.get("negations") or []:
        if not isinstance(entry, Mapping):
            continue
        pattern = str(entry.get("pattern") or "").strip()
        if not pattern:
            continue
        negations.append(
            IntentNegation(
                pattern=pattern,
                without_genres=str(entry.get("without_genres") or "").strip(),
                without_keywords=str(entry.get("without_keywords") or "").strip(),
            )
        )
    genre_hints: List[IntentGenreHint] = []
    for entry in raw.get("genre_hints") or []:
        if not isinstance(entry, Mapping):
            continue
        pattern = str(entry.get("pattern") or "").strip()
        genres = str(entry.get("genres") or "").strip()
        if not pattern or not genres:
            continue
        genre_hints.append(
            IntentGenreHint(
                pattern=pattern,
                genres=genres,
                prefer_media_type=str(entry.get("prefer_media_type") or "").strip(),
            )
        )
    tv_type_hints: List[IntentTvTypeHint] = []
    for entry in raw.get("tv_type_hints") or []:
        if not isinstance(entry, Mapping):
            continue
        pattern = str(entry.get("pattern") or "").strip()
        tv_type = str(entry.get("tv_type") or "").strip()
        if not pattern or not tv_type:
            continue
        tv_type_hints.append(
            IntentTvTypeHint(
                pattern=pattern,
                tv_type=tv_type,
                media_type=str(entry.get("media_type") or "show").strip() or "show",
            )
        )
    try:
        min_words = int(raw.get("descriptive_ask_min_words") or 5)
    except (TypeError, ValueError):
        min_words = 5
    try:
        lookback = int(raw.get("recent_years_lookback") or 8)
    except (TypeError, ValueError):
        lookback = 8
    return IntentRules(
        descriptive_ask_glue=frozenset(
            str(v).strip().casefold().replace("'", "")
            for v in (raw.get("descriptive_ask_glue") or [])
            if str(v).strip()
        ),
        descriptive_ask_min_words=max(1, min_words),
        recent_years_lookback=max(0, lookback),
        theme_stopwords=frozenset(
            str(v).strip().casefold()
            for v in (raw.get("theme_stopwords") or [])
            if str(v).strip()
        ),
        negations=tuple(negations),
        genre_hints=tuple(genre_hints),
        tv_type_hints=tuple(tv_type_hints),
        recent_pattern=str(raw.get("recent_pattern") or r"\brecent\b"),
    )


def _normalize_taxonomy_mapping(data: Mapping[str, Any]) -> Dict[str, Any]:
    """Accept layered (concepts/aliases/packs) and/or flat v1 overlays.

    Flat ``genre_aliases`` / ``genre_crosswalk`` keys (DATA_DIR overlays) are
    folded into concepts even when a layered seed is already present.
    """
    normalized: Dict[str, Any] = dict(data)
    if "packs" not in normalized and "facet_packs" in normalized:
        normalized["packs"] = normalized.get("facet_packs")

    flat_aliases = _as_str_dict(normalized.get("genre_aliases"))
    flat_crosswalk = _as_str_list_map(normalized.get("genre_crosswalk"))
    has_layered = bool(normalized.get("concepts") or normalized.get("aliases"))

    if not has_layered:
        concepts, aliases = _concepts_from_flat(flat_aliases, flat_crosswalk)
        return {
            **normalized,
            "concepts": {
                cid: {"label": c.label, "names": list(c.names)}
                for cid, c in concepts.items()
            },
            "aliases": aliases,
            "packs": normalized.get("packs") or {},
        }

    if not flat_aliases and not flat_crosswalk:
        return normalized

    # Merge flat overlay tokens into the layered maps.
    concepts = _parse_concepts(normalized.get("concepts"))
    aliases = {
        str(k).casefold(): str(v)
        for k, v in _as_str_dict(normalized.get("aliases")).items()
    }
    extra_concepts, extra_aliases = _concepts_from_flat(flat_aliases, flat_crosswalk)

    # Prefer attaching flat aliases onto existing concepts when the primary
    # name already belongs to one (e.g. "space opera" → Science Fiction).
    name_to_concept: Dict[str, str] = {}
    for concept in concepts.values():
        for name in concept.names:
            name_to_concept[name.casefold()] = concept.id
        if concept.label:
            name_to_concept[concept.label.casefold()] = concept.id

    for alias_key, primary in flat_aliases.items():
        existing_id = name_to_concept.get(primary.casefold())
        if existing_id:
            aliases[alias_key.casefold()] = existing_id
            continue
        # New concept from overlay.
        concept_id = extra_aliases.get(alias_key.casefold()) or extra_aliases.get(
            primary.casefold()
        )
        if concept_id and concept_id in extra_concepts and concept_id not in concepts:
            concepts[concept_id] = extra_concepts[concept_id]
            for name in extra_concepts[concept_id].names:
                name_to_concept[name.casefold()] = concept_id
        if concept_id:
            aliases[alias_key.casefold()] = concept_id

    for concept_id, concept in extra_concepts.items():
        if concept_id in concepts:
            continue
        # Skip if all names already claimed.
        if any(name.casefold() in name_to_concept for name in concept.names):
            continue
        concepts[concept_id] = concept
        for name in concept.names:
            name_to_concept[name.casefold()] = concept_id
        aliases.setdefault(concept.id.casefold(), concept.id)

    return {
        **normalized,
        "concepts": {
            cid: {"label": c.label, "names": list(c.names)} for cid, c in concepts.items()
        },
        "aliases": aliases,
        "packs": normalized.get("packs") or {},
    }


def registry_from_mapping(
    data: Mapping[str, Any], *, source_paths: Sequence[str] = ()
) -> FacetRegistry:
    normalized = _normalize_taxonomy_mapping(data)
    try:
        version = int(normalized.get("version") or 2)
    except (TypeError, ValueError):
        version = 2

    concepts = _parse_concepts(normalized.get("concepts"))
    aliases_raw = _as_str_dict(normalized.get("aliases"))
    aliases = {k.casefold(): v for k, v in aliases_raw.items()}
    # Ensure every concept name/label resolves.
    for concept in concepts.values():
        aliases.setdefault(concept.id.casefold(), concept.id)
        if concept.label:
            aliases.setdefault(concept.label.casefold(), concept.id)
        for name in concept.names:
            aliases.setdefault(name.casefold(), concept.id)

    packs_raw = normalized.get("packs") or normalized.get("facet_packs")
    return FacetRegistry(
        version=version,
        concepts=concepts,
        aliases=aliases,
        facet_packs=_parse_packs(packs_raw),
        tv_types={
            k.casefold(): v for k, v in _as_str_dict(normalized.get("tv_types")).items()
        },
        intent=_parse_intent(normalized.get("intent")),
        motif_search_aliases={
            k.casefold(): v
            for k, v in _as_str_list_map(normalized.get("motif_search_aliases")).items()
        },
        source_paths=tuple(source_paths),
    )


def _load_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        if not path.is_file():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return None
    return payload if isinstance(payload, dict) else None


def candidate_alias_paths() -> List[Path]:
    paths: List[Path] = []
    env = str(os.environ.get("PROJECTIONIST_FACET_ALIASES") or "").strip()
    if env:
        paths.append(Path(env).expanduser())
    data_dir = str(os.environ.get("DATA_DIR") or "").strip()
    if data_dir:
        root = Path(data_dir).expanduser()
        paths.append(root / "taxonomy.json")
        paths.append(root / "facet_aliases.json")
    paths.append(_SEED_PATH)
    return paths


def load_facet_registry(*, force_reload: bool = False) -> FacetRegistry:
    """Load packaged seed, then deep-merge any DATA_DIR / env overlay."""
    global _CACHED
    with _LOCK:
        if _CACHED is not None and not force_reload:
            return _CACHED

        seed = _load_json(_SEED_PATH) or {}
        merged: Dict[str, Any] = deepcopy(seed)
        used: List[str] = []
        if seed:
            used.append(str(_SEED_PATH))

        # Overlay order: DATA_DIR taxonomy, DATA_DIR facet_aliases, then env (env wins).
        data_dir = str(os.environ.get("DATA_DIR") or "").strip()
        if data_dir:
            root = Path(data_dir).expanduser()
            for name in ("taxonomy.json", "facet_aliases.json"):
                overlay = _load_json(root / name)
                if overlay:
                    merged = _deep_merge(merged, overlay)
                    used.append(str(root / name))

        env = str(os.environ.get("PROJECTIONIST_FACET_ALIASES") or "").strip()
        if env:
            overlay = _load_json(Path(env).expanduser())
            if overlay:
                if overlay.get("replace_seed"):
                    merged = deepcopy(overlay)
                    used = [str(Path(env).expanduser())]
                else:
                    merged = _deep_merge(merged, overlay)
                    used.append(str(Path(env).expanduser()))

        _CACHED = registry_from_mapping(merged, source_paths=used)
        return _CACHED


def get_registry() -> FacetRegistry:
    return load_facet_registry()


def reload_registry() -> FacetRegistry:
    return load_facet_registry(force_reload=True)


def reset_registry_cache() -> None:
    """Test helper — drop the process-wide cache."""
    global _CACHED
    with _LOCK:
        _CACHED = None
