# FAQ

Canonical FAQ for CuratorX 1.0. Same content as [`docs/FAQ.md`](../FAQ.md).

## What is CuratorX?

A chat-first curation companion for self-hosted **Plex** libraries. It indexes what you own, recommends with explainable reasons, and only writes to Radarr/Sonarr after you confirm.

## Is there still a dual UI (Turnstyle / Immersive)?

No. **1.0 is a single workspace**: sidebar conversations + full-width chat + status dock. An optional overlay can expand large title-card result sets.

## Which Docker image should I use?

- Unraid / everyday: `romwil/curatorx:1.0`
- Pin exact: `romwil/curatorx:1.0.12`
- Newest stable: `romwil/curatorx:latest`

Images are multi-arch (amd64 + arm64).

## Where is my data stored?

Under `/config` in the container (`DATA_DIR`):

- `settings.json` — connections and feature flags
- `curatorx.db` — library index, chat, persona, lenses
- `jobs_state.json` — durable sync job history

## Do I need an LLM API key?

For chat curation, yes (or a local Ollama endpoint). Without an LLM, setup and library sync still work; conversational tools will not.

## Is multi-user required?

No. Default is single-owner with no login. Enable `features.multi_user_enabled` only if you want household Plex sign-in.

## Does CuratorX support OIDC or local passwords?

Not in 1.0. Multi-user auth is **Plex login** only.

## Will a sync survive a container restart?

Job **state** is durable. An in-flight sync cannot resume mid-phase; it is marked failed with a clear message so you can start sync again.

## How is this different from Overseerr / Seerr?

CuratorX is a **taste-aware curator** over your library (RAG, lenses, persona, purge advice). Seerr is an optional request front-end you can enable for members — it does not replace CuratorX’s owner chat loop.
