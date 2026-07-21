# Product Requirement Document (PRD)

> **Historical design archive.** This PRD documents early design thinking. CuratorX **1.0+** ships a single chat workspace (see [WEB_UI.md](../WEB_UI.md) and [wiki/Home.md](../wiki/Home.md)). For the current roadmap and system overview, see [ARCHITECTURE.md](../ARCHITECTURE.md). Prefer the wiki and README for operator docs.

**Project CuratorX: Ambient Intent Derivation & Zero-Touch UI**  
**Version 3.0 (design archive)**

## 1. Product Vision & Behavioral Shift

CuratorX eliminates manual profile switching, prompt tagging, and explicitly managed curation lanes. The platform transitions to a single, continuous user thread that adapts to topic changes automatically. Contexts are lightweight shells derived from conversational signals, allowing the agent to respond with relevant taste memory without manual lens switching.

```
[Conversational Input]
         │
         ▼
[Context Shell Resolution (rule-based)]
         │
         ▼
[Persona-Aware Agent Response]
```

## 2. Adaptive Onboarding Flow (3-Card Wizard)

The wizard inside `frontend/src/pages/ConfigPage.jsx` is a controlled 3-step state machine:

```
[Step 1: Identity Seed] ──> [Step 2: Infrastructure Matrix] ──(Plex verified)──> [Step 3: Dropdown Mapping] ──> [Main App]
```

| Step | Key | Purpose | Advance when |
|------|-----|---------|--------------|
| 1 | `identity_seed` | Curator name only | Name entered |
| 2 | `infrastructure` | LLM + Plex + Radarr + Sonarr verify | All four certified |
| 3 | `dropdown_mapping` | Movie/show Plex library `<select>` dropdowns | Both sections chosen |

**Finish** sets `onboarding_complete: true` when LLM, Plex (with sections), Radarr, and Sonarr are all certified.

Removed from first-run wizard (maintenance dashboard only):

- Persona sliders (available in maintenance dashboard)
- Optional services (TMDB, Fanart.tv, Tautulli)
- Manual lens creation UI (deprecated; APIs retained)

### Plex dropdown UX

- On successful `test_plex`, `plex_url` / `plex_token` inputs collapse
- Step 3 shows `<select>` filtered by `type === "movie"` and `type === "show"`
- Selections persist to `plex_movie_section` / `plex_tv_section` on change and step advance

## 3. Unified Interface (Zero-Touch Experience)

### Command workspace

- Monospace command lane with **ambient context indicator** (e.g. `⧉ [General Exploration] > _`)
- Replaces manual lens prefix in primary chat surfaces

### Maintenance dashboard

Post-onboarding Settings exposes integration re-testing, persona sliders, optional metadata services, legacy lens management, and advanced paths.

## 4. Technical Schema

Migrations in `curatorx/library/db.py`:

| Table / view | Role |
|--------------|------|
| `derived_contexts` | Context shells (`context_hash`, `inferred_label`) for ambient scoping |
| `integration_profiles` | View alias over `service_integrations` |
| `system_telemetry_stream` | Interaction logging with context references (**implemented** ingest + admin APIs) |
| `service_integrations` | Certification status per service (unchanged) |

Default derived context: `context_hash='general'`, label **General Exploration**.

## 5. Architectural Codebase Mapping

```
├── frontend/
│   └── src/
│       ├── App.jsx                 — ambient context indicator, legacy lens sidebar
│       ├── api/client.js           — WIZARD_STEPS (3), getActiveContext, getPlexSections
│       ├── components/
│       │   └── TurnstyleViewport.jsx
│       └── pages/
│           └── ConfigPage.jsx      — 3-card onboarding + maintenance dashboard
└── curatorx/
    ├── library/
    │   └── db.py                   — derived_contexts, telemetry, integration_profiles view
    └── web/
        ├── app.py                  — GET /api/context/active, /api/setup/wizard
        └── setup.py                — build_wizard_status (3 steps), test_plex sections
```

## 6. Deferred Work

Historical PRD backlog — several items below are **shipped** (see [ARCHITECTURE.md](../ARCHITECTURE.md) extension points):

~~- Telemetry ingestion from playback streams~~ → **Implemented** (admin telemetry APIs)
~~- True LLM SSE streaming~~ → **Implemented**
~~- OIDC / local-password auth~~ → **Implemented** (opt-in)

Still deferred / partial:

- Full deprecation/removal of `curation_lenses` APIs
- Agent blueprints richer scheduler wiring
- Plex Lists publish (pending stable Plex Discover API)
- Deeper plot-semantic natural-language discovery beyond current library embeddings

---

> **Current roadmap:** This PRD is a historical design archive. For the living roadmap and system overview, see [ARCHITECTURE.md](../ARCHITECTURE.md).
