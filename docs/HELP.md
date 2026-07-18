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

Cinema browse over the same SQLite feeds the agent uses: Recently Added, Recent Releases, On This Day, and links into Plot Lab / Tags. Empty rails usually mean enrichment caches are still cold — not that your library is empty.

### Plot Lab

1. Open **Plot Lab** from the nav menu or Explore.
2. Tap one or more **motif chips**. Multiple chips mean **intersection (AND)** — titles that carry *all* selected motifs.
3. Open **Why?** on a poster for which motifs matched and plot-summary excerpts.
4. Seed a title under **Surprising neighbors** for narrative oddballs from the plot-similarity cache.

If chips are missing or a wall is empty, see [Why walls feel sparse](#why-motif-walls-feel-sparse) and the full [knowledge guide](CURATOR_KNOWLEDGE.md).

### Why? on posters

**Why?** explains a Plot Lab match using selected motifs and summary excerpts. It is provenance for the wall — not a spoiler essay. (Roadmap: cite keyword vs motif vs live text layer when multi-signal search lands.)

---

## Why motif walls feel sparse

Plex/TMDB blurbs are short. Motifs are a **small lexical extract** (today: up to eight uncommon unigrams per title from summary + overview). An AND wall needs every chip present as a facet — so `bride` + `coma` can miss *Kill Bill* even when the free text contains both words, or when TMDB keywords already say `revenge` / `martial arts`.

That is a representation limit, not a broken library. Full case study and roadmap: [CURATOR_KNOWLEDGE.md](CURATOR_KNOWLEDGE.md#case-study-kill-bill--bride--coma).

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

Honest empty “More Like This” / Plot Lab notes mean caches are cold. Owners get a deep link to Scheduled Tasks; members see the note only.

### Telemetry & tuning (as of this release + roadmap)

**As of this release:** Admin shows last-run outcome, owner-set intervals, and theoretical backlog ETAs. Live run logs are in-memory and reset on restart.

**Roadmap:** durable run history, measured items/hour, and auto-tune of batch size / interval from real durations — especially to catch up neighbor graphs. See [CURATOR_KNOWLEDGE.md — Idle tasks](CURATOR_KNOWLEDGE.md#idle-tasks--purpose-trickle-auto-tune).

### LLM vs free sources

Chat needs an LLM (or Ollama). Library sync, TMDB enrichment, motifs from existing text, and neighbor materialization do **not** require inventing plot with GPT. Prefer free layers first — details in the [knowledge guide](CURATOR_KNOWLEDGE.md#what-requires-llm-vs-free-sources).

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
