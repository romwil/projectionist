# About Projectionist

**Cinema intelligence for your personal archive.**

Projectionist is an open-source, self-hosted cinema intelligence engine and agentic companion for personal media libraries — local-first, zero-telemetry, with vector mapping, multi-signal taste modeling, MCP access, and hardened multi-tenant roles (Owner / Member / Youth / Guest). It indexes what you own, talks with a BYO LLM, only writes to Radarr/Sonarr/Seerr after you confirm, and can drive **Lobby Theater** wall kiosks (now playing + library-fed idle carousels) alongside **Live Channels** and the main cinema workspace.

## Why Projectionist?

Projectionist serves as a **real-world, production-quality example of an MCP (Model Context Protocol) interface** against structured and unstructured local data. It demonstrates a privacy-first pattern: the LLM operates over a highly optimized local SQLite index of your Plex library — your server token, watch history, and collection details never leave your hardware.

> "The LLM gets to act like a natural language surgeon on a highly optimized, predictable local dataset. It's incredibly fast, it's cheap, and it keeps your Plex token and personal collection server info locked down."

The dual-key MCP transport (privacy / full) shows how a single dataset can be exposed at different trust levels — sharing read-only library metadata externally while keeping *arr mutations and internal fields behind a separate boundary.

For the full MCP protocol surface and integration guide, see [MCP.md](MCP.md).

## Links

- **Help** — [HELP.md](HELP.md) (also in-app at `/help`)
- **Curator knowledge** — [CURATOR_KNOWLEDGE.md](CURATOR_KNOWLEDGE.md)
- **Privacy & data use** — [PRIVACY.md](PRIVACY.md) (also in-app at `/privacy`)
- **Security assessment** — [SECURITY.md](SECURITY.md)
- **Architecture** — [ARCHITECTURE.md](ARCHITECTURE.md)
- **MCP integration** — [MCP.md](MCP.md)
- **Changelog** — [../CHANGELOG.md](../CHANGELOG.md)

Primary About UI lives at `/about` in the app (AppNav + footer; not a top-bar icon). Help is at `/help`. This file is the short docs companion.
