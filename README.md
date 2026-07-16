# CuratorX

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Docker Hub](https://img.shields.io/badge/docker-romwil%2Fcuratorx-2496ED?logo=docker&logoColor=white)](https://hub.docker.com/r/romwil/curatorx)
[![Version](https://img.shields.io/badge/version-1.8.1-green.svg)](CHANGELOG.md)

**Agentic access to your structured + unstructured local media data — chat curator, Explore hub, and privacy-first MCP for self-hosted Plex.**

CuratorX sits between Plex and your *arr stack: talk about taste, browse Explore rails, find gaps and purge candidates, rate what you watched, and add titles to Radarr or Sonarr only after you confirm. Bring your own LLM (cloud or local). Built for Unraid and Docker.

**Privacy:** CuratorX is self-hosted — see [PRIVACY.md](docs/PRIVACY.md) (also the in-app **`/privacy`** page) for what is stored, what household members vs owners see, and what MCP / the LLM receive. Operators: [SECURITY.md](docs/SECURITY.md).

> Ordinary recommenders blend everything you’ve ever watched. CuratorX keeps taste contexts separate so a comfort binge doesn’t reshape your discovery lane.

---

## Design philosophy

CuratorX is a **real-world, production-quality example of agentic access** to structured and unstructured local data. Structured rows (credits, release dates, facets, relations) and unstructured plot text (Plex summaries, TMDB overviews, optional LLM loglines) live in one SQLite index. The LLM never bulk-exports your collection — it issues targeted tool calls; Explore and Title Detail read the same materialized caches.

> “The LLM gets to act like a natural language surgeon on a highly optimized, predictable local dataset. It’s incredibly fast, it’s cheap, and it keeps your Plex token and personal collection server info locked down.”

Teaching principles: **sync vs idle trickle** (keep interactive sync fast; enrich in the background), **materialize similarity** (`item_neighbors` / `title_relations` instead of per-click O(n²)), **honest provenance** (never invent release dates from year alone), and **homelab SQLite constraints** (WAL, busy timeout, capped idle writers). Dual MCP API keys (privacy / full) let you share read-only library access externally while keeping *arr mutations behind a separate trust boundary. See [MCP.md](docs/MCP.md) and [ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## Who it’s for

Homelab folks who already run **Plex** (and usually Radarr/Sonarr), want conversational curation over *their* library — not a Netflix top-10 — and prefer one clear UI over another request queue.

---

## Highlights

- **Chat + Explore** — cinema workspace with Lights Up / Lights Down themes; `/explore` browse hub; title detail with trailer, Watch on Plex, and **More Like This** neighbors
- **Library-grounded curator** — RAG + facet query over structured credits/motifs and layered plot text; explainable “why this?”; agent tools for similar titles, relations, and people
- **Confirm before you grab** — Radarr / Sonarr (and optional Seerr) writes need an explicit confirm in chat or the status dock
- **Ratings, watchlists & household recommends** — 1–5★ reviews (optional Plex sync), Plex Discover watchlist pull, peer recommendations inbox
- **Owner dashboard** — library composition charts, health gauges, multi-select purge, taste timeline
- **Sync that survives restarts** — durable jobs with live phase / count / %; idle trickle for metadata, embeddings, neighbors, and title relations (circuit breaker)
- **Privacy-first MCP** — dual trust-plane keys over the same local index
- **Household optional** — **Sign in with Plex** (PIN), optional local password and/or OIDC; roles when multi-user is on
- **BYOP LLM** — OpenAI, Anthropic, Ollama, or any OpenAI-compatible endpoint; true SSE token streaming
- **Unraid-ready** — `romwil/curatorx:latest`, single `/config` volume, non-root container, Community Applications template

CuratorX complements disk tools like [Reclaimspace](https://github.com/romwil/reclaimspace): Reclaimspace quarantines duplicate files; CuratorX helps you decide *what* deserves the space.

---

## Quick start

### Docker Hub (recommended)

```bash
docker pull romwil/curatorx:latest
docker run -d --name curatorx \
  -p 8788:8788 \
  -v /path/to/curatorx/config:/config \
  romwil/curatorx:latest
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
### Windows (PowerShell)

WSL/bash is not required. One-shot setup: `.\scripts\setup-dev.ps1`. Or from the repo root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[web]"
cd frontend; npm install; npm run build; cd ..
$env:DATA_DIR = ".\config"
python -m curatorx.web
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
| [`romwil/curatorx:latest`](https://hub.docker.com/r/romwil/curatorx) | Everyday Unraid / Compose (CA template default) |
| [`romwil/curatorx:1.8`](https://hub.docker.com/r/romwil/curatorx) | Track the 1.8 line |
| [`romwil/curatorx:1.8.1`](https://hub.docker.com/r/romwil/curatorx) | Pin an exact release |

**Unraid:** install from Community Applications using the template (`templates/curatorx.xml` / `unraid/curatorx.xml`; CA icons at `unraid/curatorx-icon.png` / `unraid/curatorx-icon-512.png`), or add the container manually:

| Setting | Value |
|---------|-------|
| Repository | `romwil/curatorx:latest` |
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
| `features.multi_user_enabled` | `false` | Login + session cookies; owner vs member partitioning |
| `features.seerr_enabled` | `false` | Seerr discovery / request path for members |

Auth methods are opt-in: **Sign in with Plex** (PIN), **local password** (owner registration), and/or **OIDC** (Authelia, Authentik, Keycloak, etc.). The login page shows whatever is configured (`auth_methods` from `GET /api/features`). Plex token paste remains an advanced fallback.

Details: [Wiki → Multi-User](docs/wiki/Multi-User.md) · [Wiki → Seerr](docs/wiki/Seerr.md) · [CONFIGURATION.md](docs/CONFIGURATION.md)

---

## Documentation & wiki

| Doc | Description |
|-----|-------------|
| **[Wiki home](docs/wiki/Home.md)** | In-repo wiki index |
| [Privacy](docs/PRIVACY.md) | Data use (household + owner); in-app `/privacy` |
| [Security](docs/SECURITY.md) | Threat model and findings checklist |
| [FAQ](docs/FAQ.md) | Common questions |
| [Onboarding](docs/ONBOARDING.md) | First-run checklist |
| [Web UI](docs/WEB_UI.md) | Workspace layout and routes |
| [Architecture](docs/ARCHITECTURE.md) | System context and data flows |
| [Design](docs/DESIGN.md) | UX principles and agent tools |
| [Data model](docs/DATA_MODEL.md) | SQLite schema |
| [Configuration](docs/CONFIGURATION.md) | Env vars and settings |
| [Docker / Unraid](docs/DOCKER.md) | Container deployment |
| [Testing (e2e / CA)](docs/TESTING.md) | Playwright and CA release checklist |
| [Value-based testing](TESTING.md) | How to write logic-level backend tests |
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
