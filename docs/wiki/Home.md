# CuratorX wiki

In-repo documentation for operators deploying CuratorX **1.8** on Docker or Unraid.

## What CuratorX is

An **agentic curator** for self-hosted Plex — chat, Explore browse, and a **privacy-first MCP interface** over local structured + unstructured data. CuratorX indexes your library into SQLite (credits, dates, facets, layered plot text, materialized neighbors/relations) and exposes surgical tool calls to a BYO LLM. Your Plex token, watch history, and collection details never leave your hardware.

Features: library-grounded recommendations, Explore feeds, title detail with neighbors, confirm-gated Radarr/Sonarr adds, ratings and watchlists, Lights Up/Down themes, owner dashboard, optional household auth (Plex PIN, local password, OIDC), dual-key MCP transport, and a single `/config` Docker volume. See [MCP.md](../MCP.md) and [ARCHITECTURE.md](../ARCHITECTURE.md).

## Pages

| Page | Topic |
|------|-------|
| [Home](Home.md) | What CuratorX is and how to navigate docs |
| [Installation](Installation.md) | Docker Hub, Compose, local build |
| [Unraid](Unraid.md) | Community Applications / template install |
| [Configuration](Configuration.md) | Settings, env vars, feature flags |
| [Library Sync](Library-Sync.md) | Indexing Plex, progress, checkpoints / resume |
| [Multi-User](Multi-User.md) | Optional household auth (Plex / local / OIDC) |
| [Seerr](Seerr.md) | Optional Seerr requests for members |
| [Troubleshooting](Troubleshooting.md) | Common failures and fixes |
| [FAQ](FAQ.md) | Short answers (mirrors [`../FAQ.md`](../FAQ.md)) |
| [Privacy](../PRIVACY.md) | What data CuratorX stores and who can see it (also `/privacy` in the UI) |
| [Security](../SECURITY.md) | Threat model + living findings checklist (pen-test brief) |
| [Penetration tests](../security/pentests/README.md) | Repeatable Protocol v1.0 + engagement archives |

## Related guides

- [../ONBOARDING.md](../ONBOARDING.md) — first-run wizard
- [../WEB_UI.md](../WEB_UI.md) — single workspace UI
- [../DOCKER.md](../DOCKER.md) — Mac / Compose / Unraid notes
- [../PRIVACY.md](../PRIVACY.md) — privacy & data use (household + owner)
- [../SECURITY.md](../SECURITY.md) — security assessment (S1–S15)
- [../security/pentests/README.md](../security/pentests/README.md) — penetration-test protocol v1.0
- [../TESTING.md](../TESTING.md) — CA release test checklist
- [../../CHANGELOG.md](../../CHANGELOG.md) — release notes
