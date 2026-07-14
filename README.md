# CuratorX

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Docker Hub](https://img.shields.io/badge/docker-romwil%2Fcuratorx-2496ED?logo=docker&logoColor=white)](https://hub.docker.com/r/romwil/curatorx)
[![Version](https://img.shields.io/badge/version-1.2.0-green.svg)](CHANGELOG.md)

**A cinema-dark chat curator for your self-hosted Plex library.**

CuratorX sits between Plex and your *arr stack: talk about taste, find gaps and purge candidates, rate what you watched, and add titles to Radarr or Sonarr only after you confirm. Bring your own LLM (cloud or local). Built for Unraid and Docker.

> Ordinary recommenders blend everything you’ve ever watched. CuratorX keeps taste contexts separate so a comfort binge doesn’t reshape your discovery lane.

---

## Who it’s for

Homelab folks who already run **Plex** (and usually Radarr/Sonarr), want conversational curation over *their* library — not a Netflix top-10 — and prefer one clear UI over another request queue.

---

## Highlights

- **Cinema-dark chat workspace** — Fraunces + DM Sans, amber accent, poster-forward title cards, turnstyle recommendation strips, slash commands
- **Library-grounded curator** — RAG over your indexed Plex library; explainable “why this?” on every card
- **Confirm before you grab** — Radarr / Sonarr (and optional Seerr) writes need an explicit confirm in chat or the status dock
- **Ratings & watchlists** — half-star reviews, optional sync to Plex stars, household watchlist pins
- **Sync that survives restarts** — durable jobs with live phase / count / %; phase checkpoints resume unfinished work (≤72h); embeddings skip unchanged titles
- **Household optional** — Overseerr-style **Sign in with Plex** (PIN); shared conversations and roles when you turn multi-user on
- **BYOP LLM** — OpenAI, Anthropic, Ollama, or any OpenAI-compatible endpoint
- **Unraid-ready** — `romwil/curatorx`, single `/config` volume, Community Applications template

CuratorX complements disk tools like [Reclaimspace](https://github.com/romwil/reclaimspace): Reclaimspace quarantines duplicate files; CuratorX helps you decide *what* deserves the space.

---

## Quick start

### Docker Hub (recommended)

```bash
docker pull romwil/curatorx:1.1
docker run -d --name curatorx \
  -p 8788:8788 \
  -v /path/to/curatorx/config:/config \
  romwil/curatorx:1.1
```

Open **http://localhost:8788** and complete the setup wizard (Name → Connections → Libraries).

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
| [`romwil/curatorx:1.2.0`](https://hub.docker.com/r/romwil/curatorx) | Pin an exact release |
| [`romwil/curatorx:1.2`](https://hub.docker.com/r/romwil/curatorx) | Track the 1.2 line |
| [`romwil/curatorx:1.1`](https://hub.docker.com/r/romwil/curatorx) | Track the 1.1 line |
| [`romwil/curatorx:latest`](https://hub.docker.com/r/romwil/curatorx) | Newest stable |

**Unraid:** install from Community Applications using the template (`templates/curatorx.xml` / `unraid/curatorx.xml`; CA icons at `unraid/curatorx-icon.png` / `unraid/curatorx-icon-512.png`), or add the container manually:

| Setting | Value |
|---------|-------|
| Repository | `romwil/curatorx:1.1` |
| Port | `8788` |
| Config path | `/mnt/user/appdata/curatorx/config` → `/config` |

Full steps: [Wiki → Unraid](docs/wiki/Unraid.md) · [Docker guide](docs/DOCKER.md)

---

## Configuration

Settings live in `{DATA_DIR}/settings.json` (Docker: `/config/settings.json`). Environment variables from `.env` seed first-run values.

**Config is for connecting services:** Plex server URL + **server token** (library sync), movie/TV libraries, TMDB, your LLM, and optionally Radarr/Sonarr. That server token is not the household login path.

See [CONFIGURATION.md](docs/CONFIGURATION.md) and [Wiki → Configuration](docs/wiki/Configuration.md).

---

## Optional: multi-user & Seerr

Default install is **single-owner** — no login screen. Household features are opt-in:

| Flag | Default | Effect |
|------|---------|--------|
| `features.multi_user_enabled` | `false` | **Sign in with Plex** (PIN / link, Overseerr-style); owner vs member |
| `features.seerr_enabled` | `false` | Seerr discovery / request path for members |

OIDC and local username/password are not shipped — use Plex PIN login when multi-user is on. Token paste on `/login` is an advanced fallback only.

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

Open [issues](https://github.com/romwil/curatorx/issues) for ideas and bugs.

---

## License

MIT — see [LICENSE](LICENSE).
