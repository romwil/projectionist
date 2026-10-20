# Media intelligence

Living map of how Projectionist turns library text and watch evidence into **honest** relatedness. Cosine similarity alone is not a reason to recommend a title.

Related: [CURATOR_KNOWLEDGE.md](CURATOR_KNOWLEDGE.md) · [DATA_MODEL.md](DATA_MODEL.md) · [ARCHITECTURE.md](ARCHITECTURE.md)

---

## North star

Recommendations and discovery must cite a **concrete link** to something this household watched, saved, or cares about — a named plot subject, shared director/writer, or shared collection. Empty shelves mean “no named link,” not a silent embedding miss.

---

## System map (baseline)

```mermaid
flowchart LR
  sources[Plex / TMDB / wiki]
  items[library_items + people/credits + facets]
  emb[embeddings]
  neigh[item_neighbors]
  rel[title_relations]
  ui[More Like This / relations / inbox]
  sources --> items
  items --> emb
  emb --> neigh
  neigh --> rel
  items --> rel
  neigh --> ui
  rel --> ui
```

| Layer | Store | Idle / sync |
|-------|--------|-------------|
| Identity + plot text | `library_items` | sync + `metadata_enrichment` / synopsis |
| Credits | `people` / `credits` | TMDB enrichment |
| Lexical facets | `library_facets` (`genre`, `motif`, `keyword`, `theme`, …) | sync facets + `summary_motifs` |
| Vectors | `embeddings` | `semantic_embeddings` |
| Similarity cache | `item_neighbors` (`score`, `surprise_score`, **`explainable`**, **`plot_link_json`**) | `plot_neighbors` |
| Graph edges | `title_relations` (`collection`, `neighbor`, `shared_crew`, `directed_by`, `written_by`) | `title_relations_refresh` |

Watch ledger (`watch_completions` / `watch_sessions` / terminal `watch_events`) plus `watchlist_pins` seed inbox bridges (Release 2).

---

## Critical tensions

1. **Coverage over-counts.** Raw `with_neighbors_pct` counts any cosine peer. Owners used to read that as “useful relatedness.” Release 1 splits **Similar cache** vs **Named kinship** (`with_explainable_neighbors_pct`).
2. **Cosine ≠ why.** `_why_payload` / `specific_plot_link` already refused generic neighbor labels at read time; Release 1 **materializes** that gate on `item_neighbors` so feeds never surface cosine-only peers.
3. **Genre facets.** Sync emits `facet_type='genre'` from `library_items.genres` (Release 3); JSON on the item row remains the source of truth and a query fallback.
4. **Motif budget.** Each title keeps at most **18** motifs (`MAX_MOTIFS_PER_ITEM` = 12 rare + 6 keyword-bonus), not the historical 8-slot hard cap.
5. **Schema location.** Ordered migrations live in `projectionist/library/db/migrations.py`; migration bodies in `projectionist/library/db/_schema.py` (and a few inline helpers in `migrations.py`). Primary DB file: `{DATA_DIR}/projectionist.db` (legacy `curatorx.db` still opened if present).

---

## Release series

| Release | Theme | Status |
|---------|--------|--------|
| **1** | Explainable kinship — materialize `explainable` + explanation objects; coverage split; `MEDIA_INTELLIGENCE.md` | Done (1.37.54) |
| **2** | Household bridges — inbox/whisper/weekly cite watch/watchlist seeds with named links | Done (1.37.55) |
| **3** | Catalog graph — genre facets, person-centric edges, keyword-first Related titles | Done (1.37.56) |
| **4** | Owner demand catch-up — miss signals → idle priority; Admin promotes explainable % | Planned |

### Release 1 notes

- Shared explanation shape: `{kind, sentence, seed_ids?, peer_id?, terms[], evidence}` for `plot_link` | `shared_crew` | `collection` | `watched_bridge`. Built next to `specific_plot_link` / `_why_payload`.
- `item_neighbors.explainable` + `plot_link_json` filled on neighbor build (and a cheap annotate pass for legacy rows).
- Relations mirror and More Like This read **explainable** rows only.
- Admin / Explore coverage shows raw neighbor % and explainable %.

### Release 2 notes

- **Seeds** prefer `watch_completions`, then recent `watch_sessions`, then terminal `watch_events`, plus `watchlist_pins`. Library `view_count` / `last_viewed_at` is a last resort only when the ledger is empty.
- **Bridge builder** (`recommendation_reasons.bridge_between`) finds peers via explainable neighbors, shared crew, or collection and emits `kind=watched_bridge` (“You finished *X*; *Y* — …”). No seed → no fake “because you watched.”
- **Nudges, whispers, and weekly member newsletters** pick through the same path. When `multi_user_enabled`, prefer the acting member’s evidence, then fall back to the household.
- Cosine-only neighbors stay excluded from candidate discovery (`explainable_only=True`).

### Release 3 notes

- **Genre facets** — `_collect_facet_rows` / `rebuild_library_facets` emit `facet_type='genre'`; catalog + ensure-backfill treat genre like country/language.
- **Person-centric edges** — `directed_by` / `written_by` for solo auteur pairs (capped per title); multi-person overlap stays `shared_crew` (`min_shared=2`). Why labels name the person.
- **Keywords as first-class why** — Related titles carry `shared_keywords` on every why payload; Plot Lab Why? merges facet + item JSON keywords into `match_layers`.
- **Softer empty walls** — Plot Lab default remains multi-signal (`hybrid` AND). `plot_match_mode=any` is ranked OR across tokens when a strict AND would miss keyword/plot hits.

---

## Success signals

| Release | Signal |
|---------|--------|
| R1 | Explainable neighbor % visible; More Like This never shows cosine-only peers |
| R2 | New inbox/whisper rows cite a watched/pinned seed + named link |
| R3 | Genre facet filter works; solo-director shelves where credits exist |
| R4 | Missed titles show accelerated enrichment in task metrics / Admin |
