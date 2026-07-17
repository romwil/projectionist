# CuratorX FAQ

Common questions for CuratorX **1.8**. Also mirrored under [wiki/FAQ.md](wiki/FAQ.md).

## What is CuratorX?

A chat-first + Explore curator for self-hosted **Plex** libraries — and a real-world example of **agentic access** to local structured + unstructured data via a privacy-first MCP interface. It indexes what you own into SQLite (credits, dates, plot layers, neighbors), lets a BYO LLM query that index with surgical tool calls, recommends with explainable reasons, and only writes to Radarr/Sonarr after you confirm. Your Plex token and collection details never leave your hardware. See [MCP.md](MCP.md).

## Which Docker image should I use?

| Tag | When |
|-----|------|
| `romwil/curatorx:latest` | Everyday Unraid / Compose (CA template default) |
| `romwil/curatorx:1.8` | Track the 1.8 line |
| `romwil/curatorx:1.8.4` | Pin an exact release |

Images are multi-arch (**amd64 + arm64**), run as non-root `curatorx` (UID/GID 1000). See [wiki/Installation.md](wiki/Installation.md).

## Where is my data stored?

Under `/config` (`DATA_DIR`):

| File | Contents |
|------|----------|
| `settings.json` | Connections, feature flags, onboarding |
| `curatorx.db` | Library index, chat, persona, lenses, checkpoints |
| `jobs_state.json` | Durable sync job history |

Back up the whole config directory before major changes.

## Do I need an LLM API key?

For conversational curation, yes — or a reachable Ollama (or other OpenAI-compatible) endpoint. Library sync and setup work without an LLM; chat tools will not.

## Is multi-user / Seerr required?

No. Defaults are single-owner, no login, Seerr off. Enable only if you need household sign-in or Seerr requests. See [wiki/Multi-User.md](wiki/Multi-User.md) and [wiki/Seerr.md](wiki/Seerr.md).

## How do household users sign in?

When multi-user is on, the login page shows whichever methods you enabled:

- **Sign in with Plex** — Overseerr-style plex.tv PIN / link flow (most common)
- **Local password** — owner-registered accounts (PBKDF2)
- **OIDC** — Authelia, Authentik, Keycloak, or other OIDC IdPs

Pasting a Plex token on `/login` is an advanced fallback only. The **Plex server token** in Config is separate: it is for library sync, not household login.

## Does CuratorX support OIDC or local passwords?

Yes (opt-in). Enable `features.multi_user_enabled`, then configure `auth.plex_login_enabled`, `auth.local_login_enabled`, and/or `auth.oidc_enabled` in Admin / `settings.json`. See [CONFIGURATION.md](CONFIGURATION.md).

## Will a sync survive a container restart?

Job **state** is persisted; an in-flight job is marked failed with *Interrupted by server restart — start sync again*. Starting sync again resumes from the last **phase checkpoint** when still valid (≤72h), so finished phases are not redone. Unchanged titles also skip re-embedding. See [wiki/Library-Sync.md](wiki/Library-Sync.md).

## How do I watch sync progress?

Status dock (**bottom of the conversation sidebar**) and Settings → Library sync show phase, counts, and percent. Persona phrases are secondary and do not replace live progress.

## Where is About / Privacy?

Subtle footer links on every layout, plus Settings. About is **not** in the top navigation bar.

## What is Explore?

Top-bar cinema icon → `/explore`. Browse rails (Recently Added, Recent Releases, On This Day, Plot Lab) read the same SQLite feeds as the agent. Chat remains the primary curation loop; Explore is cinema browse.

## Why is “More Like This” / Plot Lab empty?

Neighbors and motifs are **materialized by idle scheduler tasks** after sync (`plot_neighbors`, `summary_motifs`, `title_relations_refresh`). Empty means the cache has not been built yet — not that your library has no similar titles. Leave the container idle after a sync, or check Admin → scheduled tasks.

## Lights Up vs Lights Down?

**Lights Down** is the cinema chamber (default). **Lights Up** is gallery paper. **Match system** follows OS preference. Cycle from the top-bar icon or Settings → Profile.

## How is this different from Overseerr / Seerr?

CuratorX is a **taste-aware curator** (RAG, persona, ratings, purge advice, confirmation-gated *arr*, owner dashboard). Seerr is an optional request front-end for members — it complements CuratorX; it does not replace the owner chat loop.

## Where is the privacy policy?

In-app at **`/privacy`** (no login), and the same document in [PRIVACY.md](PRIVACY.md). It covers household vs owner data, MCP exposure, voice, and watchlist token use.

## What are the two MCP API keys?

| Env / Admin → Advanced | Mode |
|------------------------|------|
| `CURATORX_MCP_API_KEY` | **Privacy** — public content schema, read-only library tools |
| `CURATORX_MCP_FULL_API_KEY` | **Full** — internal library fields + confirm-gated *arr propose tools |

Keys must differ. Either (or both) enables HTTP `/mcp`. Generate/rotate in **Admin → Advanced**, or set env vars (see [MCP.md](MCP.md) and [.env.example](../.env.example)).

## How does Plex watchlist sync work?

Local watchlist pins can sync with Plex Discover when you enable sync in Settings. Refresh **pulls from Plex** then lists local pins. CuratorX stores an **encrypted** copy of your Sign-in-with-Plex account token for that purpose only — never the server library token as a stand-in. Re-sign in if the token is missing. See [PRIVACY.md](PRIVACY.md).

## Can CuratorX publish named lists to Plex Lists?

**Not yet.** CuratorX supports **local** named curated lists (Settings → Lists, plus chat tools `list_lists` / `create_list` / `add_to_list` / `remove_from_list`). A 2026 spike found **no clear public/stable API** for Plex Discover personal Lists (`watch.plex.tv/watchlist/my-lists`): official PMS docs cover Playlists/Collections, and Discover documents Watchlist add/remove only. Publish-to-Plex-Lists is deferred so we never fake a broken sync. Watchlist ↔ Discover sync remains separate and available.

## Where should I look next?

- [wiki/Home.md](wiki/Home.md) — wiki index
- [PRIVACY.md](PRIVACY.md) / in-app `/privacy` — data use
- [MCP.md](MCP.md) — dual-mode MCP keys and tools
- [DESIGN.md](DESIGN.md) — UX layout, cards, dashboard, personas
- [ONBOARDING.md](ONBOARDING.md) — first-run wizard
- [TROUBLESHOOTING via wiki](wiki/Troubleshooting.md) — common failures
- [CHANGELOG.md](../CHANGELOG.md) — release notes
