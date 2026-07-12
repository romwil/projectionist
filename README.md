# CuratorX

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Docker Hub](https://img.shields.io/badge/docker-romwil%2Fcuratorx-2496ED?logo=docker&logoColor=white)](https://hub.docker.com/r/romwil/curatorx)
[![Version](https://img.shields.io/badge/version-1.0.9-green.svg)](CHANGELOG.md)

**An intent-aware curation companion for self-hosted Plex libraries.**

CuratorX turns your homelab from a passive download queue into a context-aware curator. It knows what you own, learns taste within isolated **curation lenses**, and recommends hidden gems, collection gaps, and purge candidates — then adds titles to Radarr/Sonarr only after you confirm.

> Dumb recommenders average everything you ever watched. CuratorX sandboxes taste by lens so a late-night comfort binge never poisons your director-study discovery lane.

---

## Table of contents

- [Why CuratorX](#why-curatorx)
- [Features](#features)
- [Quick start](#quick-start)
- [Docker Hub / Unraid](#docker-hub--unraid)
- [Configuration](#configuration)
- [Optional: multi-user & Seerr](#optional-multi-user--seerr)
- [Documentation & wiki](#documentation--wiki)
- [Testing](#testing)
- [Contributing](#contributing)
- [License](#license)

---

## Why CuratorX

| Typical recommender | CuratorX |
|---------------------|----------|
| One global taste profile | **Lens isolation** — separate contexts (General, Director Studies, …) |
| “Top 10 on Netflix” vibes | **Library-grounded RAG** — answers from what you own and watch |
| Opaque scores | **Explainable cards** — every title carries a `recommendation_reason` |
| Auto-grab everything | **Confirmation-gated *arr** — Radarr/Sonarr writes need explicit approval |
| Vendor-locked AI | **BYOP LLM** — OpenAI, Anthropic, Ollama, or any OpenAI-compatible endpoint |

CuratorX complements disk tools like [Reclaimspace](https://github.com/romwil/reclaimspace): Reclaimspace quarantines duplicate files; CuratorX helps you decide *what* deserves the space.

---

## Features

- **Single chat workspace** — full-width conversation with sidebar threads, welcome panel, and status dock
- **Chat-first curator** — discovery, gap analysis, purge advice, and “what to watch tonight”
- **Curation lenses** — hard walls between taste contexts; chat history and telemetry scoped by `lens_id`
- **Dynamic persona** — name your curator and tune tone sliders
- **RAG over Plex** — semantic search with embeddings over your indexed library
- **Durable library sync** — background jobs with live phase / count / `%` progress; state survives container restarts
- **Safe automation** — short-lived confirmation tokens for all Radarr/Sonarr mutations
- **Unraid-ready** — single Docker container, SQLite persistence, Community Applications template

---

## Quick start

### Docker Hub (recommended)

```bash
docker pull romwil/curatorx:1.0
docker run -d --name curatorx \
  -p 8788:8788 \
  -v /path/to/curatorx/config:/config \
  romwil/curatorx:1.0
```

Open **http://localhost:8788** and complete the setup wizard.

### Docker Compose

```bash
git clone https://github.com/romwil/curatorx.git
cd curatorx
cp .env.example .env
docker compose up -d --build
```

### Local development

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[web]"
cd frontend && npm install && npm run build && cd ..
DATA_DIR=./config python -m curatorx.web
```

---

## Docker Hub / Unraid

Published multi-arch images (**amd64 + arm64**):

| Tag | Use |
|-----|-----|
| [`romwil/curatorx:1.0.9`](https://hub.docker.com/r/romwil/curatorx) | Pin an exact release |
| [`romwil/curatorx:1.0`](https://hub.docker.com/r/romwil/curatorx) | Track the 1.0 line |
| [`romwil/curatorx:latest`](https://hub.docker.com/r/romwil/curatorx) | Newest stable |

**Unraid:** install from Community Applications using the template (`templates/curatorx.xml` / `unraid/curatorx.xml`), or add the container manually:

| Setting | Value |
|---------|-------|
| Repository | `romwil/curatorx:1.0` |
| Port | `8788` |
| Config path | `/mnt/user/appdata/curatorx/config` → `/config` |

Full steps: [Wiki → Unraid](docs/wiki/Unraid.md) · [Docker guide](docs/DOCKER.md)

---

## Configuration

Settings live in `{DATA_DIR}/settings.json` (Docker: `/config/settings.json`). Environment variables from `.env` seed first-run values.

Minimum to be useful: **Plex URL + token**, **movie/TV library sections**, **TMDB API key**, and an **LLM provider**. Radarr/Sonarr unlock add/remove after confirmation.

See [CONFIGURATION.md](docs/CONFIGURATION.md) and [Wiki → Configuration](docs/wiki/Configuration.md).

---

## Optional: multi-user & Seerr

CuratorX ships as a **single-owner** app with no login screen. Household features are opt-in:

| Flag | Default | Effect |
|------|---------|--------|
| `features.multi_user_enabled` | `false` | Plex sign-in gate; owner vs member roles |
| `features.seerr_enabled` | `false` | Seerr discovery / request path for members |

OIDC and local username/password auth are **not** implemented in 1.0 — use Plex login when multi-user is on.

Details: [Wiki → Multi-User](docs/wiki/Multi-User.md) · [Wiki → Seerr](docs/wiki/Seerr.md)

---

## Documentation & wiki

| Doc | Description |
|-----|-------------|
| **[Wiki home](docs/wiki/Home.md)** | In-repo wiki index |
| [FAQ](docs/FAQ.md) | Common questions |
| [Onboarding](docs/ONBOARDING.md) | First-run checklist |
| [Web UI](docs/WEB_UI.md) | Workspace layout and routes |
| [Architecture](docs/ARCHITECTURE.md) | System context and data flows |
| [Design](docs/DESIGN.md) | UX principles and agent tools |
| [Data model](docs/DATA_MODEL.md) | SQLite schema |
| [Configuration](docs/CONFIGURATION.md) | Env vars and settings |
| [Docker / Unraid](docs/DOCKER.md) | Container deployment |
| [Testing](docs/TESTING.md) | Unit, Playwright, CA checklist |
| [Changelog](CHANGELOG.md) | Release notes |

---

## Testing

```bash
# Backend
.venv/bin/python -m unittest discover -s tests -v

# Frontend unit
cd frontend && npm run test:unit

# Mocked Playwright (no live Plex/LLM required)
npm run test:e2e
```

CA-focused suites and live optional gates: [TESTING.md](docs/TESTING.md).

---

## Contributing

1. Fork [romwil/curatorx](https://github.com/romwil/curatorx)
2. Create a feature branch: `git checkout -b feat/your-idea`
3. Install: `pip install -e ".[web]"` and `cd frontend && npm install`
4. Run the unit suites above, then open a PR with a clear description and test plan

Open [issues](https://github.com/romwil/curatorx/issues) for lens presets, agent blueprints, and connector ideas.

---

## License

MIT — see [LICENSE](LICENSE).
