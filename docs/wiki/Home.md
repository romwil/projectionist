# CuratorX wiki

In-repo documentation for operators deploying CuratorX **1.7** on Docker or Unraid.

## What CuratorX is

A cinema-dark chat curator for self-hosted Plex — and a **production-quality example of a privacy-first MCP (Model Context Protocol) interface** over local structured and unstructured data. CuratorX indexes your Plex library into a fast local SQLite store and exposes it to a BYO LLM via targeted MCP tool calls. Your Plex token, watch history, and collection details never leave your hardware.

Features: library-grounded recommendations, confirm-gated Radarr/Sonarr adds, ratings and watchlists, title detail / trailer / Watch on Plex, owner dashboard, optional household auth (Plex PIN, local password, OIDC), dual-key MCP transport (privacy / full trust), and a single `/config` Docker volume. See [MCP.md](../MCP.md) for the protocol surface.

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

## Related guides

- [../ONBOARDING.md](../ONBOARDING.md) — first-run wizard
- [../WEB_UI.md](../WEB_UI.md) — single workspace UI
- [../DOCKER.md](../DOCKER.md) — Mac / Compose / Unraid notes
- [../PRIVACY.md](../PRIVACY.md) — privacy & data use (household + owner)
- [../SECURITY.md](../SECURITY.md) — security assessment (S1–S13)
- [../TESTING.md](../TESTING.md) — CA release test checklist
- [../../CHANGELOG.md](../../CHANGELOG.md) — release notes
