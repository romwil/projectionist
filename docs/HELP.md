# Help

CuratorX is a private cinema companion for the library you already own. It talks to *your* Plex catalog — not a Netflix top-10 — so every recommendation, comparison, and "what should we watch?" is grounded in titles you actually have. This page is the in-app guide for **Chat**, **Explore**, **Plot Lab**, and — for owners — idle curation.

New here? Start with **[Chat](/)** and just ask for something in plain language. Everything below shows you the shortest path to a result, then explains how it works so you can trust it.

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
| Save a curator reply | **Save to library** below any curator response, then open [Library](/library) |
| Curated shelves | [Lists & playlists](/lists) |
| Personal prefs | [Settings](/settings) |
| Version & release notes | [About](/about) |
| Data use | [Privacy](/privacy) |

Keyboard cheat sheet: press `?` (outside a text field). Slash commands in chat: type `/help`.

---

## For everyone — browse & chat

### Chat

**Ask for what you want in plain language.** The curator uses tools against your indexed library, so it answers from titles you own (it won't invent titles you don't have unless you're in a discovery flow that explicitly searches outside your library).

Try one of these — they're good first prompts because each exercises a different skill:

> **"I love 70s paranoid thrillers — what's missing from my collection?"**
> You get a gap analysis: titles that fit the vibe but aren't in your library yet, each with a reason, plus an allowed request/add action where one is available.

> **"What should we watch tonight, something under two hours I haven't seen?"**
> A short, finishable shortlist drawn from *your* shelves, each with a one-line "why this fits" and a **Play** button when the title has a Plex match.

> **"More like *Michael Clayton* — but tenser."**
> Neighbors and thematic cousins from your library, explained.

> **"Which large files have I never watched?"**
> Purge candidates ranked by size and neglect, so you can reclaim space with confidence.

**How to read the answer.** When Chat discusses collection gaps, its poster strip mirrors the *missing* titles being discussed rather than the owned titles it used as context. A gap card is marked **new** or **queued** and can offer an allowed request/add action; **Play** appears only for a true in-library title with a playable Plex identity. The short **reply chips** under a useful response are suggested next turns — tap one (for example *"only comedies"* or *"go older"*) to send it as your next message without retyping.

**Slash commands** (instant, no LLM call): type `/help` for the list. The handy ones:

- `/stats` — movie/show counts and last sync
- `/rate <title>` — star a watched title (e.g. `/rate Inception`)
- `/purge` — large / unwatched / low-taste candidates

Thumbs up / down on curator replies train future recommendations. Personal **reviews** (stars on titles) are separate from those reactions.

**How this works / why it matters:** the curator issues targeted tool calls against a local SQLite index instead of reading your whole catalog every turn — that's what keeps replies fast, cheap, and grounded in what you own.

### Saving a curator reply to your Library

When a recommendation set or explanation is worth returning to, open the **⋮ menu** below that curator response and choose **Save to library**. CuratorX creates a named, private library item, adds a short summary in your active persona's voice, and keeps it to authenticated household members only. Open saved items later from [Library](/library) — rows are searchable, grouped by day, and show which persona shaped the response.

Saved pages preserve the structured text, title cards, and reply chips. From the same ⋮ menu you can:

- **Copy** the authenticated `/library/:id` link (no public/tokenized links)
- **Export** as **Markdown**, **JSON** (the structured source), or **TXT**
- **Print / PDF** via a clean client-side view
- **Share** through your device share sheet (falls back to Copy link)
- **Chat from here** — opens a *new* conversation seeded with the saved analysis, so you can keep building on the idea without changing the original thread

### Explore

**[Explore](/explore) is cinema browse** over the same SQLite feeds the curator uses. Open it to skim:

- **Recently Added** and **Recent Releases**
- **Revisit These** — partially watched TV that's been idle 60+ days
- **On This Day**
- A daily-rotating **director filmography** and **genre**, plus a nearby calendar-occasion rail (holidays and observances, including Arbor Day) or a gentle season-of-the-year fallback

Those discovery rails only appear when your library has enough matching metadata, and their headings open the matching director or genre wall.

**Library Pulse** sits at the bottom of Explore, paired side-by-side with the knowledge-coverage strip in a shared footer (they stack on narrow screens). Discovery comes first so the hub opens with titles, not dashboard metrics. Posters show watched / in-progress overlays from Plex sync. **Empty rails usually mean enrichment caches are still cold — not that your library is empty.**

### Searching and browsing the library

The **search bar** at the top of Explore looks across your library by title and plot summary. Submit it to open the unified browse page with your results. You can also jump straight into a full, paginated list with the **Browse Movies** and **Browse TV** cards, or the *Movies* / *TV* links on the Recently Added and Recent Releases rails — these show your whole library of that type, not just recent additions.

The browse page uses the same controls as every other wall (sort, direction, type, watch state, year, genres, columns, poster/list, CSV). A **Show** selector picks how many titles load at once: **48**, **100**, **500**, or **All**. With a fixed size you page through results with **Previous** / **Next**; **All** loads everything in one go up to a safety ceiling of 5,000 titles and tells you *"Showing first N of M"* when your library is larger than that. Select titles to pin them to your watchlist in bulk (owners can also remove them from the index).

### What knowledge coverage means

"Knowledge coverage" is an **honesty gauge, not a grade of your library.** It reports how much of each **plot-knowledge layer** the curator has filled in so far: overviews and keywords, semantic embeddings, plot motifs, plot-similarity neighbors, and optional LLM loglines (plus themes and long synopsis when those enrichers run). A high percentage means the curator has rich signals to reason over when it recommends, compares, or explains; a low percentage means idle enrichment still has work to do — recommendations may lean on thinner data until it catches up.

**Why it matters:** every "more like *X*", motif wall, and surprising-neighbor answer is only as deep as the layers behind it. Coverage climbs on its own as the container sits idle and the scheduler trickles metadata, embeddings, motifs, and neighbors. Sparse bars are **expected** right after a big import or an upgrade that improves extraction — they're a to-do list, not a fault. (Owners: nudge specific layers from [Scheduled Tasks](#refreshing-plot-lab-motifs-after-an-update) and read the full breakdown under [Coverage over time](#coverage-over-time).)

### Plot Lab

**[Plot Lab](/explore/plot-lab)** builds facet walls from the plot signals CuratorX has extracted. To get a wall:

1. Open **Plot Lab** from the nav menu or Explore.
2. Tap one or more **motif chips**. Multiple chips mean **intersection (AND)** — titles that carry *all* selected signals.
3. Choose **Multi-signal** (default) so each token can match via motif, keyword, or plot text — or **Motifs only** for pure facet walls.
4. When theme enrichment has run, optional **theme chips** appear and AND with your motif selection.
5. Open **Why?** on a poster to see which layer matched (motif / keyword / plot text) and summary excerpts.
6. Seed a title under **Surprising neighbors** for narrative oddballs from the plot-similarity cache.

**Worked example:** tap `heist` + `betrayal` in **Multi-signal** mode → a wall of your library titles that carry both ideas, even when only one is a formal motif chip and the other lives in the plot text. Switch to **Motifs only** and the same wall tightens to titles where both are extracted facets.

If chips are missing or a wall is empty, see [Why motif walls feel sparse](#why-motif-walls-feel-sparse) and the full [knowledge guide](CURATOR_KNOWLEDGE.md).

### Why? on posters

**Why?** explains a Plot Lab match and cites which layer hit each selected token (motif facet, keyword, or live plot text). It's provenance for the wall — not a spoiler essay.

### Browse controls, lists, and issue reports

Poster walls default to the visual browse view; **List** view makes scanning metadata and watch state faster. Sort, filters, columns, and CSV export deliberately use the same current query, so a shared link, a visible wall, and an exported research slice all mean the same thing. Watchlist and named collections export their current visible membership; library-query walls keep the same visibility rules as the source query.

Three shelves, three different promises:

- **Watchlist** — a personal "remember this" pin. It can merge local pins with Plex Discover sync. Removing a pin never deletes the title from your library.
- **List** — a durable, named CuratorX shelf such as "70s paranoia" or "family guests," for grouping and revisiting.
- **Playlist** — the same local storage with a different intent: an ordered viewing program such as "Friday double feature." It does not sync to Plex Playlists today.

Use the grip's **Add to list or playlist** chooser to place a title in more than one shelf.

**The ⋮ action grip** is repeated on posters, title-card overlays, and list rows on purpose — so "open details," Plex playback when available, watchlist pinning, list/playlist membership, household recommendations, **Recommend like this in chat**, discovery, and **Report issue** all live in one place whether you browse with mouse, keyboard, or touch. The centered **Play** control appears only when a card is a library title with a playable Plex rating key; external discovery cards never show a dead Play action.

**Reporting a title problem — safely.** Anyone who can browse can submit a typed **Report issue** (wrong language, bad video/audio, wrong title, missing subtitles, duplicate, or other) with an optional note. The report captures the title identity and a snapshot of what you saw, then lands in the owner queue at **Admin → Issues**. Members and guests never invoke Radarr or Sonarr commands from a report — this separation protects your files and downloads from accidental changes. An owner decides whether to resolve it or run a supported, logged repair.

### Title detail — Plot knowledge

On a library title, the **Plot knowledge** panel shows which plot layers are present (overview, tagline, logline, and long synopsis when that source exists), motif/keyword/theme chips, and neighbor-cache count. Sparse panels mean idle enrichment is still catching up — the same honesty gauge described under [What knowledge coverage means](#what-knowledge-coverage-means).

### What CuratorX remembers about you

The curator keeps two kinds of memory:

- **Shared knowledge** about titles, people, and companies it has researched, with sources cited. This isn't tied to any one account, so a second question about the same subject recalls the earlier cited answer instead of starting over.
- **Your private memory** — preferences, stated goals, watch intentions, and follow-ups for *your* account only. It's surfaced back to you at the start of a conversation (including a "resume where we left off" nudge) and is never shared with, or applied to, another household member. Youth-mode accounts show a badge in **Profile**; only those accounts can be reviewed by the owner for moderation.

**Your private memory is yours.** CuratorX can hand you a full copy or permanently delete everything it remembers for your account — private notes, chat transcripts, saved library pages, and preference facts. See the [Privacy](/privacy) page for exactly what that export and purge cover, and how to run them.

---

## Why motif walls feel sparse

Plex/TMDB blurbs are short. Motifs are a **small lexical extract** from summary + overview (+ tagline / logline when present). A pure motif AND wall needs every chip present as a facet — so `bride` + `coma` can miss *Kill Bill* even when the free text contains both words, or when TMDB keywords already say `revenge` / `martial arts`.

**Multi-signal** mode fixes that class of miss without inventing plot. Full case study: [CURATOR_KNOWLEDGE.md](CURATOR_KNOWLEDGE.md#case-study-kill-bill--bride--coma).

---

## For owners — curation & scheduler

Owners (or single-workspace installs with no login) also configure sync and idle enrichment. This half is hidden from members and guests, so API and config depth is welcome here.

### After sync

1. Run **Sync library** from Admin / Config (or `/sync` in chat when multi-user is off).
2. Leave the container **idle** so the scheduler can trickle metadata, embeddings, motifs, and neighbors.
3. Open **Admin → Scheduled Tasks** (`/admin/tasks`) — confirm knowledge tasks are enabled; adjust cadence after large imports.

Knowledge-related tasks: `metadata_enrichment`, `semantic_embeddings`, `summary_motifs`, `plot_neighbors`, `title_relations_refresh`, optional `llm_logline_enrichment`.

Kick off a sync from the terminal if you prefer (single-owner install shown):

```bash
# Start a library index job on the owner host
curl -s -X POST http://localhost:8788/api/library/sync
# Watch counts climb
curl -s http://localhost:8788/api/library/stats | python3 -m json.tool
```

### Coverage over time

| Signal | Expectation |
|--------|-------------|
| Overviews / keywords | Climb via sync + metadata trickle |
| Embeddings | Trickle to near-full coverage |
| Motifs | Appear after `summary_motifs` runs; re-run it after upgrades that improve motif extraction |
| Neighbor edges | Often lag embeddings — patience or a tighter `plot_neighbors` cadence |
| LLM loglines | Sparse by design |
| Themes / long synopsis | Appear only after those optional enrichers run |

**Where to read coverage in the app**

- **Admin → Dashboard** — full **Knowledge coverage** panel (% with overview, motifs, keywords, neighbors, loglines; themes/synopsis when present).
- **Admin → Scheduled Tasks** and **Explore** — compact honesty strip so sparsity stays visible while you tune cadence.

Read the same numbers over HTTP when you're scripting a health check:

```bash
# Owner host — coverage percentages the Dashboard panel renders
curl -s http://localhost:8788/api/library/knowledge-coverage | python3 -m json.tool
# → {"overview_pct": 98, "embeddings_pct": 91, "motifs_pct": 63, "neighbors_pct": 44, "loglines_pct": 7}
```

(The same object is nested under `GET /api/library/stats`.) Honest empty "More Like This" / Plot Lab notes mean caches are cold. Owners get a deep link to Scheduled Tasks; members see the note only.

### Refreshing Plot Lab motifs after an update

Motifs are materialized facet rows, not live query results. When a release improves motif quality, open **Admin → Scheduled Tasks** (`/admin/tasks`) and run `summary_motifs` once (or wait for its next idle run). The task safely replaces only motif facets from the existing layered plot text; no full library reindex is needed.

### Telemetry & tuning

Admin shows last-run outcome, durable run history, measured items/hour, owner-set intervals/batch, and ETA (measured when history exists). Auto-tune may adjust batch/interval for trickle tasks within safe caps — you can still override. See [CURATOR_KNOWLEDGE.md — Idle tasks](CURATOR_KNOWLEDGE.md#idle-tasks--purpose-trickle-auto-tune).

### Issue queue and repair policy

Open **Admin → Issues** to triage reports by status. Read the member's note and title identity first, then either resolve/reject the report or run a repair **only when the target is clear**. An owner may opt in to automatic repair for explicitly trusted issue codes, but the default is off.

The safety model is deliberately conservative: auto-repair is an owner policy over narrow, logged playbooks — not a rule that every report should redownload or remove something. Supported high-confidence cases may identify a title already managed by the corresponding *arr service, mark a known bad file where the connector supports it, and request a search. CuratorX does **not** guess a title, delete arbitrary files, correct a bad metadata match blindly, or guarantee subtitles merely because a search was requested. If identity is incomplete, the title isn't managed, or the connector can't act safely, the issue records a clear skip/failure reason. Review the repair log after each run.

### Memory & privacy controls (owner)

Because members can't see this half, here's the exact mechanism behind the member-facing "export or delete your memory" guidance. Each signed-in account can export or purge its own data via `/api/me/memory`:

```bash
# Export everything CuratorX holds for the signed-in account (JSON)
curl -s http://localhost:8788/api/me/memory > my-curatorx-export.json

# Permanently delete the same set — private notes, chat threads + message
# transcripts, saved library pages, and preference facts. Export first.
curl -s -X DELETE http://localhost:8788/api/me/memory
```

Export and purge cover **exactly the same set**, so a copy taken before a purge is complete. Shared, sanitized repository research about media is *not* part of an account purge — it isn't tied to any one account. For **Youth-mode** accounts only, an owner may review or export that account's memory for moderation (`GET /api/users/{id}/memory`, owner-only); adult member memory is never owner-readable. Full data map: [Privacy](/privacy).

### LLM vs free sources

Chat needs an LLM (or Ollama). Library sync, TMDB enrichment, motifs from existing text, keyword→theme mapping, and neighbor materialization do **not** require inventing plot with GPT. Prefer free layers first — details in the [knowledge guide](CURATOR_KNOWLEDGE.md#what-requires-llm-vs-free-sources).

### Long synopsis (Wikipedia by default)

Wikipedia is the default long-synopsis source because it's free, needs no API key, and deepens plot text without an LLM. Fresh installs start trickle-filling automatically (first-start bootstrap may run `long_synopsis_enrichment` once if it has never run).

```jsonc
// {DATA_DIR}/settings.json
{
  "long_synopsis_source": "wikipedia"  // default | "omdb" | "auto" | "off"
}
```

- Default is already `wikipedia` when the setting is missing/unset.
- To stop the trickle, set `long_synopsis_source` to `off` (or `CURATORX_LONG_SYNOPSIS_SOURCE=off`). Empty / `none` / `disabled` also disable it.
- For OMDb (or `auto` fallback), set `omdb_api_key` / `OMDB_API_KEY` and `long_synopsis_source` to `omdb` or `auto`.
- Themes: `keyword_theme_tagging` needs no key. Plot Lab shows theme chips once facets exist.

**First-start bootstrap:** after the idle scheduler starts, never-run foundational tasks (`metadata_enrichment` if backlog, `summary_motifs`, `keyword_theme_tagging`, synopsis when enabled, embeddings only if the store is empty) run once in sequence so coverage doesn't wait days. See [CURATOR_KNOWLEDGE.md](CURATOR_KNOWLEDGE.md#first-start-idle-bootstrap).

### Researching a specific title

When you ask for more plot, cast, crew, or context, the curator can use configured official media APIs rather than guessing from a thin local card: TMDB for details/credits/images, Wikipedia's MediaWiki API without a key, and optional OMDb or TVDB when the owner configures their keys. It reports which sources answered and what remains unavailable. This is media research — not general-purpose open-web browsing or HTML scraping.

Research it has done before is kept in a **persistent, source-cited knowledge store**. Before saying it has nothing, the curator checks what it already knows about a title, person, or company, and refreshes that knowledge when it's gone stale. It cites its sources in the reply.

### MCP (external tools)

CuratorX can expose your **indexed library** to external tools over MCP, gated by which key is presented:

| Key | Typical env | Purpose |
|-----|-------------|---------|
| Privacy MCP key | `CURATORX_MCP_API_KEY` | Read-oriented library intelligence with a **public content** schema |
| Full / in-stack MCP key | `CURATORX_MCP_FULL_API_KEY` | Deeper internal fields + confirm-gated *arr propose tools for trusted LAN automation |

Generate/rotate both in **Admin → Advanced** (or set the env vars); the keys must differ. Privacy mode never exposes `X-Plex-Token` media URLs, `rating_key`, or secrets. Details and the exposure model: [MCP.md](MCP.md) and [Privacy](/privacy).

---

## Related documentation

| Doc | Audience |
|-----|----------|
| [CURATOR_KNOWLEDGE.md](CURATOR_KNOWLEDGE.md) | Why / what / how of library knowledge |
| [ONBOARDING.md](ONBOARDING.md) | First-run wizard & sync |
| [WEB_UI.md](WEB_UI.md) | Routes & chat features |
| [FAQ.md](FAQ.md) | Short Q&A |
| [PRIVACY.md](PRIVACY.md) | What's stored, what leaves the box, export/purge |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Scheduler & Explore APIs |
| [DATA_MODEL.md](DATA_MODEL.md) | Tables & provenance |
| [CONFIGURATION.md](CONFIGURATION.md) | Settings reference |
| [DOCS_STYLE.md](DOCS_STYLE.md) | How these docs are written |
