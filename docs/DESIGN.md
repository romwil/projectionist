# CuratorX — Design Document

Product principles, single-workspace UX, lens isolation, agent behavior, and API design for CuratorX **1.3**. Items marked **Future** are planned but not fully shipped.

---

## Product principles

1. **Intent-aware, not averaged** — Taste lives in **curation lenses**, not one global profile. Casual watches must not poison curated study lanes.

2. **Chat-first** — The curator conversation is the primary loop. Settings, sync, and title detail support the chat.

3. **One workspace** — Full-width chat with a conversation sidebar and status dock. Optional overlay expands large title-card result sets.

4. **Explain the “why”** — Every title card carries a `recommendation_reason`.

5. **Sovereign identity** — Name your curator; tune persona sliders without redeploying.

6. **Confirm before changing the fleet** — Radarr/Sonarr mutations always require explicit confirmation.

7. **Bring your own provider** — LLM and embeddings are configurable; Ollama on the homelab is first-class.

8. **Homelab pragmatism** — Single container, SQLite, no mandatory cloud beyond TMDB and your chosen LLM.

---

## Visual language

**Cinema dark** — near-black chamber surfaces, warm paper text, a single **amber/gold** accent (no blue→violet gradients). Display type (**Fraunces**) for brand and empty-state headlines; body UI (**DM Sans**). Atmosphere comes from subtle ambient washes (persona/context), not glow stacks or pill chrome.

| Token role | Intent |
|------------|--------|
| Surfaces | Layered `--bg` / `--surface` / `--surface-raised` |
| Accent | Warm gold primary CTAs and focus |
| Type | Display for brand; body for chat and forms |

---

## Single workspace layout

CuratorX serves one React application (`frontend/src/App.jsx`):

| Region | Contents |
|--------|----------|
| **Top bar** | CuratorX brand, curator name, agent pulse, library counts, Config link, optional avatar menu |
| **Sidebar** | Conversation list + New thread + **status dock** (bottom of rail) |
| **Chat column** | Thread, ambient context tag, title cards, composer |
| **Results overlay** | Optional horizontal expand for large card sets (“Cinema mode”) |

### Visual state tokens

| Token | Meaning |
|-------|---------|
| `.agent-pulse` | **Chat** agent state only: idle / thinking / error (not library sync) |
| Ambient tint | Subtle background shift from conversation context + persona accent |
| Status dock | Operational sync / add progress — lives in the **sidebar**, not the chat column |

---

## Lens isolation UX

### User mental model

A **lens** is a taste sandbox — like separate playlists for “comfort rewatch” vs “director study.” Switching lenses (API / advanced config) changes:

- Which chat messages appear in history
- Which taste weights apply (`lens_taste_profile`)
- Which telemetry bucket receives future events (**Future** full ingestion)

Ambient context inference complements lenses for everyday chat; legacy lens CRUD remains available for power users.

### Default and custom lenses

- **`general`** — seeded at install; default active lens.
- **Custom lenses** — created via `POST /api/lenses` with URL-safe `lens_id`.

### Cross-contamination firewall

Watch completions and chat signals under lens A do not update taste weights for lens B unless:

- The user explicitly bridges contexts (**Future**), or
- A cluster has `explicit_lock = 0` and shared global preference facts apply (global `preference_facts` remain cross-lens today).

### API contract

```json
POST /api/chat
{
  "message": "Find neo-noir gaps",
  "session_id": "optional-uuid",
  "lens_id": "general"
}
```

Response includes `lens_id` on the assistant message. History queries use the same filter server-side.

---

## Persona tuning UX

Configured in **Settings** (`/config`) and stored in `curator_persona_metrics`:

| Slider | Field | Low (0.0) | High (1.0) |
|--------|-------|-----------|------------|
| Vocabulary | `val_bro_prof` | Bro | Professorial |
| Tone | `val_dipl_snark` | Diplomatic | Snarky |
| Autonomy | `val_pass_auto` | Passive | Autonomous |

**Curator name** updates greetings, page title, and LLM system prompt via `build_system_prompt()` — no container restart required.

Presets (Classic Curator, Blunt Archivist, …) set welcome copy, composer hints, and accent; live sync progress in the status dock always takes priority over persona job-status flavor text.

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

### Gap finding, watch tonight, purge

Purge remains advisory; *arr remove requires confirmation. See agent catalog below.

---

## UI design system

Dark **cinematic** styling in `frontend/src/styles.css`:

- Top bar + sidebar + chat column as one composition
- Title cards with poster, reason text, and optional “Why this?”
- Status dock anchored bottom-left of the chat column

Typography and accent colors follow persona presets where configured; avoid treating persona flavor as operational status.

---

## Agent tools (1.0)

Core tools include library search, genre exploration, gap analysis, watch-tonight, purge candidates, preference recording, Radarr/Sonarr propose/confirm, reviews, and optional Plex collections (when enabled).

Keyword routing still applies when no LLM provider is configured — same heuristics as earlier releases.

---

## API surface (highlights)

| Area | Endpoints |
|------|-----------|
| Chat | `POST /api/chat`, `GET /api/chat/stream` |
| Library | `POST /api/library/sync`, `GET /api/jobs`, stats/health/purge |
| Setup | wizard, certifications, settings, service tests |
| Persona / lenses | `GET/PUT /api/persona`, `GET /api/lenses` |
| Actions | propose / confirm pending tokens |
| Optional auth | `/api/auth/*`, `/api/users/*` when multi-user enabled |

Full route tables: [WEB_UI.md](WEB_UI.md).

---

## Related documentation

- [WEB_UI.md](WEB_UI.md) — workspace layout and chat features
- [ARCHITECTURE.md](ARCHITECTURE.md) — system context
- [wiki/Home.md](wiki/Home.md) — operator wiki
- [FAQ.md](FAQ.md) — common questions
