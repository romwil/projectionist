# CuratorX — Design Document

Product principles, single-workspace UX, lens isolation, agent behavior, and API design for CuratorX **1.7**. Items marked **Future** are planned but not fully shipped.

---

## Product principles

1. **Intent-aware, not averaged** — Taste lives in **curation lenses**, not one global profile. Casual watches must not poison curated study lanes.

2. **Chat-first** — The curator conversation is the primary loop. Settings, sync, title detail, and the owner dashboard support the chat.

3. **One workspace** — Full-width chat (~80% reading column) with a conversation sidebar and status dock. Optional overlay expands large title-card result sets.

4. **Explain the “why”** — Every title card carries a `recommendation_reason`.

5. **Sovereign identity** — Name your curator; tune persona sliders and switch personas per conversation without redeploying.

6. **Confirm before changing the fleet** — Radarr/Sonarr/Seerr mutations always require explicit confirmation.

7. **Bring your own provider** — LLM and embeddings are configurable; Ollama on the homelab is first-class.

8. **Homelab pragmatism** — Single container (non-root), SQLite, no mandatory cloud beyond TMDB and your chosen LLM.

---

## Visual language

**Cinema dark** — near-black chamber surfaces, warm paper text, a single **amber/gold** accent (no blue→violet gradients). Display type (**Fraunces**) for brand and empty-state headlines; body UI (**DM Sans**). Atmosphere comes from subtle ambient washes (persona/context), not glow stacks or pill chrome.

| Token role | Intent |
|------------|--------|
| Surfaces | Layered `--bg` / `--surface` / `--surface-raised` |
| Accent | Warm gold primary CTAs and focus |
| Type | Display for brand; body for chat and forms |
| Text size | Per-user preference (`small` / `medium` / `large`) via `--base-font-size` |

---

## Single workspace layout

CuratorX serves one React application (`frontend/src/App.jsx`):

| Region | Contents |
|--------|----------|
| **Top bar** | CuratorX brand, curator name, agent pulse; **Plex server name** + movie/show counts; optional streak chip; **watchlist pins** chip (click toggles panel); **Admin** (owners) / **Settings**; optional **UserMenu** when multi-user is on. No About link in the top bar. |
| **Sidebar** | Conversation list + New thread + **Watchlist panel** + **status dock** (bottom of rail) |
| **Chat column** | Recommendations inbox (multi-user), welcome / On This Day / Library Glance / Quick Pick, thread with ambient context tag (⧉), title cards, composer with **PersonaSelector** + Surprise Me |
| **Results overlay** | Optional horizontal expand for large card sets (“Cinema mode”) |
| **Footer** | Subtle **Privacy** and **About** links on all layouts (chat, Admin, Settings) |

### Visual state tokens

| Token | Meaning |
|-------|---------|
| `.agent-pulse` | **Chat** agent state only: idle / thinking / error (not library sync) |
| Ambient tint | Subtle background shift from **per-thread** conversation context + persona accent |
| Status dock | Operational sync / add progress — lives in the **sidebar**, not the chat column |
| Context label | Inferred topic (`context_label`) stored per thread; updates when switching conversations |

---

## Title cards & title detail

Inline and turnstyle cards share the same affordances:

| Action | Behavior |
|--------|----------|
| **Click title / poster** | Navigate to `/title/{movie\|show}/{id}` — backdrop hero, metadata, purge notes |
| **Watch trailer** | On detail, opens a YouTube trailer modal when `trailer_youtube_key` is present |
| **Watch on Plex** | Shown when the title is in-library (`rating_key`); opens Plex deep link |
| **Recommend** | Multi-user: pick household peers + optional note; unread inbox on home |
| **Pin (☆)** | Add/remove local watchlist pin |
| **Why this?** | Expand `recommendation_reason` / facet matches |
| **Add / Request** | Radarr, Sonarr, or Seerr via confirmation flow |
| **Not interested** | Preference dismiss signal |

Runtime under 100 minutes gets emphasis on the card. Show cards may display a TV progress ring.

---

## Watchlist

- Pins live in the sidebar panel and as a top-bar count chip (click toggles the panel).
- Refresh **pull-syncs from Plex Discover** when a Sign-in-with-Plex account token is available, then lists local pins.
- Watchlist rows **click through to title detail**.
- Agent tools: `query_watchlist`, `add_to_watchlist`, `remove_from_watchlist`, `curate_watchlist`, `critique_watchlist`.

---

## Owner dashboard

Owners open **Admin → Dashboard** (`/admin/dashboard`) for library intelligence (pure SVG/CSS charts — no charting library):

| Panel | Contents |
|-------|----------|
| **Composition** | Decade, top genres, movies vs shows, countries, languages, runtime distribution |
| **Health & engagement** | Unwatched %, stale adds, **rating coverage** (watched titles with reviews), curator streak, **TV completion** (top 10 shows with episode counts) |
| **Storage** | Purge candidates table — multi-select checkboxes, **Delete Selected** / **Dismiss Selected** with confirmation |
| **Taste profile** | Recent reviews / preference signals with stars on a **/5** scale |

Background **idle scheduler** tasks pre-warm health metrics, taste refresh, embeddings, anniversaries, and recommendation caches so the dashboard and chat stay responsive. See [ARCHITECTURE.md](ARCHITECTURE.md#agent-tools-vs-background-scheduler).

---

## Multi-user recommendations

When `features.multi_user_enabled` is on:

1. Any title card can **Recommend** to household peers (`RecommendModal`).
2. Recipients see an unread **RecommendationsInbox** at the top of chat home.
3. Dismiss one or dismiss-all clears the inbox items.

Local curated lists (Settings → Lists) remain separate from peer recommendations.

---

## Lens isolation UX

### User mental model

A **lens** is a taste sandbox — like separate playlists for “comfort rewatch” vs “director study.” Switching lenses (API / advanced config) changes:

- Which chat messages appear in history
- Which taste weights apply (`lens_taste_profile`)
- Which telemetry bucket receives future events (ingestion is live; cross-lens sharing remains limited)

Ambient context inference complements lenses for everyday chat; legacy lens CRUD remains available for power users.

### Default and custom lenses

- **`general`** — seeded at install; default active lens.
- **Custom lenses** — created via `POST /api/lenses` with URL-safe `lens_id`.

### Cross-contamination firewall

Watch completions and chat signals under lens A do not update taste weights for lens B unless:

- The user explicitly shares a preference across lenses (**Future**), or
- A lens has `explicit_lock = 0` and shared global preference facts apply (global `preference_facts` remain cross-lens today).

### API contract

```json
POST /api/chat
{
  "message": "Find neo-noir gaps",
  "session_id": "optional-uuid",
  "lens_id": "general",
  "persona_id": "optional-persona-template-id"
}
```

Response includes `lens_id` on the assistant message. History queries use the same filter server-side. SSE streaming (`GET /api/chat/stream`) emits `token`, `tool_call`, `done`, and `error` events for incremental UI updates.

---

## Persona tuning UX

### Conversation-level personas (1.5+)

The composer **PersonaSelector** switches persona per thread: five built-in presets (Classic Curator, Blunt Archivist, Enthusiastic Scout, Academic Critic, Night Owl Host), plus owner-shared and user-private custom personas. Threads show the active persona in the sidebar; “set as default” applies to new conversations.

### Seven personality sliders

Configured in **Admin → Persona** / persona create-edit modal and stored on persona templates:

| Slider | Field | Low (0.0) | High (1.0) |
|--------|-------|-----------|------------|
| Vocabulary | `val_bro_prof` | Casual | Professorial |
| Tone | `val_dipl_snark` | Diplomatic | Snarky |
| Autonomy | `val_pass_auto` | Passive | Autonomous |
| Depth | `val_depth` | Quick picks | Deep dives |
| Obscurity | `val_obscurity` | Mainstream | Niche |
| Verbosity | `val_verbosity` | Concise | Detailed |
| Formality | `val_formality` | Chatty | Structured |

**Curator name** updates greetings, page title, and LLM system prompt via `build_system_prompt()` — no container restart required.

Presets set welcome copy, composer hints, accent, and review prompt voice; live sync progress in the status dock always takes priority over persona job-status flavor text.

---

## Profile & preferences

Under **Settings → Profile** (when signed in):

- Display name / household identity (multi-user)
- **UI font size** — `small` / `medium` / `large` (persisted as `ui_font_size`, applied via CSS variable)

---

## Delight features (chat home)

Shipped alongside the idle scheduler (1.6+):

| Feature | UX |
|---------|-----|
| **On This Day** | Anniversary prompts above the welcome panel |
| **Library at a Glance** | One-time post-sync summary (genres, decade range, hidden gems) |
| **Night Owl** | After evening hours, softer top-bar palette + runtime-aware tonight picks |
| **Double Feature** | Agent tool + `DoubleFeatureCard` pairing UI |
| **Surprise Me** | Dice button → `QuickPickCard` reveal |
| **Streaks** | Top-bar chip after 3+ conversations in 30 days |

---

## User journeys

### Onboarding

```mermaid
flowchart TD
    Start[Open :8788] --> Config[/config]
    Config --> Identity[Name curator]
    Config --> Infra[Verify Plex *arr LLM]
    Config --> Map[Map movie/TV libraries]
    Map --> Chat[Chat /]
    Chat --> Sync[Sync library]
    Sync --> Ready[Curate]
```

### Genre exploration

1. User chats in the workspace (ambient context or active `lens_id`).
2. Sends: "Explore neo-noir based on what I love."
3. Agent calls `explore_genre` / `search_library` with preference context.
4. Cards appear inline; user may expand the results overlay for large sets.
5. Dismissals record preference signals; adds go through confirmation flow.
6. Click a card for detail / trailer / Watch on Plex; optionally recommend to household peers.

### Gap finding, watch tonight, purge

Purge remains advisory in chat; *arr remove requires confirmation. Owners can also multi-select purge candidates on the dashboard. See agent catalog below.

---

## UI design system

Dark **cinematic** styling in `frontend/src/styles.css`:

- Top bar + sidebar + chat column as one composition
- Title cards with poster, reason text, optional “Why this?”, and library / Plex / recommend actions
- Status dock anchored at the **bottom of the conversation sidebar**
- User chat bubbles use a warm-tinted background for readability
- Footer Privacy / About — never compete with brand in the top bar

Typography and accent colors follow persona presets where configured; avoid treating persona flavor as operational status.

---

## Agent tools (1.7)

Core tools include library search and facet query, genre exploration, gap analysis, hidden gems, watch-tonight / tonight picks, purge candidates, preference recording, Radarr/Sonarr/Seerr propose/confirm, reviews and review dialogue, watchlist and local lists, Plex collections (when enabled), anniversaries, library snapshot, double feature, and quick-pick roulette.

Keyword routing still applies when no LLM provider is configured — same heuristics as earlier releases.

Agent tools are **synchronous and user-triggered**; long batch work (embeddings, taste refresh, health metrics, anniversary scan, recommendation warmup, data retention) belongs to the **background idle scheduler** with circuit-breaker quarantine. Boundary rules: [ARCHITECTURE.md](ARCHITECTURE.md#agent-tools-vs-background-scheduler).

---

## API surface (highlights)

| Area | Endpoints |
|------|-----------|
| Chat | `POST /api/chat`, `GET /api/chat/stream` (SSE tokens) |
| Library | sync, stats, health, purge, aggregates, quick-pick, anniversaries, overview |
| Title | `GET /api/title/{media_type}/{id}` |
| Setup | wizard, certifications, settings, service tests |
| Persona | legacy `GET/PUT /api/persona`; templates CRUD + per-thread `persona_id` |
| Lenses / context | `GET /api/lenses`, `GET /api/context/active` |
| Watchlist | list / pin / remove + Plex pull sync |
| Recommendations | create / list / dismiss (multi-user) |
| Actions | propose / confirm pending tokens |
| Auth | Plex PIN, local password, OIDC — `/api/auth/*`; `GET /api/features` returns `auth_methods` |
| Admin | dashboard data, scheduled tasks (+ quarantine reset), telemetry, training export |
| Optional household | `/api/users/*` when multi-user enabled |

Full route tables: [WEB_UI.md](WEB_UI.md).

---

## Related documentation

- [WEB_UI.md](WEB_UI.md) — workspace layout and chat features
- [ARCHITECTURE.md](ARCHITECTURE.md) — system context, scheduler boundary, SQLite concurrency
- [wiki/Home.md](wiki/Home.md) — operator wiki
- [FAQ.md](FAQ.md) — common questions
- [TESTING.md](../TESTING.md) — value-based testing pattern
- [docs/TESTING.md](TESTING.md) — Playwright / CA release checklist
