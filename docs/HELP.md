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

Poster walls default to the visual browse view, while **List** view makes scanning metadata and watch state faster. Sort, filters, columns, and CSV export deliberately use the same current query so a shared link, a visible wall, and an exported research slice mean the same thing. Watchlist and named collections export their current visible membership; library-query walls keep the same visibility rules as the source query.

Use a **watchlist** for personal “remember this” pins. Use a **list** for a durable curated shelf; use a **playlist** for a deliberate viewing sequence. They share the same collection engine, but express different intent so a future watch does not get confused with a planned program.

The ⋮ grip on posters and list rows keeps common actions in one location. **Report issue** records a typed report for an owner; it never directly changes Plex or *arr. Owners decide whether to resolve it or run a supported, logged repair. This separation protects files and downloads from accidental member actions.

#### A practical browse workflow

Start broad on an Explore, Tag, Plot Lab, Watchlist, or collection wall, then narrow deliberately: choose a media type or watch state, select a year or genre when that surface offers it, choose a sort direction, and switch to **List** when you want to compare facts instead of artwork. The controls keep that choice in the URL where the wall supports it, so refresh and sharing do not silently reset a research slice. **Export CSV** is not an unrestricted database dump: library-query results export the active query under the same member visibility rules as the wall, while an Explore feed exports only its current loaded page and visible columns.

The small **⋮ action grip** is deliberately repeated on posters, title-card overlays, and list rows. It puts “open details,” Plex playback when available, watchlist pinning, list/playlist membership, household recommendations, **Recommend like this in chat**, discovery, and issue reporting in the same place whether you are browsing with a mouse, keyboard, or touch. “Recommend like this” opens Chat with the title and year as context, then sends a request to discuss the title and find related picks. It is an action launcher, not a bypass around permissions: owner-only index operations stay owner-only, and a report is never a hidden repair button.

The small horizontal rails on the Explore hub and Plot Lab’s **Surprising neighbors**, plus a person’s credit-annotated filmography, intentionally stay context-dense rather than repeating a full browse toolbar in every short embedded strip. They still use the same card/grip actions; choose the linked full Explore section, Tag, or Plot wall when you need filters, List view, or CSV.

#### Lists, playlists, and watchlist are different promises

- **Watchlist:** a personal reminder. It can merge local pins with Plex Discover sync and answers “keep this on my radar.” Removing a pin does not delete the title from your library.
- **List:** a durable, named CuratorX shelf such as “70s paranoia” or “family guests.” It is for grouping and revisiting.
- **Playlist:** the same local collection storage with a different intent: an ordered or deliberate viewing program such as “Friday double feature.” It does not sync to Plex Playlists today.

Use the grip’s **Add to list or playlist** chooser to place a title in more than one shelf. On a playlist wall, its matching action is **Remove from this playlist**, which changes only that membership.

#### Reporting a title problem safely

Anyone who can browse can submit a typed report such as wrong language, bad video/audio, wrong title, missing subtitles, duplicate, or other—with an optional note. The report records the title identity and a snapshot of what the member saw, then appears in the owner queue at **Admin → Issues**. This is useful because the person who hits a playback problem can describe it immediately, while the person who manages storage and *arr gets one durable, auditable place to decide what happens next.

Members and guests never invoke Radarr or Sonarr repair commands from a report. Owners can reject, resolve, approve, or run a supported repair; every attempt is logged back on the issue. Supported high-confidence cases may identify a title already managed by the corresponding *arr service, mark a known bad file where the connector supports it, and request a search. CuratorX does **not** guess a title, delete arbitrary files, correct a bad metadata match blindly, or guarantee subtitles merely because a search was requested. If identity is incomplete, the title is not managed, or the connector cannot safely perform the action, the issue records a clear skip/failure reason for owner review.

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

### Owner: issue queue and repair policy

Open **Admin → Issues** to triage reports by status. Read the member’s note and title identity first; then either resolve/reject the report or run a repair only when the target is clear. An owner may opt in to automatic repair for explicitly trusted issue codes, but the default is off. The safety model is intentionally conservative: auto-repair is an owner policy over narrow, logged playbooks—not a rule that every report should redownload or remove something. Review the repair log after each run, especially for *arr availability, library identity, and command results.

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
