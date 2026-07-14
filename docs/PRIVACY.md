# Privacy & data use

This page explains what CuratorX stores, who can see it, and what leaves your machine. It is written for people who use the app — not only for operators reading the [security assessment](SECURITY.md).

CuratorX is a **self-hosted** app. The server owner chooses where it runs, which LLM provider to use, and whether to enable household login or MCP. There is no CuratorX cloud account that receives your library by default.

Jump to: [Household members](#household-members) · [Server owners](#server-owners) · [MCP](#mcp) · [Exposure matrices](#exposure-matrices) · [We do not](#we-do-not)

---

## Who this is for

| Role | How you arrive | What you administer |
|------|----------------|---------------------|
| **Server owner** | First Plex sign-in when multi-user is on, or the single operator when multi-user is off | Connections, libraries, sync, persona, household users, MCP keys, fleet credentials |
| **Household member** | Later **Sign in with Plex** after multi-user is enabled | Your own profile preferences, chats, watchlist, ratings — not the server |

Default install is **single-owner with no login**: anyone on the trusted network who can reach the UI is effectively an admin. Multi-user adds Sign in with Plex and separates personal data; it is still a household product on a LAN, not a multi-tenant SaaS.

---

## From the household member’s perspective

### What you share when you sign in

When you use **Sign in with Plex**, CuratorX asks Plex who you are and stores a household user profile:

- Plex display name
- Optional email and avatar URL (if Plex provides them)
- Plex user id (for identity, not shown as a “shareable” library field)
- Role (`owner` or `member`)
- Optional Seerr link (user id / permissions) when the owner has Seerr enabled and linking succeeds

There is no email invite flow. You appear after a successful Plex sign-in.

### What is yours alone (multi-user on)

When multi-user is enabled, these stay scoped to your user:

- Chat threads and messages
- Pending confirm tokens for *arr / Seerr actions you started
- Watchlist pins
- Ratings and review prompts tied to you
- Preference / taste facts the curator keeps for you
- **Preferred conversation name** — how the curator addresses you in chat (may differ from your Plex display name)
- Voice toggles (listen / speak replies), when voice mode is available

Other household members cannot open your chats or confirm your pending actions through the normal multi-user API boundary.

### What is shared household

Everyone on the same CuratorX instance shares:

- The indexed library catalog (titles, metadata, facets, embeddings)
- Sync jobs and library health
- Curator persona voice (name, tone, presets) configured by the owner
- In-app browsing of what the household owns (members may see a **public content** view of titles — more on posters and identifiers below)

### What the LLM provider receives

Chat uses the **owner’s configured LLM** (OpenAI, Anthropic, Ollama, OpenRouter, etc.). The model receives:

- Your prompts and conversation context
- Tool results the agent needs (title metadata, library matches, watch signals the tools return)

It should **not** receive Plex server tokens, live `X-Plex-Token` media URLs, webhook secrets, or settings dumps. Your chat content goes to whichever provider the owner configured — including a local Ollama if they chose one.

### Voice mode

If you enable voice input:

- The **browser / OS speech service** may process microphone audio (some browsers use a cloud speech-to-text service).
- CuratorX does **not** upload raw audio to its own servers and does **not** store raw audio on disk.
- Transcripts become normal chat text and then follow the usual chat → LLM path.
- Optional “speak replies” uses the browser’s `speechSynthesis` for assistant text.

### Preferred name

You can set a **preferred conversation name** on your profile. CuratorX stores it on your user record and uses it when addressing you. Fallback: Plex display name, then a neutral greeting.

### Watchlist and Plex account token (planned / when enabled)

Local watchlist pins are yours. When watchlist ↔ Plex Discover sync is enabled:

- CuratorX may store an **encrypted** copy of your Plex account token from Sign in with Plex (`plex_token_enc`) solely to pull/push your Discover watchlist (and related account features such as Seerr linking).
- That token is **not** returned by API responses, MCP tools, or the UI.
- If the token is missing, sync asks you to re-sign in — it does not fall back to exposing the server library token as “your” account token.

### Curated lists

Named lists you create in CuratorX (for example “Friday picks”) are stored locally and owned by your user. Visibility may be private, household, or link-based inside CuratorX. Publishing to **Plex Lists** (when supported) uses your encrypted account token; CuratorX will not pretend a Plex publish succeeded if the API is unavailable.

### What other members cannot see

- Your chat history and message feedback
- Your pending *arr / Seerr confirmation tokens
- Your watchlist and personal ratings (as personal records)
- Owner-only Admin: fleet URLs, API keys, MCP keys, household user management

### MCP and members

Household members do **not** control MCP API keys. The owner may expose library *content* to external apps via MCP; see [MCP](#mcp). That path is about titles and inventory — not your private chats.

---

## From the server owner’s perspective

### Fleet credentials

Stored under the app data directory (typically `/config` → `settings.json` and related files):

- Plex server URL and **server** token
- Radarr / Sonarr / Seerr / TMDB / TVDB / Fanart / Tautulli keys as configured
- LLM provider base URL, model, and API key
- Webhook secret, session secret material, feature flags

**Who can view them in the UI:** owner Admin / Configuration only (not household members). Treat the Docker `/config` volume and backups as secret material — keys are not encrypted at rest on disk today.

### MCP keys

CuratorX supports two trust planes (selected by which secret is presented — never by a client “mode” flag alone):

| Key | Typical env | Purpose |
|-----|-------------|---------|
| Privacy MCP key | `CURATORX_MCP_API_KEY` | Read-oriented library intelligence with a **public content** schema |
| Full / in-stack MCP key | `CURATORX_MCP_FULL_API_KEY` | Deeper internal library fields + confirm-gated *arr propose tools for trusted automation on your LAN |

Details and exposure: [MCP](#mcp). Rotate keys in Admin → Advanced when available. Do not reuse the same string for both keys.

### Images (TMDB posters)

For privacy-safe and member-facing library JSON, CuratorX prefers **TMDB CDN** poster/backdrop URLs (`image.tmdb.org`). Those URLs carry no Plex token and no LAN hostname. Plex thumbnail URLs that embed `X-Plex-Token` must not leave via privacy MCP or member public schemas.

### Webhooks, logging, backups

- Plex webhooks (if enabled) require a configured webhook secret.
- Application logs may include titles, job phases, and user ids — not raw API keys by design — but still treat log volume access as sensitive.
- Backups of `/config` include credentials; store them like password vaults.

### Network expectations

Do **not** expose bare port `8788` to the public internet. Keep CuratorX on a trusted LAN or behind an authenticated reverse proxy. See [SECURITY.md](SECURITY.md) for the operator threat model and finding checklist.

---

## MCP (Model Context Protocol)

MCP lets external tools query your **indexed library**. Mode is determined by the API key (HTTP) or explicit stdio mode settings — not by the client asserting a privilege level.

### Privacy mode (default for sharing)

- **Tools:** read-only library intelligence (query, facets, watch suggestions, etc.).
- **Schema:** public content — titles, years, genres, cast, truncated overviews, `tmdb_id` / `tvdb_id`, optional coarse watch state, **TMDB** image URLs when available.
- **Must not include:** Plex/LAN/`X-Plex-Token` media URLs, `rating_key`, machine identifiers, household user identity, email/avatar, file sizes in bytes, raw view timestamps, `in_radarr` / `in_sonarr`, absolute paths, secrets, or *arr write tools.

### Full / in-stack mode (trusted LAN automation)

- **Tools:** privacy read tools with richer **internal** fields, plus confirm-gated propose tools for Radarr/Sonarr (and optional Seerr) that return a pending token — no silent writes.
- **Still must not include:** live `X-Plex-Token` in any URL or field; webhook / session / LLM / *arr API keys; dumps of `settings.json`.
- Prefer TMDB CDN images even in full mode.

Stdio transport for full mode is intentionally guarded so a shared laptop cannot accidentally speak full mode without the full key present in the environment.

Operator guide: [MCP.md](MCP.md). Threat-model notes: [SECURITY.md](SECURITY.md).

---

## Exposure matrices

Legend: **Y** = may see / receive · **—** = not exposed by design · **P** = planned / when feature enabled · **\*** = owner-configured destination

### By audience

| Data class | Stored where | Member | Owner | Privacy MCP | Full MCP | LLM (chat tools) |
|------------|--------------|--------|-------|-------------|----------|------------------|
| Title metadata (name, year, genres, cast) | SQLite library index | Y | Y | Y | Y | Y |
| Truncated overview / public facets | SQLite | Y | Y | Y | Y | Y |
| TMDB poster / backdrop CDN URLs | Derived / TMDB | Y | Y | Y | Y | Y |
| Plex tokenized poster URLs | May exist in DB | — | In-app only | — | — | — |
| `tmdb_id` / `tvdb_id` | SQLite | Y | Y | Y | Y | Y |
| Plex `rating_key` | SQLite | — | Y | — | Y | Y (agent/internal) |
| File size / paths | SQLite | — | Y | — | Y (size; not secrets) | Sometimes (internal tools) |
| `in_radarr` / `in_sonarr` | SQLite | — | Y | — | Y | Y (agent) |
| Watch telemetry (detailed) | SQLite | Own signals in UI | Y | — | Y | Y (agent tools) |
| Chat messages | SQLite | Own | Own + admin host access | — | — | Y\* (provider) |
| Watchlist pins | SQLite | Own | Own | Snapshot tool may list pins (no account token) | Same | Y (agent tools) |
| Ratings / reviews | SQLite | Own | Own | — | — | Y (agent tools) |
| Preferred name | User row | Own | Household user admin | — | — | Y (addressing) |
| Plex display name / avatar | User row | Own (profile) | Household table | — | — | Minimal (addressing) |
| Encrypted Plex account token | User row (`plex_token_enc`) | — (P) | — (not via API) | — | — | — |
| Curated lists | SQLite | Own / household per visibility | Same + host | — | — | Y (agent tools) |
| Plex server URL + server token | `settings.json` | — | Admin | — | — | — |
| *arr / Seerr / LLM API keys | `settings.json` | — | Admin | — | — | — (key itself) |
| MCP privacy / full keys | Env / settings | — | Admin | Auth only | Auth only | — |
| Persona configuration | SQLite / settings | Shared voice in chat | Admin edit | — | — | Y (system prompt) |

### Voice path (members)

| Step | Who processes it | Stored by CuratorX |
|------|------------------|--------------------|
| Microphone audio | Browser / OS speech service | No raw audio |
| Transcript text | CuratorX chat + LLM\* | As chat messages |
| Spoken replies | Browser `speechSynthesis` | Not stored as audio |

---

## We do not

- Sell your household data or train a CuratorX-hosted foundation model on your chats
- Require a CuratorX cloud account for core library curation
- Expose live `X-Plex-Token` media URLs through privacy MCP or member public library JSON
- Let privacy MCP (or a mode flag) escalate into full / write-capable MCP
- Hand MCP clients your Plex server token, LLM key, or `settings.json`
- Store raw microphone audio on the CuratorX data volume (voice transcripts only)
- Email household invites or scrape contacts from Plex beyond the signed-in profile fields above
- Pretend Plex Lists publish succeeded when the Discover API path is unavailable

---

## Your choices

- Keep **multi-user off** for a single trusted operator on a private network
- Turn **multi-user on** so chats, watchlists, and ratings partition per Plex identity
- **Do not enable** full MCP (or leave `CURATORX_MCP_FULL_API_KEY` unset) if you only want the privacy schema
- **Rotate** MCP keys if a client or paste leaked
- Choose an **LLM provider** you trust (including fully local Ollama)
- Leave the household by asking the owner to disable or remove your user (when user management is available)
- Read the technical checklist: [SECURITY.md](SECURITY.md)

---

## Related docs

- [SECURITY.md](SECURITY.md) — operator threat model and findings
- [MCP.md](MCP.md) — MCP tools, keys, and transport
- [wiki/Multi-User.md](wiki/Multi-User.md) — Sign in with Plex
- In-app copy of this page: **`/privacy`** (no login required)
