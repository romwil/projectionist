# CuratorX FAQ

Common questions for CuratorX **1.0**. Also mirrored under [wiki/FAQ.md](wiki/FAQ.md).

## What is CuratorX?

A chat-first curation companion for self-hosted **Plex** libraries. It indexes what you own, recommends with explainable reasons, and only writes to Radarr/Sonarr after you confirm.

## Which Docker image should I use?

| Tag | When |
|-----|------|
| `romwil/curatorx:1.0` | Everyday Unraid / Compose |
| `romwil/curatorx:1.0.4` | Pin an exact release |
| `romwil/curatorx:latest` | Newest stable |

Images are multi-arch (**amd64 + arm64**). See [wiki/Installation.md](wiki/Installation.md).

## Where is my data stored?

Under `/config` (`DATA_DIR`):

| File | Contents |
|------|----------|
| `settings.json` | Connections, feature flags, onboarding |
| `curatorx.db` | Library index, chat, persona, lenses |
| `jobs_state.json` | Durable sync job history |

Back up the whole config directory before upgrades.

## Do I need an LLM API key?

For conversational curation, yes — or a reachable Ollama (or other OpenAI-compatible) endpoint. Library sync and setup work without an LLM; chat tools will not.

## Is multi-user / Seerr required?

No. Defaults are single-owner, no login, Seerr off. Enable only if you need household Plex sign-in or Seerr requests. See [wiki/Multi-User.md](wiki/Multi-User.md) and [wiki/Seerr.md](wiki/Seerr.md).

## Does CuratorX support OIDC or local passwords?

**Not in 1.0.** When multi-user is enabled, authentication is **Plex login** only.

## Will a sync survive a container restart?

Job **state** is persisted. An in-flight sync cannot resume mid-phase after restart; it is marked failed with *Interrupted by server restart — start sync again*. Start a new sync from Config.

## How do I watch sync progress?

Status dock (bottom-left of chat) and Config → Library sync card show phase, counts, and percent. Persona phrases are secondary and do not replace live progress.

## How is this different from Overseerr / Seerr?

CuratorX is a **taste-aware curator** (RAG, lenses, persona, purge advice, confirmation-gated *arr*). Seerr is an optional request front-end for members — it complements CuratorX; it does not replace the owner chat loop.

## Where should I look next?

- [wiki/Home.md](wiki/Home.md) — wiki index
- [ONBOARDING.md](ONBOARDING.md) — first-run wizard
- [TROUBLESHOOTING via wiki](wiki/Troubleshooting.md) — common failures
- [CHANGELOG.md](../CHANGELOG.md) — release notes
