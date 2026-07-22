# Help

CuratorX is a private cinema companion for the library you already own. It talks to *your* Plex catalog — not a Netflix top-10 — so every recommendation, comparison, and "what should we watch?" is grounded in titles you actually have. This page is the in-app guide for **Chat**, **Search**, **Explore**, **Inbox**, **My Journey**, **Plot Lab**, and — for owners — idle curation.

New here? Start with **[Chat](/chat)** and just ask for something in plain language. The top bar keeps Search, Chat, Explore, Inbox, My Journey, and Settings as peer destinations (owners also see Admin). Everything below shows you the shortest path to a result, then explains how it works so you can trust it.

Deep dive: [CURATOR_KNOWLEDGE.md](CURATOR_KNOWLEDGE.md) · [About](/about) · [Privacy](/privacy)

---

## Start here

| Goal | Where |
|------|--------|
| Talk to your curator | [Chat](/chat) |
| Search your collection (and beyond) | [Search](/search) |
| Browse rails & Pulse | [Explore](/explore) |
| Recommendations & notices | [Inbox](/inbox) |
| Achievements & cinema pathways | [My Journey](/my-journey) |
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

- **Continue Watching** — in-progress titles from Plex On Deck (resume + Play), not a live "now playing" session list
- **For you this week** — personalized unwatched picks with a short persona-voiced *why* (built on the weekly digest cadence). Tap **Why this?** on a card, or use **Chat about these** to discuss the same saved picks with those reasons attached.
- **Recently Added** and **Recent Releases**
- **Revisit These** — partially watched TV that's been idle 60+ days
- **On This Day**
- A daily-rotating **director filmography** and **genre**, plus a nearby calendar-occasion rail (holidays and observances, including Arbor Day) or a gentle season-of-the-year fallback

**Chat about a rail.** Most Explore rails offer **Chat about these** — it opens a new conversation seeded with that rail's titles, stable library identities, and the persona *why* when present, so the curator discusses those same in-library picks (not outside search replacements).

Those discovery rails only appear when your library has enough matching metadata, and their headings open the matching director or genre wall.

### For you weekly rail

Your **For you** rail is rebuilt about once a week alongside the library digest. It prefers unwatched titles that match your taste clusters, saves each pick with its library id and a short reason in your default curator's voice, and surfaces that reason on **Why this?** and when you **Chat about these**.

Tune the underlying weights under **Settings → Taste** — raise a cluster, lower another, and **Lock** anything you don't want the automatic refresh to drift. Locked weights stay put; unlocked ones can still learn from reviews and chat feedback.

> **Example:** You lock `noir` high and leave `comedy` unlocked. Next week's For you leans hard into noir thrillers you haven't watched, while comedy weights can still soften if you keep rating rom-coms highly.

**How it works / honest limits.** The scheduler fans out one rail per member with a hard cap on optional LLM polish (v1 uses persona template voice). Empty rails usually mean cold taste data — rate a few titles or chat first.

### Taste profile

**Settings → Taste** shows the cluster tags CuratorX learned for you (genres, moods, eras). Drag a weight, lock it, or **Reset** an override to fall back to the household lens baseline.

### My Journey — achievements, pathways, and secrets

Open **[My Journey](/my-journey)** from the top bar (the route icon, immediately left of Settings) for your cinema discovery path:

- **List** or **Achievements Tree** — Civ-style pathways toward ultimate category badges
- **Progress** — earned, in progress, and hidden secrets found
- **Persona pathways** — branches that encourage trying curator voices
- **Hidden achievements** — silhouette / "???" awards until you earn them
- **Cinema courses** and **Explainers** — learning along the way
- **Chat streak** — consecutive chat days plus your 30-day conversation count

Youth-mode accounts see youth-safe achievements only. Member-facing copy never says “engagement.”

**Surprise Me with a mood.** Above the dice in chat, optional mood chips (**Cozy**, **Thrill**, **Laugh**, **Think**, **Escape**) bias a *single* pick. They do not overwrite your durable taste profile.

**Scholar footnotes in chat.** When the curator cites sources with footnote-style markdown (`claim[^1]` plus `[^1]: source` definitions), chat renders them as theme-safe footnote refs under the reply.

**Ask to acquire a title.** In chat you can ask the Concierge to walk find → availability → Seerr request with explicit steps. Nothing is requested until you confirm.

**Where can I watch this?** On title detail (and on chat recommendation posters) CuratorX shows a compact availability line: **In your library ✓**, **Requestable** (when Seerr is your request path), or **Not here yet**. It does not look up Netflix, Max, or other external streamers.

**Watchlist pins feel instant.** Adding or removing a pin updates your wall immediately; CuratorX reconciles with Plex Discover in the background when sync is enabled.

### Inbox & notifications

**[Inbox](/inbox)** is a top-bar peer (the notifications icon). Unread items show a badge. Household recommendations, title arrivals, digests, and curator **nudges** all land there — not inside Chat.

Under **Settings → Notifications** you can:

- Set a **notification email** (or leave blank to use your account email)
- Turn the **in-app inbox** on or off
- Opt into **email alerts** when the owner has mail configured
- Subscribe to the **weekly newsletter** — a short, personalized note in your default curator’s voice (guest accounts get a guest-friendly voice when available)
- Opt into **curator nudges** — occasional “you have to see this” picks (optionally reacting to what you recently watched / continue-watching). These are never live Plex session alerts.

Dismiss a card when you’re done; **Dismiss all** clears the unread stack.

**Library Pulse** sits at the bottom of Explore, paired side-by-side with the knowledge-coverage strip in a shared footer (they stack on narrow screens). Discovery comes first so the hub opens with titles, not dashboard metrics. Posters show watched / in-progress overlays from Plex sync. **Empty rails usually mean enrichment caches are still cold — not that your library is empty.**

### Searching and browsing the library

**[Search](/search)** is the top-level collection search. Explore’s search box sends you there. Browse filters, facets, and **Beyond your collection** live on the same page.

The **search bar** at the top of Explore looks across your library by title and plot summary. Submit it to open the unified browse page with your results. You can also jump straight into a full, paginated list with the **Browse Movies** and **Browse TV** cards, or the *Movies* / *TV* links on the Recently Added and Recent Releases rails — these show your whole library of that type, not just recent additions.

The browse page uses the same controls as every other wall (sort, direction, type, watch state, year, genres, columns, poster/list, CSV). A **Show** selector picks how many titles load at once: **48**, **100**, **500**, or **All**. With a fixed size you page through results with **Previous** / **Next**; **All** loads everything in one go up to a safety ceiling of 5,000 titles and tells you *"Showing first N of M"* when your library is larger than that. Select titles to pin them to your watchlist in bulk (owners can also remove them from the index).

### Search beyond the collection

Sometimes the thing you want isn't in the library yet. Whenever you've searched, look for **Search beyond your collection** — it's front and center when nothing in your library matched, and a quieter button below your results otherwise. Tap it and CuratorX looks up matching movies or shows from the wider film database, then shows them in a clearly separated **Beyond your collection** section.

> **You search:** "arrival"
>
> **Your library has nothing** — so **Search beyond your collection for "arrival"** sits right in the empty state. Tap it and *Arrival (2016)* and its neighbors appear under **Beyond your collection**, each with a poster, a link to full details, and — depending on who you are — a way to bring it in.

What the button on each beyond result does depends on your role, and CuratorX never double-adds something you already have:

- **Owners** get **Add to Radarr** (movies) or **Add to Sonarr** (shows), which queues the title for download.
- **Members** get **Request in Seerr**, sending it to the household request queue for approval.
- **Guests** see a gentle *"Ask owner"* note instead of a button — browsing and discovery stay open to everyone, but only owners and members can bring titles in.

Anything already in your library (or already queued to download) is shown with an **In library** or **In queue** badge and no add button, so you can see it exists without accidentally requesting a duplicate. If external search isn't available, the button steps aside with a short note rather than failing loudly.

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

**Mark as watched — a guided one-tap.** For any title that lives in your Plex library, the grip offers **Mark as watched**. Say you just finished *Heat* on the TV downstairs but forgot to press play in Plex — open the ⋮ menu on its poster and choose **Mark as watched**. CuratorX records the view and tells Plex, so the poster's watched overlay turns on and the title stops showing up as "unwatched" everywhere it appears. Changed your mind, or marked the wrong one? The same spot now reads **Mark as unwatched** and reverses it. The action only appears on real library titles (the same rule as **Play**) — discovery cards for things you don't own never show it — and, like everything else, it's tied to *your* signed-in Plex context.

**Reporting a title problem — safely.** Anyone who can browse can submit a typed **Report issue** (wrong language, bad video/audio, wrong title, missing subtitles, duplicate, or other) with an optional note. The report captures the title identity and a snapshot of what you saw, then lands in the owner queue at **Admin → Issues**. Members and guests never invoke Radarr or Sonarr commands from a report — this separation protects your files and downloads from accidental changes. An owner decides whether to resolve it or run a supported, logged repair.

### Title detail — Plot knowledge

On a library title, the **Plot knowledge** panel shows which plot layers are present (overview, tagline, logline, and long synopsis when that source exists), motif/keyword/theme chips, and neighbor-cache count. Sparse panels mean idle enrichment is still catching up — the same honesty gauge described under [What knowledge coverage means](#what-knowledge-coverage-means).

### What CuratorX remembers about you

The curator keeps two kinds of memory:

- **Shared knowledge** about titles, people, and companies it has researched, with sources cited. This isn't tied to any one account, so a second question about the same subject recalls the earlier cited answer instead of starting over.
- **Your private memory** — preferences, stated goals, watch intentions, and follow-ups for *your* account only. It's surfaced back to you at the start of a conversation (including a "resume where we left off" nudge) and is never shared with, or applied to, another household member. Youth-mode accounts show a badge in **Profile**; only those accounts can be reviewed by the owner for moderation.

**Your private memory is yours.** CuratorX can hand you a full copy or permanently delete everything it remembers for your account — private notes, chat transcripts, saved library pages, and preference facts. See the [Privacy](/privacy) page for exactly what that export and purge cover, and how to run them.

### Youth mode

If your account has **Youth mode** on, CuratorX uses a distinct big-poster layout. The top bar keeps **Ask**, **Browse**, **Inbox**, and **My Journey** (plus Search and Settings). The hamburger holds secondary destinations like **My list**. Explore and Chat only show titles with a content rating at or below the owner's max — **unrated titles stay hidden**. Ask the curator stays friendly and age-aware. Try **Pick for me** on Explore for a quick surprise from safe shelves.

### Guest tour

When the owner enables **Take a Tour** (Admin household toggle, or env `CURATORX_GUEST_TOUR_ENABLED`), the login page offers a public tour at **/tour** — no hamburger chrome. Signed-in **guests** also get a tour shell. Open **What's great** for published collections your host shared, then browse or ask without destructive actions. Visitors who are not signed in yet can **Request access** on the login page — that queue is owned by CuratorX (not Seerr); the owner approves from **Admin → Access requests**.

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

### Search beyond the collection — how acquisition works

The member-facing **Search beyond your collection** action (see the member half above) is backed by an authenticated endpoint that queries TMDB, de-dupes the hits against your library and Radarr/Sonarr queue, and returns cards flagged with `in_library` / `in_radarr` / `in_sonarr` / `already_queued`. TMDB must be configured for it to work; when it isn't, the endpoint returns `503` and the UI hides the affordance behind a short note (no provider detail leaks to members).

```bash
# Search beyond the library for a movie (owner host); shows dedupe flags
curl -s "http://localhost:8788/api/search/external?q=arrival&media_type=movie&limit=5" \
  | python3 -m json.tool
# → {"query": "arrival", "returned": 5, "items": [{"title": "Arrival", "in_library": false, "already_queued": false, ...}]}
```

The add/request buttons on beyond results reuse the same **propose → confirm** acquisition flow as the rest of the app, so it's role-aware without new plumbing:

- **Owners** propose `add_radarr` (by `tmdb_id`) or `add_sonarr` (by `tvdb_id`, which shows results carry via TMDB enrichment). Requires Radarr/Sonarr configured with a valid root folder.
- **Members** propose `request_seerr` — routed to Seerr for approval. With `seerr.require_linked_user_for_requests` on, the member must have a linked Seerr account.
- **Guests** get no write path at all; the API rejects acquisition just as it does elsewhere.

Owned or already-queued titles are returned for context (so members see they exist) but never carry an add/request button. This is a read-only discovery surface: nothing is downloaded until someone with the right role confirms the proposal.

### Watched state & Plex sync

When anyone in the household uses **Mark as watched / unwatched** from a poster's ⋮ grip (or the button on a title's detail page), CuratorX does two things: it updates the title's `view_count` / `last_viewed_at` in its own index, and it pushes the change to your Plex server. The Plex write uses the Plex "scrobble" endpoint (`/:/scrobble` to mark watched, `/:/unscrobble` to clear it) against the same server URL and token the connector already uses for sync and deep links — no new Plex credential is introduced.

Which Plex identity gets the write depends on how the member signed in: if they authenticated with **Sign in with Plex**, their own account token is used so the watched flag lands on *their* Plex profile. If no per-account token is available, CuratorX falls back to the server `plex_token`, which applies watched state to the admin/account that owns that token — effectively household-wide. Guests cannot change watched state while multi-user is on.

If Plex is unreachable or not configured, the local index is still updated and the member sees an honest note (for example *"saved locally; Plex sync failed"*) rather than a silent failure.

```bash
# The scrobble call CuratorX makes on your behalf (movie ratingKey 12345)
curl -s "http://localhost:32400/:/scrobble?identifier=com.plexapp.plugins.library&key=12345&X-Plex-Token=$PLEX_TOKEN"
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

### Library-health hero & issue badge

The **Admin → Dashboard** now opens with a **library-health hero**: at-a-glance tiles for overall health, knowledge coverage, chat streak, and the count of **open issues**, each linking into the page that fixes it. The Admin rail carries the same open-issue count as a badge next to **Issues**, so you can see the queue is backing up without opening it.

The hero reuses the same aggregations the rest of the Dashboard already loads — nothing new is fetched per tile. The open-issue count comes from the existing queue:

```bash
# Owner host — the same open-issue count the badge shows
curl -s "http://localhost:8788/api/media-issues?status=open" | python3 -m json.tool
# → {"count": 3, "issues": [ ... ]}
```

### One-click grooming rerun with safe undo

Grooming is the housekeeping pass that finds **purge candidates** (stale, unwatched, or low-signal titles) so you can prune the library. From **Admin → Dashboard** you can rerun the grooming warm-up in one click (it runs the same scheduled tasks as the multi-task preset), then act on the refreshed candidates.

Deleting purge candidates is destructive, so CuratorX records every bulk delete in a **grooming action log** before it runs. Each entry snapshots the exact CuratorX index rows removed, so you can reverse the last run:

```bash
# List recent destructive grooming actions (most recent first)
curl -s http://localhost:8788/api/admin/grooming/actions | python3 -m json.tool
# → {"actions": [{"id": "…", "action_type": "purge_delete", "item_count": 12,
#                 "summary": "Deleted 12 purge candidates", "undone_at": null}]}

# Undo one — restores the snapshotted rows
curl -s -X POST http://localhost:8788/api/admin/grooming/actions/ACTION_ID/undo
```

Use the **Undo last grooming run** panel on the Dashboard for the same thing without a terminal.

**How it works / honest limits.** Undo restores the CuratorX **index rows** (the metadata, knowledge, and neighbor edges the delete removed); regenerable derived data such as embeddings is rebuilt by the normal idle tasks, so it is not snapshotted. Undo does **not** touch Plex or your files — a purge only prunes CuratorX's own index, never the media on disk. Once an action is undone it is marked `undone_at` and can't be undone twice.

### Collections & courses (publish a list to members)

Any curated list can become a members-visible **collection**, and an ordered **course** with a short note per step (e.g. a "Kurosawa 101" watch-through). Members can view what you publish; only the owner publishes. Members track course step progress under **Explore → Engagement**.

- Create or open a list under **Lists**, set its kind to **course** if you want an ordered sequence, and use the owner **Course authoring** panel to reorder items and add a per-step note.
- Toggle **Publish** to make it visible to members under **Collections**; toggle it off to make it private again.

```bash
# Publish a list to members (owner-only)
curl -s -X PATCH http://localhost:8788/api/lists/LIST_ID \
  -H 'Content-Type: application/json' -d '{"visibility": "published"}'

# Add a step note and set its order
curl -s -X PATCH http://localhost:8788/api/lists/LIST_ID/items/ITEM_ID \
  -H 'Content-Type: application/json' -d '{"note": "Start here", "position": 1}'

# What members see
curl -s http://localhost:8788/api/collections | python3 -m json.tool
```

**How it works / honest limits.** Publishing sets a list's `visibility` to `published` and stamps `published_at`; the members read path (`GET /api/collections`) only ever returns published lists. Course sequencing reuses the existing item `position`; the `note` is per-step prose. Members can read published collections but cannot publish, reorder, or edit them.

### Weekly digest — "This week in your library"

CuratorX assembles an in-app **weekly digest** — new additions, library counts, knowledge coverage, open issues, and purge-candidate pressure — as a snapshot you can read on the Dashboard. A scheduled `weekly_digest` task refreshes it once per weekly bucket; you can also **Generate now**.

Members who opt in under **Settings → Notifications** also get a personalized **weekly newsletter** (inbox + email when mail is configured). A separate **monthly collection-curation** update goes to owners on the same transport. Gap / watchlist **arrival** notifications fire when matching titles land in the library. Opt-in **enthusiast nudges** ride a weekly `enthusiast_nudge` task (same transport; requires `nudge_opt_in`). The **member weekly For-you rail** rides the same weekly cadence (`member_weekly_rail`); owners can force a rebuild:

```bash
curl -s -X POST http://localhost:8788/api/admin/weekly-rail/generate | python3 -m json.tool
```

Weekend / holiday **Seasonal picks** on Explore prefer anniversary-scanner rows when available (no calendar connector).
```bash
# Read the latest digest (owner-only)
curl -s http://localhost:8788/api/admin/weekly-digest | python3 -m json.tool

# Force a fresh snapshot for the current week
curl -s -X POST http://localhost:8788/api/admin/weekly-digest/generate
```

**How it works / honest limits.** The owner Dashboard digest remains an in-app snapshot keyed to a fixed 7-day bucket. Member newsletters and arrival alerts reuse the shared notification inbox; email only sends when **Admin → Mail** is enabled and the member has opted in.

### Mail (SMTP + Resend)

Configure outbound mail under **Admin → Mail**. Choose **SMTP** or **Resend**, set from-address / template fields (subject prefix, footer, logo URL), and use **Send test email**. Secrets are stored in `settings.json` with mode `0600`, like other API keys.

```bash
# Inspect masked mail settings (owner session cookie required)
curl -s http://localhost:8788/api/settings | python3 -c "import sys,json; print(json.load(sys.stdin).get('mail'))"

# Test send (uses your notification email if to_email is omitted)
curl -s -X POST http://localhost:8788/api/admin/mail/test \
  -H 'Content-Type: application/json' \
  -d '{"to_email":"you@example.com"}'
```

**How it works / honest limits.** One provider is active at a time (`smtp` or `resend`). Empty password / API-key fields on save keep the previously stored secret. Without mail configured, notifications still appear in the in-app inbox.

### Youth gate & guest access requests

Under **Admin → Household**, set **Youth max content rating** (default `PG-13`). Youth-mode members never see empty/`content_rating` titles or anything above that max — browse, feeds, title detail, and chat cards all fail closed.

```bash
# Inspect current youth gate (owner session cookie)
curl -s http://localhost:8788/api/settings | jq '.youth'

# List pending CuratorX access requests (not Seerr)
curl -s http://localhost:8788/api/admin/access-requests?status=pending

# Approve → creates a local member + one-time password when local login is on
curl -s -X POST http://localhost:8788/api/admin/access-requests/REQUEST_ID/approve
```

Visitors submit **Request access** on `/login` (`POST /api/access-requests`). Approvals also notify you via the inbox (`access-request` kind) and email when mail is configured. Seerr stays for post-member *media* requests only. Manage the queue in **Admin → Access requests**.

### Memory & privacy controls (owner)

Because members can't see this half, here's the exact mechanism behind the member-facing "export or delete your memory" guidance. Each signed-in account can export or purge its own data via `/api/me/memory`:

```bash
# Export everything CuratorX holds for the signed-in account (JSON)
curl -s http://localhost:8788/api/me/memory > my-curatorx-export.json

# Permanently delete the same set — private notes, chat threads + message
# transcripts, saved library pages, and preference facts. Export first.
curl -s -X DELETE http://localhost:8788/api/me/memory
```

Export and purge cover **exactly the same set**, so a copy taken before a purge is complete. Shared, sanitized repository research about media is *not* part of an account purge — it isn't tied to any one account. For **Youth-mode** accounts only, an owner may review that account's memory for moderation from the **Admin → Youth review** dashboard, which lists Youth-flagged accounts and their stored notes. The same data is available over HTTP (`GET /api/users/{id}/memory`, owner-only); adult member memory is never owner-readable, and the endpoint fails closed — it returns memory only for accounts actually flagged Youth. Full data map: [Privacy](/privacy).

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
