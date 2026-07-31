# Projectionist

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Docker Hub](https://img.shields.io/badge/docker-romwil%2Fprojectionist-2496ED?logo=docker&logoColor=white)](https://hub.docker.com/r/romwil/projectionist)
[![Version](https://img.shields.io/badge/version-1.29.24-green.svg)](CHANGELOG.md)

**Cinema intelligence for your personal archive.**

Projectionist is an open-source, self-hosted cinema intelligence engine and agentic companion for personal media libraries — local-first, zero-telemetry, with vector mapping, multi-signal taste modeling, MCP access, and hardened multi-tenant roles (Owner / Member / Youth / Guest).

It sits between Plex and your *arr stack: talk about taste, browse Explore rails, find gaps and purge candidates, rate what you watched, and add titles to Radarr or Sonarr only after you confirm. Bring your own LLM (cloud or local). Built for Unraid and Docker.

---

## Overview

Ordinary recommenders blend everything you’ve ever watched into one noisy profile. Projectionist keeps taste contexts separate so a comfort binge doesn’t reshape your discovery lane — and the LLM never bulk-exports your collection. It issues targeted tool calls against a highly optimized local SQLite index of structured credits/facets and layered plot text. Your Plex token and personal collection stay on your hardware.

> The LLM gets to act like a natural language surgeon on a highly optimized, predictable local dataset. It’s incredibly fast, it’s cheap, and it keeps your Plex token and personal collection server info locked down.

---

## Architecture

```
                 ┌─────────────────────────────┐
                 │     Projectionist UI / MCP  │
                 │   (Owner · Member · Youth)  │
                 └──────────────┬──────────────┘
                                │
              ┌─────────────────┼─────────────────┐
              ▼                 ▼                 ▼
        ┌──────────┐     ┌────────────┐    ┌────────────┐
        │  Chat /  │     │  Explore / │    │ Dual-key   │
        │  Agent   │     │  Plot Lab  │    │ MCP tools  │
        └────┬─────┘     └─────┬──────┘    └─────┬──────┘
             │                 │                 │
             └─────────────────┼─────────────────┘
                               ▼
                    ┌────────────────────┐
                    │  Local SQLite index │
                    │  + optional vec ANN │
                    └─────────┬──────────┘
                              │
            ┌─────────────────┼─────────────────┐
            ▼                 ▼                 ▼
       ┌─────────┐      ┌──────────┐      ┌──────────┐
       │  Plex   │      │ Radarr / │      │ BYO LLM  │
       │ library │      │ Sonarr   │      │ endpoint │
       └─────────┘      └──────────┘      └──────────┘
```

Teaching principles: **sync vs idle trickle**, **materialize similarity**, **honest provenance**, and **homelab SQLite constraints**. Dual MCP keys (privacy / full) let you share read-only library access externally while keeping *arr mutations behind a separate trust boundary. See [MCP.md](docs/MCP.md) and [ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## Key capabilities

- **Chat + Explore** — cinema workspace with Lights Up / Lights Down themes; `/explore` browse hub; title detail with trailer, Watch on Plex, and **More Like This** neighbors
- **Library-grounded curator** — RAG + facet query over structured credits/motifs and layered plot text; explainable “why this?”; agent tools for similar titles, relations, and people
- **Confirm before you grab** — Radarr / Sonarr (and optional Seerr) writes need an explicit confirm in chat or the status dock
- **Ratings, watchlists & household recommends** — 1–5★ reviews (optional Plex sync), Plex Discover watchlist pull, peer recommendations inbox
- **Owner dashboard** — library composition charts, health gauges, multi-select purge, taste timeline
- **Sync that survives restarts** — durable jobs with live phase / count / %; idle trickle for metadata, embeddings, neighbors, and title relations
- **Privacy-first MCP** — dual trust-plane keys over the same local index
- **Household optional** — **Sign in with Plex** (PIN), optional local password and/or OIDC; roles when multi-user is on
- **BYOP LLM** — OpenAI, Anthropic, Ollama, or any OpenAI-compatible endpoint; true SSE token streaming
- **Unraid-ready** — `romwil/projectionist:latest`, single `/config` volume, non-root container

Projectionist complements disk tools like [Reclaimspace](https://github.com/romwil/reclaimspace): Reclaimspace quarantines duplicate files; Projectionist helps you decide *what* deserves the space.

---

## Quick start

### Docker Hub (recommended)

```bash
docker pull romwil/projectionist:latest
docker run -d --name projectionist \
  -p 8788:8788 \
  -v /path/to/projectionist/config:/config \
  romwil/projectionist:latest
```

Open **http://localhost:8788** and complete the setup wizard (Name → Connections → Libraries).

During the compatibility window, the same image digests are also published as `romwil/curatorx:*`.

### Docker Compose

```yaml
services:
  projectionist:
    image: romwil/projectionist:latest
    ports:
      - "8788:8788"
    volumes:
      - ./config:/config
    environment:
      - PROJECTIONIST_SESSION_SECRET=change-me
    restart: unless-stopped
```

Or from a clone:

```bash
git clone https://github.com/romwil/projectionist.git
cd projectionist
cp .env.example .env
docker compose up -d --build
```

### Local development

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[web]"
cd frontend && npm install && npm run build && cd ..
DATA_DIR=./config python -m projectionist.web
```

### Windows (PowerShell)

WSL/bash is not required. One-shot setup: `.\scripts\setup-dev.ps1`. Or from the repo root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[web]"
cd frontend; npm install; npm run build; cd ..
$env:DATA_DIR = ".\config"
python -m projectionist.web
```

Or: `.\scripts\dev-server.ps1` (builds the frontend if needed; default **http://127.0.0.1:8788**).

**Python:** Prefer python.org 3.12 (not Microsoft Store). Per-user install:

```powershell
winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
Remove-Item -Recurse -Force .venv -ErrorAction SilentlyContinue
.\scripts\setup-dev.ps1
```

**E2E (mocked Playwright, port 8799):** `.\scripts\run-e2e.ps1` or `npm run test:e2e`. Playwright starts the app via `node scripts/start-e2e-server.mjs` (not bash). Avoid using **8788** for e2e if that port is an SSH tunnel to production.

---

## Docker Hub / Unraid

Published multi-arch images (**amd64 + arm64**):

| Tag | Use |
|-----|-----|
| [`romwil/projectionist:latest`](https://hub.docker.com/r/romwil/projectionist) | Everyday Unraid / Compose (CA template default) |
| [`romwil/projectionist:<MAJOR.MINOR>`](https://hub.docker.com/r/romwil/projectionist) | Track a minor line |
| [`romwil/projectionist:<X.Y.Z>`](https://hub.docker.com/r/romwil/projectionist) | Pin an exact release (see [CHANGELOG.md](CHANGELOG.md)) |

**Unraid:** install from Community Applications using the Projectionist template (or add the container manually):

| Setting | Value |
|---------|-------|
| Repository | `romwil/projectionist:latest` |
| Port | `8788` |
| Config path (existing installs) | `/mnt/user/appdata/curatorx/config` → `/config` |
| Config path (new installs) | `/mnt/user/appdata/projectionist/config` → `/config` is fine |

Existing Unraid installs should keep `/mnt/user/appdata/curatorx*` — those host paths are stable. New installs may use `…/projectionist`.

Full steps: [Wiki → Unraid](docs/wiki/Unraid.md) · [Docker guide](docs/DOCKER.md)

---

## Configuration

Settings live in `{DATA_DIR}/settings.json` (Docker: `/config/settings.json`). Environment variables from `.env` seed first-run values.

**Config is for connecting services:** Plex server URL + **server token** (library sync), movie/TV libraries, TMDB, your LLM, and optionally Radarr/Sonarr. That server token is not the household login path.

### Environment variables (branded prefix)

Prefer `PROJECTIONIST_*`. During the compatibility window (~2 releases), matching `CURATORX_*` values are still read when the new key is absent.

| Variable | Purpose |
|----------|---------|
| `PROJECTIONIST_SESSION_SECRET` | Session signing secret |
| `PROJECTIONIST_WEBHOOK_SECRET` | Shared secret for inbound webhooks |
| `PROJECTIONIST_MCP_*` | MCP mode / API keys (see [MCP.md](docs/MCP.md)) |
| `PROJECTIONIST_GUEST_TOUR_ENABLED` | Guest tour gate |
| `PROJECTIONIST_LOG_LEVEL` | Logging verbosity |
| `PROJECTIONIST_LOG_FILE` | Optional override for the durable app log (default `{DATA_DIR}/logs/projectionist.log`; Unraid: `/config/logs/projectionist.log`) |
| `DATA_DIR` | Config + SQLite directory (unchanged; not brand-prefixed) |

See [CONFIGURATION.md](docs/CONFIGURATION.md) and [Wiki → Configuration](docs/wiki/Configuration.md) for the full matrix.

---

## Privacy & zero telemetry

Projectionist is self-hosted and **zero-telemetry by design** — no phone-home analytics, no cloud account required for the product itself. See [PRIVACY.md](docs/PRIVACY.md) (also the in-app **`/privacy`** page) for what is stored, what household members vs owners see, and what MCP / the LLM receive. Operators: [SECURITY.md](docs/SECURITY.md).

---

## Optional: multi-user & Seerr

Default install is **single-owner** — no login screen. Household features are opt-in:

| Flag | Default | Effect |
|------|---------|--------|
| `features.multi_user_enabled` | `false` | Login + session cookies; owner vs member partitioning |
| `features.seerr_enabled` | `false` | Seerr discovery / request path for members |
| `features.live_channels_enabled` | `false` | Tunarr-backed Live Channels → additional Plex Live TV tuner (Admin → Live Channels; keeps OTA) |

Auth methods are opt-in: **Sign in with Plex** (PIN), **local password** (owner registration), and/or **OIDC** (Authelia, Authentik, Keycloak, etc.). The login page shows whatever is configured (`auth_methods` from `GET /api/features`). Plex token paste remains an advanced fallback.

Details: [Wiki → Multi-User](docs/wiki/Multi-User.md) · [Wiki → Seerr](docs/wiki/Seerr.md) · [CONFIGURATION.md](docs/CONFIGURATION.md)

---

## Documentation & wiki

| Doc | Description |
|-----|-------------|
| **[Wiki home](docs/wiki/Home.md)** | In-repo wiki index |
| [Privacy](docs/PRIVACY.md) | Data use (household + owner); in-app `/privacy` |
| [Security](docs/SECURITY.md) | Threat model and findings checklist |
| [Penetration tests](docs/security/pentests/README.md) | Repeatable Protocol v1.0 + harness |
| [FAQ](docs/FAQ.md) | Common questions |
| [Help](docs/HELP.md) | In-app Help source (`/help`); role-aware product guide |
| [Curator knowledge](docs/CURATOR_KNOWLEDGE.md) | Library knowledge depth, motifs, idle curation |
| [Onboarding](docs/ONBOARDING.md) | First-run checklist |
| [Web UI](docs/WEB_UI.md) | Workspace layout and routes |
| [Architecture](docs/ARCHITECTURE.md) | System context and data flows |
| [Design](docs/DESIGN.md) | UX principles and agent tools |
| [Data model](docs/DATA_MODEL.md) | SQLite schema |
| [MCP](docs/MCP.md) | Dual-mode MCP keys, schemas, and tools |
| [Configuration](docs/CONFIGURATION.md) | Env vars and settings |
| [Docker / Unraid](docs/DOCKER.md) | Container deployment |
| [Release runbook](docs/RELEASE.md) | Version bump, CHANGELOG, GitHub release, multi-arch Docker Hub |
| [Delight wishlist](docs/DELIGHT-WISHLIST.md) | Persona backlog + the phased delight roadmap |
| [Documentation style](docs/DOCS_STYLE.md) | The durable docs standard (warm + E-E-A-T, worked examples, runnable snippets) |
| [Testing (e2e / CA)](docs/TESTING.md) | Playwright and CA release checklist |
| [Value-based testing](TESTING.md) | How to write logic-level backend tests |
| [Feature testing blueprint](docs/superpowers/specs/2026-07-29-feature-testing-environment-blueprint.md) | CI + QA sidecar + Interactive UI QA + pentest layers |
| [Cursor QA environment design](docs/superpowers/specs/2026-07-29-cursor-qa-environment-design.md) | Product-agnostic extract for other Cursor projects |
| [Changelog](CHANGELOG.md) | Release notes |

---

## Testing

```bash
# Backend
.venv/bin/python -m pytest

# Frontend unit
cd frontend && npm run test:unit

# Mocked Playwright (no live Plex/LLM required)
npm run test:e2e
```

CA-focused suites and live optional gates: [TESTING.md](docs/TESTING.md). Full-stack layers (value tests, mocked e2e, maintainer QA, red-hat pentest): [Feature testing environment blueprint](docs/superpowers/specs/2026-07-29-feature-testing-environment-blueprint.md).

---

## Contributing

1. Fork [romwil/projectionist](https://github.com/romwil/projectionist)
2. Create a feature branch: `git checkout -b feat/your-idea`
3. Install: `pip install -e ".[web]"` and `cd frontend && npm install`
4. Run the unit suites above, then open a PR with a clear description and test plan

**Docs gate:** user-facing changes update the relevant guide **and** add a benefit-led CHANGELOG `### Highlights` entry, meeting [docs/DOCS_STYLE.md](docs/DOCS_STYLE.md). Documentation is a first-class deliverable, checked in every PR.

Open [issues](https://github.com/romwil/projectionist/issues) for ideas and bugs.

---

## License

MIT — see [LICENSE](LICENSE).
