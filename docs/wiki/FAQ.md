# FAQ

Canonical FAQ for CuratorX **1.8**. Same content as [`docs/FAQ.md`](../FAQ.md).

## What is CuratorX?

A chat-first + Explore curator for self-hosted **Plex** libraries — and a real-world example of **agentic access** to local structured + unstructured data via a privacy-first MCP interface. It indexes what you own into SQLite (credits, dates, plot layers, neighbors), lets a BYO LLM query that index with surgical tool calls, recommends with explainable reasons, and only writes to Radarr/Sonarr after you confirm. Your Plex token and collection details never leave your hardware. See [MCP.md](../MCP.md).

## Is there still a dual UI (Turnstyle / Immersive)?

No. CuratorX is a **single workspace**: sidebar conversations + full-width chat + status dock, with turnstyle / poster cards inside the chat stream, plus an **Explore** hub (`/explore`) for cinema browse. An optional overlay can expand large title-card result sets. Privacy / About live in the page footer (not the top bar).

## Which Docker image should I use?

- Unraid / everyday: `romwil/curatorx:latest` (CA template default)
- Track the line: `romwil/curatorx:1.8`
- Pin exact: `romwil/curatorx:1.8.5`

Images are multi-arch (amd64 + arm64) and run as non-root.

## Where is my data stored?

Under `/config` in the container (`DATA_DIR`):

- `settings.json` — connections and feature flags
- `curatorx.db` — library index, chat, persona, lenses, checkpoints
- `jobs_state.json` — durable sync job history

## Do I need an LLM API key?

For chat curation, yes (or a local Ollama endpoint). Without an LLM, setup and library sync still work; conversational tools will not.

## Is multi-user required?

No. Default is single-owner with no login. Enable `features.multi_user_enabled` only if you want household sign-in (Plex PIN, local password, and/or OIDC).

## How do household users sign in?

The login page shows configured methods: **Sign in with Plex** (PIN), optional **local password**, and/or **OIDC**. Token paste on `/login` is an advanced fallback only. The Plex **server token** in Config is for library sync, not login.

## Does CuratorX support OIDC or local passwords?

Yes (opt-in alongside or instead of Plex PIN). See [CONFIGURATION.md](../CONFIGURATION.md) and [Multi-User](Multi-User.md).

## Will a sync survive a container restart?

Job **state** is durable; an interrupted job is marked failed so you can start sync again. A new sync resumes from the last valid **phase checkpoint** (≤72h) instead of redoing finished phases.

## How is this different from Overseerr / Seerr?

CuratorX is a **taste-aware curator** over your library (RAG, persona, ratings, purge advice, owner dashboard). Seerr is an optional request front-end you can enable for members — it does not replace CuratorX’s owner chat loop.

## What is Explore?

Top-bar cinema icon → `/explore`. Browse rails read the same SQLite feeds as the agent. Chat stays the primary curation loop.

## Why is “More Like This” empty?

Idle tasks materialize `item_neighbors` after sync. Empty = cache not built yet. See [Library Sync](Library-Sync.md).

## Lights Up vs Lights Down?

Theme toggle in the top bar or Settings → Profile. Lights Down = cinema chamber; Lights Up = gallery paper; Match system follows the OS.

## Where is the privacy policy?

In-app at **`/privacy`** (no login), and [PRIVACY.md](../PRIVACY.md).

## What are the two MCP API keys?

- `CURATORX_MCP_API_KEY` — privacy (public schema, read-only)
- `CURATORX_MCP_FULL_API_KEY` — full (internal fields + confirm-gated *arr proposes; must differ)

Generate in Admin → Advanced or set env vars. Details: [MCP.md](../MCP.md).

## How does Plex watchlist sync work?

Optional Discover sync uses an encrypted Sign-in-with-Plex account token (not the server library token). Refresh pulls from Plex, then lists local pins. Re-sign in if sync asks. See [PRIVACY.md](../PRIVACY.md).

## Can CuratorX publish named lists to Plex Lists?

**Not yet.** Local named lists ship under Settings → Lists (and chat tools). A spike found no clear public/stable API for Plex Discover personal Lists, so publish is deferred. Watchlist ↔ Discover sync is separate.
