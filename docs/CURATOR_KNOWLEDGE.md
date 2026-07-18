# Curator knowledge — how CuratorX understands your library

CuratorX does not “remember” every plot the way a streaming catalog’s marketing copy implies. It builds **stacked knowledge dimensions** from free local/Plex/TMDB data first, then optional LLM layers, then presents that knowledge in Chat, Explore, and Plot Lab.

This guide explains **why** motif walls can feel sparse, **what** each knowledge layer is, **how** idle tasks fill them, and **what** owners should expect over time.

In-app entry point: `/help` ([HELP.md](HELP.md)) · related: [ARCHITECTURE.md](ARCHITECTURE.md) · [DATA_MODEL.md](DATA_MODEL.md) · [WEB_UI.md](WEB_UI.md)

---

## Why short blurbs make Plot Lab walls sparse

Most titles arrive with a **Plex summary** and, after enrichment, a **TMDB overview** — typically ~200–300 characters. That is enough for a poster card, and not enough for dense motif intersections.

### Case study: Kill Bill · bride ∩ coma

*Kill Bill: Vol. 1* plot text literally mentions **the Bride** and a **coma**. Yet Plot Lab can still fail a `bride` + `coma` intersection. As of current motif extraction:

1. Motifs are **unigram** tokens from `summary` + `tmdb_overview` only (tagline / keywords are not yet in the motif pipeline).
2. Document-frequency filtering keeps uncommon-but-shared terms (`df ≥ 2`, not ultra-common).
3. Each title keeps at most **8** motifs (`MAX_MOTIFS_PER_ITEM`), preferring rarer tokens — so “bride” can lose the slot race to other rare words.
4. Possessives are not normalized (`bride's` ≠ `bride`), so Vol. 2 may store a different token than Vol. 1.
5. Plot Lab’s motif wall is an **AND** over those facet rows. Missing one chip → empty wall, even when the library “knows” the film in free text or TMDB keywords (`revenge`, `martial arts`, …).

**Takeaway:** Sparse walls are often a **representation / intersection** problem, not an empty library. Keywords and raw plot text are richer than the motif chip set today.

### Roadmap (in flight)

Phase work landing in parallel aims to unlock bride∩coma-style discovery **without** burning LLM tokens:

| Phase | Intent |
|-------|--------|
| **A** | Better motif extraction (normalize possessives, bigrams, retain keyword-aligned tokens) + Plot Lab multi-signal AND (motifs ∪ keywords ∪ live plot-text match) with Why? citing the matching layer |
| **B** | Durable scheduler run history, measured throughput in Admin, auto-tune batch/interval from real runs, neighbor backlog catch-up |
| **C** | Optional long synopsis sources + local keyword→theme mapping; LLM loglines/themes stay last-resort |
| **D** | Coverage UI, title “Plot knowledge” panel, chat tools that prefer structured layers before semantic search |

Until those land, treat empty intersections as **honest**: the motif cache or the 8-slot budget did not retain every salient word.

---

## Knowledge dimensions

Treat curator knowledge as a stack, not one chip wall:

| # | Dimension | What it is | Typical source | Status |
|---|-----------|------------|----------------|--------|
| 1 | **Identity** | Title, year, media type, Plex/TMDB/IMDB ids | Plex sync | Done |
| 2 | **Credits / place** | People, jobs, country, language | TMDB credits + sync | Done |
| 3 | **Catalog tags** | Genres, TMDB keywords | Sync + `metadata_enrichment` | Mostly done; underused in Plot Lab today |
| 4 | **Plot text layers** | summary → overview → tagline → optional long synopsis → rare LLM logline | Plex / TMDB / optional idle | Layered fields exist; long synopsis is roadmap |
| 5 | **Lexical motifs** | Searchable plot tokens in `library_facets` (`facet_type='motif'`) | Idle `summary_motifs` | Weak for multi-chip AND (see case study) |
| 6 | **Tropes / themes** | Controlled vocab (`facet_type='theme'`) | Stub `llm_theme_tagging`; keyword→theme planned | Sparse |
| 7 | **Similarity graph** | Embeddings + `item_neighbors` + `title_relations` | Idle embed / neighbors / relations | Embeddings often full; neighbor edges can lag |
| 8 | **Taste / ops** | Lenses, reviews, purge, watchlist, gaps | User + other idle tasks | Separate from plot depth |

**Principle:** Prefer free/structured sources and local NLP before LLM. LLM stays a thin optional layer for hard gaps. Provenance rules stay sacred — CuratorX must not invent plot ([DATA_MODEL.md](DATA_MODEL.md#provenance-rules-dates--plot-text)).

```mermaid
flowchart LR
  subgraph sources [Sources]
    Plex[Plex summary]
    TMDB[TMDB overview tagline keywords]
    LLM[Optional llm_logline]
  end
  subgraph preprocess [Preprocess idle]
    Motifs[summary_motifs]
    Embed[semantic_embeddings]
    Neigh[plot_neighbors]
  end
  subgraph present [Present]
    PlotLab[Plot Lab]
    Explore[Explore rails]
    Chat[Chat tools]
  end
  Plex --> Motifs
  TMDB --> Motifs
  Plex --> Embed
  TMDB --> Embed
  LLM --> Embed
  Motifs --> PlotLab
  Embed --> Neigh
  Neigh --> Explore
  Motifs --> Chat
  Neigh --> Chat
```

---

## How data is sourced, stored, preprocessed, presented

### Sourced

| Layer | Where it comes from |
|-------|---------------------|
| Plex `summary`, play state, `added_at` | Library sync |
| TMDB `tmdb_overview`, `tagline`, keywords, dates, credits | Sync enrichment + idle `metadata_enrichment` |
| `llm_logline` | Optional idle `llm_logline_enrichment` when a provider is configured — **never invented** if the task skips |
| Motif / theme facets | Idle NLP / optional LLM theme task |
| Embeddings + neighbors | Idle `semantic_embeddings` then `plot_neighbors` |

### Stored

Primary store: `{DATA_DIR}/curatorx.db` (SQLite). Key tables:

- `library_items` — identity + plot text columns + keyword JSON
- `library_facets` — genres/people facets from sync; `motif` / `theme` from idle
- `embeddings` — per-title vectors
- `item_neighbors` — materialized top-K similarity (+ surprise)
- `title_relations` — collection / neighbor / shared-crew edges

See [DATA_MODEL.md](DATA_MODEL.md) for column-level detail.

### Preprocessed (idle)

The **IdleScheduler** runs when chat has been quiet for a threshold. Tasks execute **one at a time** (SQLite write safety), with timeouts and quarantine after repeated failures. Heavy work uses **trickle** batches so a large library does not peg CPU or hold the write lock for minutes.

Agent tools and Explore feeds **read caches**; they do not recompute embeddings or motif DF on every click.

### Presented

| Surface | Knowledge used |
|---------|----------------|
| **Chat** | Tools over library, facets, neighbors, semantic search |
| **Explore** | Feed rails (recently added, releases, On This Day), Pulse |
| **Plot Lab** | Motif chip catalog + AND wall + Why? excerpts; surprising neighbors from seed title |
| **Title detail** | Overview, “More Like This” from `item_neighbors` |
| **Admin → Scheduled Tasks** | Owner cadence + batch, durable recent runs, measured items/hour when history exists, ETA (measured or theoretical) |

---

## Idle tasks — purpose, trickle, auto-tune

### Why idle?

Chat turns must stay snappy. Building motifs across thousands of titles, embedding batches, and materializing neighbor graphs are **batch** jobs. Running them while the household chats would compete for SQLite writes and LLM/embed quota. Idle windows are the homelab-friendly place for that work.

### Purpose of knowledge-related tasks

| Task | Purpose | What “done” looks like |
|------|---------|------------------------|
| `metadata_enrichment` | Fill missing TMDB overview/tagline/keywords/dates/credits | Fewer empty plot fields |
| `semantic_embeddings` | Vectorize layered plot text | Row in `embeddings` per title |
| `plot_neighbors` | Materialize top-K similar titles | Rows in `item_neighbors` |
| `summary_motifs` | Lexical motif facets for Plot Lab | `library_facets` motif rows |
| `title_relations_refresh` | Collection / neighbor / crew graph | `title_relations` edges |
| `llm_logline_enrichment` | Optional one-liner when free text is thin | Sparse `llm_logline` fills |
| `llm_theme_tagging` | Optional theme facets (stub / scarce) | `facet_type='theme'` |

Other tasks (taste, health, anniversary, retention, …) support ops and taste — not plot depth. Full boundary table: [ARCHITECTURE.md — Agent tools vs. background scheduler](ARCHITECTURE.md#agent-tools-vs-background-scheduler).

### Why trickle?

Embeddings and neighbor rebuilds are expensive. Per-cycle caps (e.g. embeddings batch limits) finish a slice, exit with `cycle_limit`, and continue next idle window. That keeps the box responsive and avoids one runaway job blocking the queue.

### Why auto-tune matters

Owners can set **run interval** and **items per run** in Admin → Scheduled Tasks. Every finished run is also written to durable **`scheduled_task_runs`** (survives restart). When enough productive history exists, ETA prefers **measured items/hour**; otherwise it falls back to theoretical backlog × cadence.

After successful trickle runs, auto-tune nudges batch/interval within safety caps from duration vs timeout and backlog ETA vs a target horizon — especially `plot_neighbors` when embeddings are full but neighbor edges are thin. Decisions appear in that run’s metrics (`autotune_*`). Details: [ARCHITECTURE.md](ARCHITECTURE.md#why-last-run-only-failed-and-what-replaced-it).

---

## What owners should expect for coverage over time

After a full library sync on a multi-thousand-title library:

| Signal | Typical early state | Steady state |
|--------|---------------------|--------------|
| Plex summary | High coverage from PMS | Stable |
| TMDB overview / tagline / keywords | Climbs via sync + `metadata_enrichment` trickle | Near-complete over days |
| Embeddings | Climb via `semantic_embeddings` trickle | Often reaches ~100% of titles |
| Motifs | Appear after `summary_motifs` full pass | ~most titles with ≤8 chips each |
| Neighbor edges | Lag embeddings — each title needs a materialization pass | Can remain underbuilt for a long time if cadence is slow |
| LLM loglines | Very sparse by design | Only trickle when provider configured |

**Honest empty states** in Explore / Plot Lab / “More Like This” mean the cache is cold — not that similarity does not exist. Owners see a CTA to **Admin → Scheduled Tasks**; members see the note only.

Practical owner habits:

1. Finish sync, then leave the container idle overnight.
2. In **Admin → Scheduled Tasks**, confirm knowledge tasks are enabled; tighten cadence for `metadata_enrichment`, `plot_neighbors`, and `summary_motifs` after large imports.
3. Use **Warm Explore** (when offered) to fire the enrichment sequence without waiting for natural idle.
4. Re-check Plot Lab motif catalog and a seed title’s neighbors after several cycles.

---

## What requires LLM vs free sources

| Capability | Free / local | Needs LLM / paid embed provider |
|------------|--------------|----------------------------------|
| Identity, credits, genres, TMDB keywords | Yes | No |
| Overview / tagline enrichment | TMDB API key (free tier) | No |
| Motif facets from existing text | Local NLP idle task | No |
| Keyword→theme map (roadmap) | Local | No |
| Long synopsis from OMDb/Wikipedia (roadmap) | Operator-keyed, rate-limited | No LLM |
| Embeddings | Hash fallback or local/OpenAI-compatible embed model | Depends on configured embed path |
| Chat curator personality / tool-using answers | — | Yes (or local Ollama) |
| `llm_logline` / LLM theme tagging | — | Yes, optional trickle |

**Policy:** never invent plot. If a free field is empty, it stays empty until a real source fills it.

---

## Using knowledge in the product

### End users (members / guests)

- **Chat** — ask for plot-ish intersections (“revenge martial arts under 2 hours”); the agent uses tools over library + facets when available.
- **Explore** — browse rails; empty rails usually mean cold caches.
- **Plot Lab** (`/explore/plot-lab`) — tap motif chips (AND when multiple); open **Why?** on a poster for motif + summary excerpts; seed a title for surprising neighbors.
- **Title detail** — “More Like This” reads `item_neighbors`.
- **Help** (`/help`, [HELP.md](HELP.md)) — role-aware guidance; links here for depth.

### Owners / admins

Everything above, plus:

- **Admin → Scheduled Tasks** — enable/disable, cadence, last outcome, ETA, quarantine reset.
- **Admin → Dashboard** — library composition / health (not yet a full “knowledge coverage” strip — roadmap Phase D).
- Expect motif quality and neighbor density to improve as idle work catches up; do not expect Chat to recompute the whole graph per turn.

---

## Related docs

| Doc | Role |
|-----|------|
| [HELP.md](HELP.md) | In-app Help source (`/help`) |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Scheduler boundary, trickle, Explore APIs |
| [DATA_MODEL.md](DATA_MODEL.md) | Tables and provenance |
| [WEB_UI.md](WEB_UI.md) | Routes and Plot Lab UX |
| [ONBOARDING.md](ONBOARDING.md) | First sync → idle warm-up |
| [FAQ.md](FAQ.md) | Short answers (“Why is Plot Lab empty?”) |
