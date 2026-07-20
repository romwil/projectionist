# CuratorX — Web UI

The CuratorX frontend is a Vite + React SPA served from the same origin as the FastAPI backend (`/` and `/api/*`).

This guide describes what you see after opening CuratorX in a browser — whether you run it with Docker on Unraid, `docker compose`, or a local dev server.

---

## First visit (self-hosted)

1. **Open the app** — In your browser, go to the host and port where CuratorX is running (for example `http://your-unraid-ip:8788` or the URL in your compose file).
2. **Setup banner** — If Plex, TMDB, or your LLM provider are not configured yet, a banner appears under the top bar: *Finish setup in Settings…* Click **Config** in the top bar to open the wizard.
3. **Top bar** — **CuratorX** (display brand), your curator name, a small **agent pulse** (chat idle / thinking / error), quiet **Plex server name · movie/show counts**, optional streak / watchlist pins chips, **Admin** (owners) / **Settings**, and an optional avatar menu when multi-user is on. **Help** and **About** live in the hamburger AppNav, footer, and user menu (not as top-bar icons).
4. **Conversation sidebar** — On the left, past chats and **New**. Collapse with `«` / `»` on smaller screens. The **watchlist panel** and **status dock** (sync jobs, confirmations) live at the bottom of this sidebar.
5. **Main chat** — Wide reading column (~80%): recommendations inbox (multi-user), messages, title cards, ambient context tag, composer with persona selector.
6. **Status dock** — In the sidebar bottom: background jobs (library sync, idle scheduler), and single-title Radarr/Sonarr confirms. Drop a title card onto the dock while dragging to queue an add — the drop hint appears only during drag.
7. **Footer** — Subtle **Privacy** and **About** links on all layouts.

There is **one workspace layout**. Visual language is **cinema dark** (near-black surfaces, amber accent, Fraunces + DM Sans). The old Turnstyle compact view and Immersive split view are removed.

---

## Layout overview

```
┌─────────────────────────────────────────────────────────────┐
│ CuratorX   curator · Server · 142 movies · 38 shows  Settings│  ← top bar
├──────────────┬──────────────────────────────────────────────┤
│ Conversations│  chat + title cards                          │
│  [ New ]     │                                              │
│  • Thread 1  │                                              │
│  • Thread 2  │                                              │
│──────────────│  [ persona ▾ ] [ composer ]        [ Send ]  │
│ watchlist    │                                              │
│ status dock  │                                              │
└──────────────┴──────────────────────────────────────────────┘
         Privacy · About  ← footer
```

| Area | What it does |
|------|----------------|
| **Top bar** | Brand-first CuratorX + curator name, chat pulse, Plex server + library counts, pins / streak chips, Admin / Settings, optional UserMenu |
| **Sidebar** | Thread list + watchlist panel + pinned status dock |
| **Chat workspace** | Wide thread, scroll region, composer with PersonaSelector |
| **Status dock** | Running jobs, add progress, drag-to-queue (sidebar bottom) |
| **Results overlay** | Optional expand for large title-card sets |
| **Footer** | Privacy and About |

**Sync library** lives on the **Config** / **Settings** page (not the main chat sidebar). After onboarding, Settings shows a **Library sync** section with movie/show counts, last sync time, and live progress while a sync runs.

### Single workspace (default)

With `features.multi_user_enabled` left at `false` (the default), CuratorX runs as one household workspace: no login screen, one implicit **owner** account in the database, and all chat threads share the same taste profile. Multi-user login and per-member Seerr requests appear only after you opt in via feature flags.

---

## Routes

| Route | Purpose |
|-------|---------|
| `/` | Curator chat — single workspace |
| `/config` | First-run setup wizard or Settings |
| `/settings/*` | Profile (font size), lists, preferences |
| `/admin/*` | Owner Admin shell (users, dashboard, advanced) |
| `/admin/dashboard` | Owner library intelligence dashboard (includes Knowledge coverage panel) |
| `/title/{movie\|show}/{id}` | Title detail — backdrop hero, Plot knowledge panel, trailer modal, Watch on Plex, purge notes |
| `/privacy` | Privacy disclosure (no login) |
| `/about` | About / version |
| `/help` | Help guide — Chat, Explore, Plot Lab, owner idle curation (no login; role-aware sections) |
| `/explore` | Explore hub — feed rails + compact knowledge-coverage honesty strip |
| `/explore/plot-lab` | Plot Lab — multi-signal / motifs-only walls, theme chips when present, Why? layers, surprising neighbors |
| `/lists` and `/lists/{id}` | Local curated lists and playlists; a list is a reusable shelf, while a playlist signals a planned viewing sequence |
| `/admin/issues` | Owner-only media-issue queue with review status and logged supported repairs |
| `/admin/tasks` | Owner Scheduled Tasks (coverage strip, cadence, batch, measured rate, run history, ETA) |
| `/login` | Multi-user login (configured auth methods) |

Session ID persists in `localStorage` for chat continuity across reloads.

### Configuration page auto-certification

On `/config` load, the UI fetches certification status and sequentially tests any **uncertified** service that has credentials configured (including env-backed secrets). Results appear inline per service card; successful tests set `certified` in SQLite so repeat visits skip re-testing until credentials change.

---

## Chat features

- **Intelligent scroll** — New messages anchor into view; a typing indicator shows while the curator responds (persona name, e.g. *Flemming is thinking*). If you scroll up while a reply arrives, a **New reply ↓** chip appears — click it to jump back to the latest message.
- **Empty-thread welcome** — New conversations show a persona greeting and three starter prompt chips you can click to send your first message.
- **Slash commands** — Type commands in the composer (no LLM call for `/help`):
  - `/help` — list available commands
  - `/stats` — library movie/show counts and last sync time
  - `/sync` — queue a Plex library index job (blocked in chat when multi-user mode is on; use Config instead)
  - `/rate <title>` — open an inline 1–5 star review for a library title (e.g. `/rate Inception`)
  - `/purge` — summarize top drive-space purge candidates (large, unwatched, low-taste)
  - `/collections` — list Plex movie and TV collections (only when **Allow curator to manage Plex collections** is enabled in Config)
- **Easter eggs** — Konami code in the composer (↑↑↓↓←→←→BA) or type your curator's name **backwards** for a one-time hidden reply. Drag a **movie** title card onto the status dock to queue it in **Radarr**, or drag a **show** card to queue in **Sonarr**, when the respective *arr service is connected.
- **Keyboard shortcuts** — Press `?` anywhere outside a text field for the cheat sheet:
  - `/` — focus composer
  - `Cmd/Ctrl+N` — new conversation
  - `Esc` — close results overlay
- **Ambient tint** — The workspace background subtly shifts based on inferred conversation context (e.g. neo-noir, 1970s).
- **Watchlist shelf** — Pin titles from any title card with the ☆ button. Pinned count appears in the top bar (click toggles the panel); open the list from the sidebar. Refresh pull-syncs from Plex Discover when configured. Click a pin to open title detail.
- **Title detail** — Click poster/title on a card to open detail with optional YouTube trailer modal and **Watch on Plex** when in-library.
- **Recommend** — When multi-user is on, send a title to household peers; unread items appear in a home inbox.
- **Persona selector** — Switch persona per conversation from the composer; create custom personas with seven sliders.
- **Font size** — Settings → Profile: small / medium / large.
- **Card hover backdrop** — Hover a title card to see a blurred backdrop image when art is available.
- **Cinema mode** — In the results overlay, toggle **Cinema mode** to enlarge cards and dim surrounding chrome.
- **TV progress rings** — Show cards display a small ring for watched vs total episodes when that data is available.
- **Watch overlays** — Every poster (Explore rails, Plot Lab, Watchlist, Person, section pages, chat TitleCard, QuickPick, title-detail related rails) shows a Plex-like upper-right checkmark when fully watched, or a distinct in-progress badge for movie playhead progress / partially watched shows.
- **Revisit These** — Explore hub rail of up to 20 partially watched shows idle for 60+ days (random sample; honest empty when none qualify).
- **Explore discovery rotation** — The hub rotates one director filmography (minimum three owned titles) and one genre (minimum four) per day using a deterministic date seed, so a reload does not shuffle the shelves. A third rail uses the small, editable server calendar for holidays and observances (including movable Arbor Day); within seven days it matches title, genre, keyword, and plot text to that occasion. Otherwise it uses a restrained season-of-the-year match. Rails hide when their metadata has no useful matches; director and genre headings deep-link to their existing Explore facet walls.
- **Library Pulse placement** — Library Pulse is deliberately after the discovery rails. It preserves the same health and collection stats, while letting title-led browsing set the first impression of Explore.
- **Curator streaks** — After three or more conversations in the last 30 days, a subtle streak chip appears in the top bar.
- **Sync completion chime** — When a library sync job finishes, a short chime plays (toggle mute with the bell in the status dock).
- **Late-night mode** — After 11 p.m. local time, the top bar shifts to a softer night-owl palette.
- **Persona typing copy** — The typing indicator uses flavor text from your active persona preset.
- **Persona welcome & composer** — Empty threads greet you with your curator's preset voice and starter chips; the composer placeholder rotates every few seconds with preset-specific suggestions.
- **Persona tint** — The workspace background subtly blends your persona accent with conversation context (neo-noir, horror, etc.).

### Persona presets (for novices)

CuratorX ships five **persona presets** — ready-made curator personalities. Switch them **per conversation** from the composer PersonaSelector, or manage defaults under **Admin → Persona**. Each preset sets tone sliders (seven dimensions), greeting copy, composer hints, review prompts, and a subtle UI accent. You can still rename your curator and fine-tune sliders afterward.

| Preset | Vibe | Good if you want… |
|--------|------|-------------------|
| **Classic Curator** | Warm film buff | Canon picks, double features, friendly deep cuts |
| **Blunt Archivist** | Direct & data-driven | Gap analysis, purge advice, no fluff |
| **Enthusiastic Scout** | Hype, but grounded | Excited recommendations that still match your taste |
| **Academic Critic** | Analytical | Movements, craft, critical lineage |
| **Night Owl Host** | Casual, tonight-focused | Short lists and finishable late-night picks |

What changes when you switch presets:

- **Welcome panel** — Greeting and starter chips on new conversations
- **Typing indicator** — e.g. *Flemming is indexing your chaos…*
- **Composer placeholder** — Rotating prompt ideas in the message box
- **Review cards** — Persona-voiced near-completion rating prompts
- **Ambient tint** — Background color blends preset accent with chat context
- **Agent behavior** — System prompt and tool use (including review memory via `get_user_reviews`)

Presets hot-reload: change persona in Config and return to chat — no server restart needed.
- Inline **title cards** — poster, rating, genres, `recommendation_reason`, and **Why this?** to expand facet-match detail when the query engine provided it
- **Confirm all** — bulk Radarr/Sonarr adds via in-chat buttons (not a center modal)
- **Results overlay** — horizontal scroll overlay for expanded result sets (`Expand N titles…`); title cards support the same drag-to-dock behavior as inline chat cards
- **Add to Radarr/Sonarr** — confirm in the status dock; server confirmation token required. Drag a movie or show card onto the dock to start the same confirm flow without clicking **Add to Radarr/Sonarr**
- **Remove from Radarr/Sonarr** — purge/removal proposals use the same status-dock confirm flow with removal-specific copy (not “proposed adds”). Confirm executes the matching pending action type.
- **Not interested** — `POST /api/preferences` with `dismiss` signal
- **Ambient context** — inferred from conversation; shown as a tag under the thread title
- **Message reactions** — thumbs up / thumbs down under each curator reply; your choice helps train future recommendations (stored per conversation)

### Helpful / not helpful reactions

After the curator answers, you may see **👍** and **👎** under that reply.

- **👍 Helpful** — the suggestion or explanation matched what you wanted.
- **👎 Not helpful** — the reply missed the mark.

Tap the same button again to clear your choice for that message. Reactions are saved per conversation and help CuratorX learn your taste over time. They appear only on curator (assistant) messages, not on your own prompts.

### Personal title reviews

CuratorX keeps a **personal review log** for titles you have watched — separate from helpful/not-helpful reactions on curator replies.

- After a **library sync** or **Plex webhook** (playback stop/scrobble), near-complete watches (≥85% through a movie or episode) may appear as an inline **rating card** at the bottom of the chat.
- Cards use your **persona preset** opener (`review_prompt_templates`) — warm film-buff, blunt archivist, etc.
- Use **1–5 stars**, optional short notes, then **Save review** or **Skip**. Skipping sets a 30-day cooldown before that title is prompted again.
- Type **`/rate Title Name`** any time to rate a library title on demand.
- The curator can run a **multi-turn review dialogue** via the `start_review_dialogue` agent tool — one persona-voiced question per turn before saving.
- Title cards show **your stars** (gold badge on the poster and “Your rating” in the card body) when you have already reviewed that title.

When a rating card appears in chat, CuratorX records `prompted_at` on the queue row (so the system knows you were shown the prompt, even if you skip without saving).

Reviews are stored in SQLite (`user_title_reviews`) and feed taste training via preference signals.

**Optional Plex sync:** In Configuration → Plex library mapping, enable **Sync personal reviews to Plex star ratings**. When on, each saved review pushes your stars to Plex (1★→2, 2★→4, … 5★→10 on Plex’s 0–10 scale). Your review is always saved locally even if Plex is unreachable.

**Plex rating conflicts:** If Plex already has a different star rating when you save (from a rating card, `/rate`, or the curator's `save_user_review` tool), an inline **keep / replace** banner appears in chat: **Keep Plex rating** leaves Plex unchanged; **Replace on Plex** overwrites Plex with your CuratorX stars. The same banner appears on proactive rating cards when the REST API returns a 409 conflict.

The curator can also propose **Plex collection** create/add actions; those require confirmation like Radarr/Sonarr adds.

---

## API highlights

### Core

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/chat` | Send message; optional `lens_id` in body |
| GET | `/api/chat/stream` | SSE stream; query `message`, `session_id`, `lens_id` |
| POST | `/api/library/sync` | Start Plex index job |
| GET | `/api/library/stats` | Item counts and last sync |
| GET | `/api/library/health` | Unwatched %, stale adds, rating coverage |
| GET | `/api/library/purge-candidates` | Purge candidate title cards for `/purge` |
| GET | `/api/admin/export/training-corpus` | Owner-only JSON export of taste-training tables |
| GET | `/api/title/{media_type}/{id}` | Title detail (`id_type` query) |
| GET | `/api/context/active` | Inferred ambient context label |

### Setup and wizard

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/setup/status` | High-level readiness flags |
| GET | `/api/setup/wizard` | Gated wizard step progress (includes `certifications`) |
| GET | `/api/setup/certifications` | Per-service `certified` / `connection_status` / `last_tested_at` |
| GET | `/api/setup/llm-providers` | Default base URLs per provider |
| POST | `/api/setup/test/{service}` | Live connection test (`plex`, `radarr`, `sonarr`, `tmdb`, `fanart`, `tautulli`, `llm`) |
| GET/PUT | `/api/settings` | Connection settings (secrets masked on read) |

### Persona and lenses (backend)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/lenses` | List curation lenses (API only; no UI switcher) |
| GET/PUT | `/api/persona` | Curator name and tone sliders (advanced config) |
| GET/PUT | `/api/system-config` | Key-value config (includes `curator_name`) |

### Actions

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/actions/propose` | Create confirmation token |
| POST | `/api/actions/confirm` | Execute or cancel pending action |
| POST | `/api/preferences` | Record taste signal |
| POST | `/api/chat/messages/{id}/feedback` | Mark assistant reply helpful or not helpful; send `"feedback": null` to clear |
| DELETE | `/api/chat/messages/{id}/feedback?session_id=…` | Clear helpful/not-helpful reaction for a message |
| GET | `/api/chat/threads/{id}/feedback` | List feedback for a thread |
| GET | `/api/reviews` | List personal title reviews (filter by `rating_key`, `tmdb_id`, `title`, `min_stars`) |
| POST | `/api/reviews` | Save or update a 1–5 star review |
| GET | `/api/reviews/prompts` | Pending near-completion rating prompts (sets `prompted_at` when surfaced) |
| POST | `/api/reviews/prompts/{id}/dismiss` | Skip a proactive rating prompt |
| POST | `/api/webhooks/plex` | Plex play/stop/scrobble ingest for near-completion prompts |
| GET | `/api/plex/collections` | List Plex collections (`media_type=movie\|show`; owner only) |
| POST | `/api/plex/collections/propose` | Propose creating a Plex collection (returns confirmation token; owner only) |
| POST | `/api/plex/collections/{key}/items/propose` | Propose adding titles to a collection (owner only) |
| GET | `/api/features` | Feature flags (multi-user, Seerr, auth modes) |
| GET | `/api/auth/me` | Current user when multi-user auth is enabled |
| POST | `/api/auth/plex/pin` | Start Plex PIN / link login |
| GET | `/api/auth/plex/pin/{id}` | Poll PIN; sets HttpOnly session cookie when authorized |
| POST | `/api/auth/plex` | Advanced token login (sets HttpOnly session cookie) |
| POST | `/api/auth/logout` | Sign out |
| GET | `/api/users` | Household user list (owner only) |
| PATCH | `/api/users/{id}` | Update user role (owner only) |
| GET | `/api/watchlist` | List pinned watchlist titles |
| POST | `/api/watchlist` | Pin a title (`tmdb_id` or `tvdb_id`, `media_type`, `title`) |
| DELETE | `/api/watchlist/{id}` | Remove a watchlist pin |
| GET | `/api/engagement/streak` | Conversation count in last 30 days |
| GET | `/api/persona/typing-phrases` | Persona-flavored typing indicator phrases |
| GET | `/api/persona/ui-copy` | Persona UI strings (welcome, composer placeholders, review templates, accent) |

---

## Login flow (optional multi-user)

When `features.multi_user_enabled` is `true` in settings:

1. The app loads `GET /api/features` and `GET /api/auth/me`.
2. If features show multi-user mode and `/api/auth/me` returns **401**, the browser redirects to **`/login`**. API middleware also requires a session for almost all `/api/*` (see [SECURITY.md](SECURITY.md)).
3. Sign in with a configured method (**Plex PIN**, **local password**, and/or **OIDC**). For Plex, CuratorX starts an Overseerr-style plex.tv PIN flow. Approve in the Plex window; CuratorX polls until authorized and stores a signed **HttpOnly** session cookie. Token paste is an advanced fallback only.
4. After login, the main chat UI loads. The top bar shows an avatar menu with display name, role, **Help**, and **Sign out**. Help / Privacy / About remain in the footer.
5. **Owners** manage household users and the dashboard under **Admin**. **Members** use **Settings** for personal prefs (including font size); Seerr request buttons appear instead of Radarr/Sonarr adds when Seerr is enabled.

When multi-user is **off** (default), there is no login screen and the bootstrap owner is used implicitly.

---

## Security

Single-owner installs have no built-in authentication — run on a trusted LAN or behind an authenticated reverse proxy. When multi-user is enabled, Plex PIN login and signed session cookies gate the SPA **and** most `/api/*` routes (see [SECURITY.md](SECURITY.md)). Always set `CURATORX_SESSION_SECRET` to a long random string (never leave the public dev default). Destructive *arr operations use confirmation tokens (10-minute TTL) scoped to the acting user.

---

## Browse controls, collections, and media issue queue

Library-oriented walls share **MediaBrowseControls**: sort and direction, type/watch/year filtering where data supports it, a poster/list pivot, column preference, and a CSV action. The controls are intentionally a *query interface*: their state is sent as normal library query parameters including `sort_dir`, and the browser may export only the server allowlist (title, year, type, genres, runtime, rating, watch state, counts/dates, and public IDs). This makes an exported slice match the visible filtered library rather than leaking filesystem paths or operational secrets.

The **⋮ poster action grip** appears on LibraryMediaCard posters, list rows, and compact TitleCard overlays. It centralizes detail, Plex playback, watchlist pinning, list/playlist membership, discovery, reporting, and owner-only tools. A repeated control location matters for keyboard and touch users, and prevents each wall from inventing a subtly different action model.

`/lists` uses one local collection model with `list_kind`:

| Kind | Use it for | Not the same as |
|------|------------|-----------------|
| **List** | A lasting shelf, research set, or shareable theme | Plex Discover watchlist |
| **Playlist** | A deliberate watch sequence | Plex Playlist synchronization (not implemented) |
| **Watchlist** | Personal “remember this” pins, optionally Plex Discover synced | A curated shelf or program |

Anyone may send a typed **Report issue** from the grip. Reports go to `/api/media-issues`; members cannot call *arr repair routes. Owners review `/admin/issues`, update the status, and may use `/repair` only for supported, logged playbooks. A repair can safely skip when the item is not managed, has ambiguous identity, or the connector lacks the required operation. It never blindly deletes a file or treats a report as authority to control *arr.

---

## Help & knowledge

| Surface | Audience | Content |
|---------|----------|---------|
| `/help` ([HELP.md](HELP.md)) | Everyone; owner sections when `isOwner` | Chat, Explore, Plot Lab, Plot knowledge, sparse-wall explanation; owners get scheduler / coverage / LLM-vs-free guidance |
| [CURATOR_KNOWLEDGE.md](CURATOR_KNOWLEDGE.md) | Operators + curious users | Full why/what/how of knowledge dimensions, idle trickle, product surfaces for coverage / Plot Lab / title detail |
| Admin → Dashboard | Owners | Knowledge coverage panel (% overview / motifs / keywords / neighbors / loglines) |
| Admin → Scheduled Tasks | Owners | Coverage strip + cadence, measured rate, ETA; deep-linked from Help and cold Explore empty states |
| Explore hub | Everyone | Compact knowledge-coverage honesty strip |

Jump links on Help highlight **Owners**, Coverage, Dashboard, and Scheduled Tasks for owners; members/guests see browse/chat guidance and are pointed at the server owner for sync.

---

## Related documentation

- [HELP.md](HELP.md) — in-app Help source
- [CURATOR_KNOWLEDGE.md](CURATOR_KNOWLEDGE.md) — library knowledge depth
- [SECURITY.md](SECURITY.md) — threat model and living findings (S1–S13)
- [DESIGN.md](DESIGN.md) — block schema, interaction patterns
- [ARCHITECTURE.md](ARCHITECTURE.md) — chat and sync data flows
