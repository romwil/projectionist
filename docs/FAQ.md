# CuratorX FAQ

Common questions, answered with the concrete command or example you'd actually use. This is the canonical FAQ; [wiki/FAQ.md](wiki/FAQ.md) points here.

## What is CuratorX?

A chat-first + Explore curator for self-hosted **Plex** libraries — and a real-world example of **agentic access** to local structured + unstructured data via a privacy-first MCP interface. It indexes what you own into SQLite (credits, dates, plot layers, neighbors), lets a BYO LLM query that index with surgical tool calls, recommends with explainable reasons, and only writes to Radarr/Sonarr after you confirm. Your Plex token and collection details never leave your hardware.

**Try it in one line** once you're set up: ask *"What should we watch tonight, under two hours, that I haven't seen?"* — you get a shortlist from *your* shelves, each with a reason. See [MCP.md](MCP.md).

## Which Docker image should I use?

| Tag | When |
|-----|------|
| `romwil/curatorx:latest` | Everyday Unraid / Compose (CA template default) |
| `romwil/curatorx:<MAJOR.MINOR>` | Track a minor line (e.g. the current `1.13` line) |
| `romwil/curatorx:<X.Y.Z>` | Pin an exact release (see [CHANGELOG.md](../CHANGELOG.md) for versions) |

```bash
docker pull romwil/curatorx:latest        # everyday
docker pull romwil/curatorx:1.13           # track the minor line
docker pull romwil/curatorx:1.13.0         # pin an exact release
```

Images are multi-arch (**amd64 + arm64**), run as non-root `curatorx` (UID/GID 1000). See [wiki/Installation.md](wiki/Installation.md).

## Unraid Force Update pulled 0 B and I'm still on an old version

Force Update calls Docker Engine pull, then recreates the container. **0 B** means Engine kept the existing local `romwil/curatorx:latest` mapping while Hub may already have a newer digest. Dockerfile labels / `.build-info` don't bypass that. Fix (config stays under `/mnt/user/appdata/curatorx/config`):

```bash
cd /mnt/user/appdata/curatorx && ./rollout.sh latest
# or: docker pull romwil/curatorx:latest   # then Force Update / Apply
# or: ./scripts/unraid-force-pull.sh latest --rmi-retry
```

Verify what you're actually running:

```bash
docker exec curatorx cat /app/.build-info
```

Details: [DOCKER.md](DOCKER.md#unraid-force-update-pulls-0-b--stays-on-an-old-version).

## Where is my data stored?

Everything lives under `/config` (`DATA_DIR`) on the owner's disk:

| File | Contents |
|------|----------|
| `settings.json` | Connections, feature flags, onboarding |
| `curatorx.db` | Library index, chat, persona, checkpoints |
| `jobs_state.json` | Durable sync job history |

Back up the whole directory before major changes:

```bash
tar czf curatorx-config-$(date +%F).tgz -C /mnt/user/appdata/curatorx config
```

## Do I need an LLM API key?

For conversational curation, yes — or a reachable **Ollama** (or other OpenAI-compatible) endpoint. Library sync and setup work without an LLM; chat tools won't. For a fully local, nothing-leaves-the-LAN setup:

```dotenv
# .env
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL=llama3.1
# no key needed for local Ollama
```

## Is multi-user / Seerr required?

No. Defaults are **single-owner, no login, Seerr off**. Enable them only if you need household sign-in or Seerr requests. See [wiki/Multi-User.md](wiki/Multi-User.md) and [wiki/Seerr.md](wiki/Seerr.md).

## How do I enable household sign-in?

Turn on multi-user in **Admin**, then enable the sign-in methods you want. Members appear after they sign in — there's no email invite flow.

- **Sign in with Plex** — Overseerr-style plex.tv PIN / link flow (most common)
- **Local password** — owner-registered accounts (PBKDF2)
- **OIDC** — Authelia, Authentik, Keycloak, or another OIDC IdP

Pasting a Plex token on `/login` is an advanced fallback only. The **Plex server token** in Config is separate — it's for library sync, not household login. Full walkthrough: [wiki/Multi-User.md](wiki/Multi-User.md).

## Will a sync survive a container restart?

Yes. Sync **state** is persisted; an in-flight job is marked failed with *"Interrupted by server restart — start sync again."* Starting again resumes from the last **phase checkpoint** while it's still valid (≤72h), so finished phases aren't redone and unchanged titles skip re-embedding. See [wiki/Library-Sync.md](wiki/Library-Sync.md).

## How do I watch sync progress?

The **status dock** (bottom of the conversation sidebar) and **Settings → Library sync** show phase, counts, and percent live. Or poll it:

```bash
curl -s http://localhost:8788/api/library/stats | python3 -m json.tool
```

## Where is About / Privacy / Help?

Footer links on every layout (**Help · Privacy · About**), plus the hamburger AppNav and user menu. About is **not** a top-bar icon — use the menu or footer.

## What is Explore?

The top-bar cinema icon opens `/explore`: browse rails (Recently Added, Recent Releases, On This Day, Revisit These, Plot Lab) that read the same SQLite feeds as the curator, plus a hero search across titles and plot summaries. Chat remains the primary curation loop; Explore is for cinema browsing. Full tour: in-app [Help](/help).

## Why is "More Like This" / Plot Lab empty?

Neighbors and motifs are **materialized by idle scheduler tasks** after sync (`plot_neighbors`, `summary_motifs`, `title_relations_refresh`). Empty means the cache hasn't been built yet — not that your library has no similar titles. Leave the container idle after a sync, then confirm the tasks are enabled in **Admin → Scheduled Tasks** (`/admin/tasks`). Check coverage directly:

```bash
curl -s http://localhost:8788/api/library/knowledge-coverage | python3 -m json.tool
```

## Why doesn't Plot Lab find a title I know matches those motifs?

Motif chips are a **small lexical extract** from short Plex/TMDB blurbs (up to eight uncommon unigrams per title). A pure **Motifs only** AND wall needs every selected chip present as a facet, so intersections can miss titles even when the free text or TMDB keywords already contain the idea. Switch to **Multi-signal** mode and the same selection also matches via keyword and plot text. Worked case study (Kill Bill, `bride` ∩ `coma`): [CURATOR_KNOWLEDGE.md](CURATOR_KNOWLEDGE.md#case-study-kill-bill--bride--coma).

## How do idle tasks deepen library knowledge?

After sync, the idle scheduler trickles metadata, embeddings, motifs, and neighbor edges so Chat/Explore stay fast. Owners tune cadence in **Admin → Scheduled Tasks**. Coverage climbs over hours/days on large libraries; neighbor edges often lag embeddings. Full why/what/how: [CURATOR_KNOWLEDGE.md](CURATOR_KNOWLEDGE.md#idle-tasks--purpose-trickle-auto-tune).

## Lights Up vs Lights Down?

**Lights Down** is the cinema chamber (default). **Lights Up** is gallery paper. **Match system** follows your OS preference. Cycle from the top-bar icon or **Settings → Profile**.

## How is this different from Overseerr / Seerr?

CuratorX is a **taste-aware curator** (RAG, persona, ratings, purge advice, confirmation-gated *arr, owner dashboard). Seerr is an optional request front-end for members — it complements CuratorX; it doesn't replace the owner chat loop.

## Can I export or delete everything CuratorX knows about me?

Yes. Every account can export a full copy of its own data or permanently purge it — **the same set either way**: your private notes, chat threads + message transcripts, saved library pages, and preference facts.

```bash
# Export your account data (as the signed-in user)
curl -s http://localhost:8788/api/me/memory > my-curatorx-export.json
# Permanently delete the same set (export first — this is irreversible)
curl -s -X DELETE http://localhost:8788/api/me/memory
```

Shared, sanitized media research isn't tied to your account and isn't part of a purge. The exact map is on the [Privacy](/privacy) page.

## Where is the privacy policy?

In-app at **`/privacy`** (no login), and the same document in [PRIVACY.md](PRIVACY.md). It covers household vs owner data, the export/purge map, MCP exposure, voice, and watchlist token use.

## What are the two MCP API keys?

| Env / Admin → Advanced | Mode |
|------------------------|------|
| `CURATORX_MCP_API_KEY` | **Privacy** — public content schema, read-only library tools |
| `CURATORX_MCP_FULL_API_KEY` | **Full** — internal library fields + confirm-gated *arr propose tools |

The two keys must differ. Either (or both) enables HTTP `/mcp`. Generate/rotate in **Admin → Advanced**, or set the env vars:

```bash
docker run -d --name curatorx -p 8788:8788 \
  -v /path/to/curatorx/config:/config \
  -e CURATORX_MCP_API_KEY="a-long-random-privacy-key" \
  romwil/curatorx:latest
```

See [MCP.md](MCP.md) and [.env.example](../.env.example).

## How does Plex watchlist sync work?

Local watchlist pins can sync with Plex Discover when you enable sync in **Settings**. A refresh **pulls from Plex** then lists your local pins. CuratorX stores an **encrypted** copy of your Sign-in-with-Plex account token for that purpose only — never the server library token as a stand-in. Re-sign in if the token goes missing. Details: [PRIVACY.md](PRIVACY.md).

## Can CuratorX publish named lists to Plex Lists?

**Not yet.** CuratorX supports **local** named curated lists (Settings → Lists, plus chat tools `list_lists` / `create_list` / `add_to_list` / `remove_from_list`). A 2026 spike found **no clear public/stable API** for Plex Discover personal Lists: official PMS docs cover Playlists/Collections, and Discover documents Watchlist add/remove only. Publish-to-Plex-Lists is deferred so we never fake a broken sync. Watchlist ↔ Discover sync remains separate and available.

## What's the difference between a list, playlist, and watchlist?

A **watchlist** is a personal reminder that can sync with Plex Discover. A CuratorX **list** is a durable named shelf ("70s paranoia"); a **playlist** uses the same local storage to signal a planned viewing sequence ("Friday double feature"). Adding or removing a collection membership never deletes a library title, and CuratorX doesn't publish local playlists to Plex today.

## Can I export a filtered library view?

Yes, from the browse controls on library-query walls. Export uses the same filters and sort direction as the view, caps the result, and accepts only a safe column allowlist (title, year, type, genres, runtime, rating, watch state, counts/dates, public IDs). It's intentionally **not** an unrestricted database dump — paths, Plex credentials, and internal operational fields are excluded. Feed and collection walls don't claim to export when their source can't faithfully reproduce a library query.

## What happens when I report bad video, audio, or metadata?

The report is saved in an **owner queue** (`Admin → Issues`) with the title identity, problem type, and optional note. Members can report but **never** directly command Radarr/Sonarr or delete a file. An owner can reject, resolve, or run a supported, logged repair — which may safely skip if the title isn't managed, is ambiguous, or is unsupported. CuratorX won't blindly delete files, "fix" a metadata match, or promise a subtitle/download result.

## Where should I look next?

- [HELP.md](HELP.md) / in-app `/help` — role-aware product help
- [ONBOARDING.md](ONBOARDING.md) — first-run setup, step by step
- [CURATOR_KNOWLEDGE.md](CURATOR_KNOWLEDGE.md) — library knowledge depth
- [PRIVACY.md](PRIVACY.md) / in-app `/privacy` — data use + export/purge map
- [MCP.md](MCP.md) — dual-mode MCP keys and tools
- [DESIGN.md](DESIGN.md) — UX layout, cards, dashboard, personas
- [wiki/Home.md](wiki/Home.md) — wiki index
- [wiki/Troubleshooting.md](wiki/Troubleshooting.md) — common failures
- [CHANGELOG.md](../CHANGELOG.md) — release notes
