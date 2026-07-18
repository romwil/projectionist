# Help

CuratorX is a private cinema companion for the library you already own. This page is the in-app guide for Chat, Explore, Plot Lab, and — for owners — idle curation.

Deep dive: [CURATOR_KNOWLEDGE.md](CURATOR_KNOWLEDGE.md) · [About](/about) · [Privacy](/privacy)

---

## Start here

| Goal | Where |
|------|--------|
| Talk to your curator | [Chat](/) |
| Browse rails & Pulse | [Explore](/explore) |
| Motif walls & surprising neighbors | [Plot Lab](/explore/plot-lab) |
| Tag / keyword search | [Tags](/explore/tags) |
| Pins | [Watchlist](/watchlist) |
| Curated shelves | [Lists & playlists](/lists) |
| Personal prefs | [Settings](/settings) |
| Version & release notes | [About](/about) |
| Data use | [Privacy](/privacy) |

Keyboard cheat sheet: press `?` (outside a text field). Slash commands in chat: type `/help`.

---

## For everyone — browse & chat

### Chat

Ask in natural language: taste gaps, tonight picks, purge candidates, “more like *X*”. The curator uses tools against your indexed library — it does not invent titles you do not have unless you are in a discovery flow that explicitly searches outside the library.

Useful slash commands (no LLM call):

- `/help` — command list
- `/stats` — movie/show counts and last sync
- `/rate <title>` — star a watched title
- `/purge` — large / unwatched / low-taste candidates

Thumbs up / down on curator replies train future recommendations. Personal **reviews** (stars on titles) are separate from those reactions.

### Explore

Cinema browse over the same SQLite feeds the agent uses: Recently Added, Recent Releases, Revisit These (partially watched TV idle 60+ days), On This Day, and links into Plot Lab / Tags. Posters show watched / in-progress overlays from Plex sync. Empty rails usually mean enrichment caches are still cold — not that your library is empty.

### Plot Lab

1. Open **Plot Lab** from the nav menu or Explore.
2. Tap one or more **motif chips**. Multiple chips mean **intersection (AND)** — titles that carry *all* selected signals.
3. Choose **Multi-signal** (default) so each token can match via motif, keyword, or plot text — or **Motifs only** for pure facet walls.
4. When theme enrichment has run, optional **theme chips** appear and AND with your motif selection.
5. Open **Why?** on a poster for which layer matched (motif / keyword / plot text) and summary excerpts.
6. Seed a title under **Surprising neighbors** for narrative oddballs from the plot-similarity cache.

If chips are missing or a wall is empty, see [Why walls feel sparse](#why-motif-walls-feel-sparse) and the full [knowledge guide](CURATOR_KNOWLEDGE.md).

### Why? on posters

**Why?** explains a Plot Lab match and cites which layer hit each selected token (motif facet, keyword, or live plot text). It is provenance for the wall — not a spoiler essay.

### Browse controls, lists, and issue reports

Poster walls default to the visual browse view, while **List** view makes scanning metadata and watch state faster. Sort, filters, and CSV export deliberately use the same current query so a shared link, a visible wall, and an exported research slice mean the same thing.

Use a **watchlist** for personal “remember this” pins. Use a **list** for a durable curated shelf; use a **playlist** for a deliberate viewing sequence. They share the same collection engine, but express different intent so a future watch does not get confused with a planned program.

The ⋮ grip on posters and list rows keeps common actions in one location. **Report issue** records a typed report for an owner; it never directly changes Plex or *arr. Owners decide whether to resolve it or run a supported, logged repair. This separation protects files and downloads from accidental member actions.

### Title detail — Plot knowledge

On a library title, the **Plot knowledge** panel shows which plot layers are present (overview, tagline, logline, and long synopsis when that source exists), motif/keyword/theme chips, and neighbor-cache count. Sparse panels mean idle enrichment is still catching up.

---

## Why motif walls feel sparse

Plex/TMDB blurbs are short. Motifs are a **small lexical extract** from summary + overview (+ tagline / logline when present). A pure motif AND wall needs every chip present as a facet — so `bride` + `coma` can miss *Kill Bill* even when free text contains both words, or when TMDB keywords already say `revenge` / `martial arts`.

**Multi-signal** mode fixes that class of miss without inventing plot. Full case study: [CURATOR_KNOWLEDGE.md](CURATOR_KNOWLEDGE.md#case-study-kill-bill--bride--coma).

---

## For owners — curation & scheduler

Owners (or single-workspace installs with no login) also configure sync and idle enrichment.

### After sync

1. Run **Sync library** from Admin / Config (or `/sync` when multi-user is off).
2. Leave the container **idle** so the scheduler can trickle metadata, embeddings, motifs, and neighbors.
3. Open **Admin → Scheduled Tasks** (`/admin/tasks`) — confirm knowledge tasks are enabled; adjust cadence after large imports.

Knowledge-related tasks: `metadata_enrichment`, `semantic_embeddings`, `summary_motifs`, `plot_neighbors`, `title_relations_refresh`, optional `llm_logline_enrichment`.

### Coverage over time

| Signal | Expectation |
|--------|-------------|
| Overviews / keywords | Climb via sync + metadata trickle |
| Embeddings | Trickle to near-full coverage |
| Motifs | Appear after `summary_motifs` runs |
| Neighbor edges | Often lag embeddings — patience or tighter `plot_neighbors` cadence |
| LLM loglines | Sparse by design |
| Themes / long synopsis | Appear only after those optional enrichers run |

**Where to read coverage in the app**

- **Admin → Dashboard** — full **Knowledge coverage** panel (% with overview, motifs, keywords, neighbors, loglines; themes/synopsis when present).
- **Admin → Scheduled Tasks** and **Explore** — compact honesty strip so sparsity stays visible while you tune cadence.
- API: `GET /api/library/knowledge-coverage` (also nested under `/api/library/stats`).

Honest empty “More Like This” / Plot Lab notes mean caches are cold. Owners get a deep link to Scheduled Tasks; members see the note only.

### Telemetry & tuning

Admin shows last-run outcome, durable run history, measured items/hour, owner-set intervals/batch, and ETA (measured when history exists). Auto-tune may adjust batch/interval for trickle tasks within safe caps — you can still override. See [CURATOR_KNOWLEDGE.md — Idle tasks](CURATOR_KNOWLEDGE.md#idle-tasks--purpose-trickle-auto-tune).

### LLM vs free sources

Chat needs an LLM (or Ollama). Library sync, TMDB enrichment, motifs from existing text, keyword→theme mapping, and neighbor materialization do **not** require inventing plot with GPT. Prefer free layers first — details in the [knowledge guide](CURATOR_KNOWLEDGE.md#what-requires-llm-vs-free-sources).

### Owner: long synopsis (Wikipedia by default)

Wikipedia is the default long-synopsis source because it is free, needs no API key, and deepens plot text without an LLM. Fresh installs start trickle-filling automatically (and first-start bootstrap may run `long_synopsis_enrichment` once if it has never run).

1. Default is already `wikipedia` when the setting is missing/unset.
2. To turn the trickle off, set `long_synopsis_source` to **`off`** in `{DATA_DIR}/settings.json` (or `CURATORX_LONG_SYNOPSIS_SOURCE=off`). Empty / `none` / `disabled` also disable.
3. For OMDb (or `auto` fallback), set `omdb_api_key` / `OMDB_API_KEY` and `long_synopsis_source` to `omdb` or `auto`.
4. Themes: `keyword_theme_tagging` needs no key. Plot Lab shows theme chips once facets exist.

**First-start bootstrap:** after the idle scheduler starts, never-run foundational tasks (`metadata_enrichment` if backlog, `summary_motifs`, `keyword_theme_tagging`, synopsis when enabled, embeddings only if the store is empty) run once in sequence so coverage does not wait days. See [CURATOR_KNOWLEDGE.md](CURATOR_KNOWLEDGE.md#first-start-idle-bootstrap).

---

## Related documentation

| Doc | Audience |
|-----|----------|
| [CURATOR_KNOWLEDGE.md](CURATOR_KNOWLEDGE.md) | Why / what / how of library knowledge |
| [ONBOARDING.md](ONBOARDING.md) | First-run wizard & sync |
| [WEB_UI.md](WEB_UI.md) | Routes & chat features |
| [FAQ.md](FAQ.md) | Short Q&A |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Scheduler & Explore APIs |
| [DATA_MODEL.md](DATA_MODEL.md) | Tables & provenance |
| [CONFIGURATION.md](CONFIGURATION.md) | Settings reference |
