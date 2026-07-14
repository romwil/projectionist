# CuratorX — Platform Architecture

CuratorX is an **intent-aware curation companion** for Plex libraries. It combines a single-workspace chat UI, a tool-using LLM agent, RAG over your indexed library, **curation lens isolation**, **dynamic persona tuning**, personal **reviews** with optional Plex rating sync, **Plex webhooks** for near-completion rating prompts, and confirmation-gated Radarr/Sonarr actions.

It is a **separate product** from [Reclaimspace](https://github.com/romwil/reclaimspace): Reclaimspace reclaims disk space by quarantining duplicate Plex files; CuratorX helps you discover, add, watch, and purge titles based on taste and usage within explicit cognitive boundaries.

---

## Vision and goals

| Goal | How CuratorX addresses it |
|------|---------------------------|
| **Intent-aware curation** | Lenses sandbox taste; persona sliders shape agent behavior |
| **Anti-monolith taste** | `lens_id` on chat, telemetry, and taste profiles prevents context contamination |
| **Chat-first interaction** | Single chat workspace with welcome panel, watchlist, and status dock |
| **Informed recommendations** | RAG embeddings + TMDB discovery grounded in library ownership |
| **Safe automation** | Radarr/Sonarr writes require explicit confirmation tokens |
| **Self-hosted, BYOP LLM** | OpenAI-compatible, Anthropic, or Ollama |
| **Homelab friendly** | Single Docker container, SQLite, Unraid template |

Non-goals: cloud SaaS, automatic file deletion without confirmation, generic streaming-service recommendations, OIDC/local password auth. Multi-user auth (**Sign in with Plex** PIN), Seerr, and Plex collections are **optional** (off by default); see [CONFIGURATION.md](CONFIGURATION.md#feature-flags-optional-off-by-default).

---

## Cognitive architecture

```mermaid
flowchart TB
    subgraph lenses [Curation lenses]
        General[general]
        Custom[custom lenses]
    end

    subgraph isolation [Lens isolation engine]
        ChatScope[Chat history filter]
        TasteWall[lens_taste_profile]
        TelemetryFW[Cross-contamination firewall]
    end

    subgraph persona [Persona layer]
        Name[curator_name]
        Sliders[bro_prof dipl_snark pass_auto]
        Prompt[Hot-reload system prompt]
    end

    General --> ChatScope
    Custom --> ChatScope
    ChatScope --> TasteWall
    TasteWall --> TelemetryFW
    Name --> Prompt
    Sliders --> Prompt
    Prompt --> Agent[CuratorAgent]
```

- **Default lens:** `general` — seeded at database init.
- **Active lens:** stored in `curator_system_config.active_lens_id`.
- **Chat isolation:** `chat_messages.lens_id` filters history per lens within a session.
- **Explicit lock:** `lens_taste_profile.explicit_lock` blocks automatic telemetry drift on protected clusters.

See [curatorx_prd.md](curatorx_prd.md) for the full product spec.

---

## System context

```mermaid
flowchart TB
    subgraph userLayer [User]
        User[Home user / curator]
    end

    subgraph curatorx [CuratorX]
        UI[Vite React SPA]
        Chat[Chat workspace]
        API[FastAPI backend]
        Agent[Curator agent + tools]
        Reviews[Reviews + Plex sync]
        Webhooks[Plex webhooks]
        Jobs[Job manager + sync scheduler]
        DB[(SQLite curatorx.db)]
        Settings[settings.json]
    end

    subgraph external [External services]
        Plex[Plex Media Server]
        TMDB[TMDB API]
        Fanart[Fanart.tv]
        Tautulli[Tautulli optional]
        Radarr[Radarr]
        Sonarr[Sonarr]
        LLM[BYOP LLM provider]
        Embed[Embedding API optional]
    end

    User --> Chat
    Chat --> UI
    UI --> API
    API --> Agent
    API --> Reviews
    Webhooks --> API
    API --> Jobs
    Agent --> DB
    Agent --> LLM
    Jobs --> DB
    API --> Settings
    Jobs --> Plex
    Jobs --> TMDB
    Jobs --> Fanart
    Jobs --> Radarr
    Jobs --> Sonarr
    Agent --> TMDB
    Agent --> Radarr
    Agent --> Sonarr
    Jobs --> Embed
    Agent --> Embed
    Jobs --> Tautulli
```

The application runs as a **single process** (Uvicorn + FastAPI). The React frontend builds to static assets served from the same origin. Persistent state lives under `DATA_DIR` (default `/config` in Docker).

---

## Component architecture

```mermaid
flowchart LR
    subgraph frontend [Frontend - Vite React]
        App[App.jsx routes]
        ChatThread[ChatThread lens-bound]
        Cards[TitleCard]
        Config[ConfigPage persona sliders]
        Detail[TitleDetailPage]
        ReviewsUI[ReviewPromptCard]
    end

    subgraph backend [Backend - FastAPI]
        Routes[app.py routes]
        Setup[setup.py wizard]
        JobMgr[jobs.py]
    end

    subgraph agentLayer [Agent layer]
        Curator[curator.py CuratorAgent]
        Tools[tools.py ToolRegistry]
        Providers[providers BYOP LLM]
    end

    subgraph library [Library and RAG]
        Sync[sync.py]
        Search[search.py]
        Emb[embeddings.py]
        Titles[titles.py]
        Db[db.py Database]
    end

    subgraph connectors [Connectors]
        PlexC[plex.py]
        TMDBC[tmdb.py]
        RadarrC[radarr.py]
        SonarrC[sonarr.py]
    end

    App --> Routes
    Routes --> Curator
    Curator --> Tools
    Curator --> Providers
    Tools --> Search
    Tools --> Db
    JobMgr --> Sync
    Sync --> Db
    Sync --> Emb
    Search --> Emb
    Sync --> PlexC
```

### Frontend (Vite / React)

- **Single workspace** — chat thread, welcome panel, watchlist sidebar, keyboard shortcuts.
- **Lens switcher** — updates active `lens_id`, theme accents, and chat scope.
- **ChatThread** — renders blocks: `text`, `title_cards`, `action_prompt`, review prompts.
- **ConfigPage** — setup wizard, persona sliders, live service validation.

See [WEB_UI.md](WEB_UI.md) and [DESIGN.md](DESIGN.md).

### Backend (FastAPI)

- REST + SSE under `/api/*`.
- **Lens API** — `/api/lenses`, `/api/lenses/active`.
- **Persona API** — `/api/persona`, `/api/system-config`.
- **Reviews API** — `/api/reviews` with optional Plex rating sync and conflict handling.
- **Webhooks** — `POST /api/webhooks/plex` for near-completion rating prompts (optional shared secret).
- **JobManager** — background library sync with progress polling.
- **CuratorAgent** — accepts `lens_id`; builds persona-aware system prompt; tool list respects feature flags.

### Library and RAG

Unchanged core: Plex sync → SQLite upsert → TMDB enrichment → embedding rebuild → semantic search.

### Connectors

Thin HTTP clients for Plex, TMDB, *arr, Fanart, Tautulli, TVDB.

---

## Data flows

### Chat / agent turn (lens-scoped)

```mermaid
sequenceDiagram
    participant UI
    participant API
    participant Agent as CuratorAgent
    participant DB
    participant LLM

    UI->>API: POST /api/chat lens_id message
    API->>Agent: run session_id message lens_id
    Agent->>DB: ensure_chat_session lens_id
    Agent->>DB: chat_history filtered by lens_id
    Agent->>DB: get_persona + build_system_prompt
    Agent->>LLM: chat messages tools
    Agent->>DB: save_chat_message user + assistant lens_id
    Agent-->>API: message lens_id pending_tokens
    API-->>UI: JSON response
```

### Library sync

`POST /api/library/sync` → JobManager → Plex/Radarr/Sonarr/TMDB → embeddings. Jobs persist under `DATA_DIR/jobs_state.json`; inspect `GET /api/jobs` for phase / percent / message. Interrupted runs after restart are marked failed with a recovery message; a new sync resumes from the last valid phase checkpoint (≤72h).

### Add-to-Radarr confirmation

Two-phase: propose token → user confirm → execute. TTL 600 seconds.

---

## Technology stack

| Layer | Choice | Rationale |
|-------|--------|-----------|
| Runtime | Python 3.10+ | Async-friendly, homelab standard |
| Web | FastAPI + Uvicorn | Typed routes, SSE |
| Frontend | Vite + React | Single-workspace SPA without SSR complexity |
| Database | SQLite | Zero-ops; single-file backup |
| Vectors | NumPy + JSON in SQLite | Adequate for home libraries |
| Container | Multi-stage Docker | Node build + Python slim |

---

## Deployment architecture

```mermaid
flowchart TB
    subgraph dockerHost [Docker host]
        subgraph container [curatorx container]
            Uvicorn[Uvicorn :8788]
            Static[frontend/dist]
            ConfigVol["/config volume"]
        end
        Ollama[Ollama on host optional]
    end

    subgraph lan [LAN services]
        PlexS[Plex :32400]
        RadarrS[Radarr]
        SonarrS[Sonarr]
    end

    UserBrowser[Browser] --> Uvicorn
    Uvicorn --> Static
    Uvicorn --> ConfigVol
    Uvicorn --> PlexS
    Uvicorn --> RadarrS
    Uvicorn --> SonarrS
    Uvicorn --> Ollama
```

See [DOCKER.md](DOCKER.md) for Mac Colima, Unraid, and Compose details.

---

## Security model

| Topic | Behavior |
|-------|----------|
| Authentication | **None by default** — single implicit owner on trusted LAN. With `features.multi_user_enabled`, **Sign in with Plex** PIN + session cookies; middleware protects `/api/*` (allowlist: health/features/auth/webhooks) |
| Roles | Owner-only: settings, setup tests, library sync mutate, persona/lens writes. Guests cannot request media / *arr writes |
| Partitioning | Chat, pending actions, watchlist, reviews, preferences scoped by `user_id` when multi-user is on (shared library remains household-wide) |
| Feature gates | `GET /api/features` exposes enabled flags; auth UI, Seerr, and Plex collection tools stay hidden until opted in |
| Webhooks | Require non-empty `webhook_secret` / `CURATORX_WEBHOOK_SECRET` + matching `X-CuratorX-Webhook-Secret` |
| Destructive actions | Confirmation tokens for all *arr / Seerr writes; tokens bound to user when multi-user is on |
| Session secret | Auto-persisted under DATA_DIR; `CURATORX_SESSION_SECRET` preferred; public default refused for multi-user |
| Secrets | Masked on API read; env overrides file |
| Lens isolation | Chat and taste scoped by `lens_id`; no cross-lens history leakage in API |
| MCP | Optional stdio + HTTP `/mcp`; dual keys (`CURATORX_MCP_API_KEY` privacy / `CURATORX_MCP_FULL_API_KEY` full) |

See [SECURITY.md](SECURITY.md) and [wiki/Multi-User.md](wiki/Multi-User.md) for the full partitioning matrix.

---

## Extension points (1.0+)

| Extension | Status |
|-----------|--------|
| Curation lenses | **Implemented** — CRUD, active lens, chat filter |
| Persona sliders / presets | **Implemented** — DB-backed, hot-reload prompt |
| Single chat workspace | **Implemented** — see [WEB_UI.md](WEB_UI.md) |
| Durable sync jobs | **Implemented** — `jobs_state.json` + restart recovery |
| Reviews + Plex sync | **Implemented** — personal stars, conflict detection, webhook prompts |
| Plex webhooks | **Implemented** — near-completion rating queue; optional auth secret |
| Agent blueprints | Schema present; scheduler wiring **Future** |
| Interaction telemetry | Schema present; ingestion **Future** |
| True LLM SSE streaming | **Future** |
| OIDC / local auth | **Future** (not shipped) |

---

## Related documentation

- [DESIGN.md](DESIGN.md) — UX principles, agent tools
- [DATA_MODEL.md](DATA_MODEL.md) — SQLite and PRD tables
- [wiki/Home.md](wiki/Home.md) — operator wiki
- [CONFIGURATION.md](CONFIGURATION.md) — settings reference
- [FAQ.md](FAQ.md) — common questions