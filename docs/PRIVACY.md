# Privacy & data use

This page explains what Projectionist stores, who can see it, and what leaves your machine. It's written for the people who use the app — not only for operators reading the [security assessment](SECURITY.md).

Projectionist is a **self-hosted** app. The server owner chooses where it runs, which LLM provider to use, and whether to enable household login or MCP. **There is no Projectionist cloud account that receives your library by default.**

The short version:

- **What we store** — your indexed library, your chats and preferences, and (for the owner) the connection credentials. All in one local SQLite database and `settings.json` on the owner's disk.
- **What leaves the box** — only what you send to the LLM provider the owner configured (your prompts + the tool results needed to answer), and TMDB image URLs. Not your Plex token, not your `settings.json`.
- **How to export or purge** — every account can download a full copy of its own data or permanently delete it. Exactly what that covers is mapped below, under **What export and purge cover**.

Jump to: [Household members](#household-members) · [Server owners](#server-owners) · [MCP](#mcp) · [Exposure matrices](#exposure-matrices) · [We do not](#we-do-not)

---

## Who this is for

| Role | How you arrive | What you administer |
|------|----------------|---------------------|
| **Server owner** | First Plex sign-in when multi-user is on, or the single operator when multi-user is off | Connections, libraries, sync, persona, household users, MCP keys, fleet credentials |
| **Household member** | Later **Sign in with Plex** after multi-user is enabled | Your own profile preferences, chats, watchlist, ratings — not the server |

Default install is **single-owner with no login**: anyone on the trusted network who can reach the UI is effectively an admin. Multi-user adds Sign in with Plex and separates personal data; it's still a household product on a LAN, not a multi-tenant SaaS.

---

## From the household member's perspective

### What you share when you sign in

When you use **Sign in with Plex**, Projectionist asks Plex who you are and stores a household user profile:

- Plex display name
- Optional email and avatar URL (if Plex provides them)
- Plex user id (for identity, not shown as a "shareable" library field)
- Role (`owner` or `member`)
- Optional Seerr link (user id / permissions) when the owner has Seerr enabled and linking succeeds

There is no open self-serve signup for new identities when invite-only is on (the default with multi-user). The owner sends a one-time **/join** link from **Admin → Access**, or you request access on the login page and wait for approval.

### What is yours alone (multi-user on)

When multi-user is enabled, these stay scoped to your user:

- Chat threads and messages
- Pending confirm tokens for *arr / Seerr actions you started
- Watchlist pins
- Ratings and review prompts tied to you
- Preference / taste facts the curator keeps for you
- Private memory notes (for example stated goals, watch intentions, callbacks/in-jokes, and external watches)
- Normalized Plex played-history, live-progress, webhook, and manual watched-state evidence that Plex attributed to your exact account id
- **Preferred conversation name** — how the curator addresses you in chat (may differ from your Plex display name)
- Voice toggles (listen / speak replies), when voice mode is available

Other household members cannot open your chats or confirm your pending actions through the normal multi-user API boundary.

### Memory, Youth mode, export, and purge

Your private memory stays tied to your account. **An owner cannot read an adult member's memory.** If the owner explicitly flags an account **Youth mode**, that account's profile shows a Youth badge and the owner may review or export that account's memory for moderation. This is not a consent toggle and does not apply to adult accounts.

#### What export and purge cover

Projectionist can hand you a full **export** of your account data, or permanently **purge** it. The two operate on **exactly the same set** — verified in `projectionist/library/db.py` (`export_user_memory` mirrors `purge_user_memory_and_chats`), so a copy taken before a purge is complete and nothing is left orphaned.

| Data | In the export? | Removed by purge? | Where it lives |
|------|:--------------:|:-----------------:|----------------|
| **Private memory notes** — goals, watch intentions, follow-ups, callbacks | Yes | Yes | `user_memory_notes` |
| **Chat threads** — titles, personas, context, timestamps | Yes | Yes | `chat_sessions` |
| **Message transcripts** — every message in your threads | Yes | Yes | `chat_messages` |
| **Saved library pages** — your saved curator responses | Yes | Yes | `saved_library_pages` |
| **Preference / taste facts** | Yes | Yes | `preference_facts` |
| Shared, sanitized media research (titles/people/companies) | No | No | Repository knowledge — not tied to any account |

The export is a single JSON (or Markdown) document containing your notes, your chat threads with their full message transcripts, your saved pages, and your preference facts. **Purge is permanent — export first if you want a copy.** Both actions record a small event (`export` / `purge`) so the account has an audit trail that it happened.

Curator research about titles, people, and production companies is **shared repository knowledge** drawn from configured official media APIs. It's kept separate from account memory, and the idle refresh task never reads private notes or chats — so purging your account never erases (and never leaks) that shared media knowledge.

> **How to run it:** each account can export or purge its own data through the Projectionist API (`GET /api/me/memory` returns the export; `DELETE /api/me/memory` purges the same set). If your build doesn't surface a button for this yet, ask your server owner, who can run it for your account. Owners: the exact commands are in the owner half of [Help](/help).

### What is shared household

Everyone on the same Projectionist instance shares:

- The indexed library catalog (titles, metadata, facets, embeddings)
- Sync jobs and library health
- Curator persona voice (name, tone, presets) configured by the owner
- In-app browsing of what the household owns (members may see a **public content** view of titles — more on posters and identifiers below)

### What the LLM provider receives

Chat uses the **owner's configured LLM** (OpenAI, Anthropic, Ollama, OpenRouter, etc.). The model receives:

- Your prompts and conversation context
- Tool results the agent needs (title metadata, library matches, watch signals the tools return)

It should **not** receive Plex server tokens, live `X-Plex-Token` media URLs, webhook secrets, or settings dumps. Your chat content goes to whichever provider the owner configured — including a local Ollama if they chose one, in which case nothing leaves the LAN.

### Voice mode

If you enable voice input:

- The **browser / OS speech service** may process microphone audio (some browsers use a cloud speech-to-text service).
- Projectionist does **not** upload raw audio to its own servers and does **not** store raw audio on disk.
- Transcripts become normal chat text and then follow the usual chat → LLM path.
- Optional "speak replies" uses the browser's `speechSynthesis` for assistant text.

### Preferred name

You can set a **preferred conversation name** on your profile. Projectionist stores it on your user record and uses it when addressing you. Fallback: Plex display name, then a neutral greeting.

### Watchlist and Plex account token

Local watchlist pins are yours. When watchlist ↔ Plex Discover sync is enabled:

- Projectionist may store an **encrypted** copy of your Plex account token from Sign in with Plex (`plex_token_enc`) solely to pull/push your Discover watchlist (and related account features such as Seerr linking).
- That token is **not** returned by API responses, MCP tools, or the UI.
- If the token is missing, sync asks you to re-sign in — it does not fall back to exposing the server library token as "your" account token.

### Curated lists

Named lists you create in Projectionist (for example "Friday picks") are stored locally and owned by your user. Visibility may be private, household, or link-based inside Projectionist. Publishing to **Plex Lists** (when supported) uses your encrypted account token; Projectionist will not pretend a Plex publish succeeded if the API is unavailable.

### What other members cannot see

- Your chat history and message feedback
- Your pending *arr / Seerr confirmation tokens
- Your watchlist and personal ratings (as personal records)
- Your mapped Plex played-history evidence
- Owner-only Admin: fleet URLs, API keys, MCP keys, household user management

### MCP and members

Household members do **not** control MCP API keys. The owner may expose library *content* to external apps via MCP; see [MCP](#mcp). That path is about titles and inventory — not your private chats.

---

## From the server owner's perspective

### Fleet credentials

Stored under the app data directory (typically `/config` → `settings.json` and related files):

- Plex server URL and **server** token
- Radarr / Sonarr / Seerr / TMDB / TVDB / Fanart / Tautulli keys as configured
- LLM provider base URL, model, and API key
- Webhook secret, session secret material, feature flags

**Who can view them in the UI:** owner Admin / Configuration only (not household members). Treat the Docker `/config` volume and backups as secret material. UI-saved keys in `settings.json` are encrypted at rest when a secrets key is available; still protect the volume and back up `PROJECTIONIST_SECRETS_KEY` with `/config`.

### Plex watch evidence health

Every 15 minutes, the **Plex Watch History** scheduled task asks Plex for a
bounded page of played-history evidence. Projectionist keeps normalized
movie/episode identifiers, the stable Plex account id, event time, optional
progress/duration, and a deterministic fingerprint. It does **not** keep the
raw response, Plex token, client IP, or transcode details.

Webhooks add pause, stop, and played signals immediately, including progress
below the separate rating-prompt threshold. Active playback is sampled once per
minute while sessions exist and every five minutes while idle; an unavailable
Plex server makes the poller back off rather than blocking startup. Projectionist
keeps only a one-way client hash for those samples—not the device name, address,
bandwidth, or raw session payload. Marking a title watched or unwatched records
an append-only manual correction only for an exactly linked Plex account.

Exact account mapping matters: an event maps to a household user only when
Plex's stable account id exactly matches that user's linked Plex id. Unmapped
events remain separate evidence. Display names are never used to guess
ownership, and one history event does not prove an uninterrupted viewing.
These observations are evidence only: Phase 2 does not turn them into a logical
session or completion count.

On a trusted single-owner installation, inspect freshness and mapping coverage:

```bash
# Run an ingest immediately (otherwise it runs every 15 minutes while idle)
curl -s -X POST \
  'http://localhost:8788/api/admin/scheduled-tasks/watch_history_ingest/run?wait=true' \
  | python3 -m json.tool

# Inspect the privacy-safe source health summary
curl -s http://localhost:8788/api/admin/watch-tracker/status \
  | python3 -m json.tool
```

The owner-only response contains source capability, cursor age, aggregate
mapped/unmapped counts, and a sanitized last-error category. It returns no
titles, rating keys, Plex account ids, server machine ids, tokens, or event
rows. With household login enabled, use the signed-in owner Admin session;
members receive `403 Forbidden`.

### MCP keys

Projectionist supports two trust planes (selected by which secret is presented — never by a client "mode" flag alone):

| Key | Typical env | Purpose |
|-----|-------------|---------|
| Privacy MCP key | `PROJECTIONIST_MCP_API_KEY` | Read-oriented library intelligence with a **public content** schema |
| Full / in-stack MCP key | `PROJECTIONIST_MCP_FULL_API_KEY` | Deeper internal library fields + confirm-gated *arr propose tools for trusted automation on your LAN |

Details and exposure: [MCP](#mcp). Rotate keys in **Admin → Advanced** (last-4 hint on status; full value shown once after regenerate). Do not reuse the same string for both keys.

### Images (TMDB posters)

For privacy-safe and member-facing library JSON, Projectionist prefers **TMDB CDN** poster/backdrop URLs (`image.tmdb.org`). Those URLs carry no Plex token and no LAN hostname. Plex thumbnail URLs that embed `X-Plex-Token` must not leave via privacy MCP or member public schemas.

### Webhooks, logging, backups

- Plex webhooks (if enabled) require a configured webhook secret.
- Application logs may include titles, job phases, and user ids — not raw API keys by design — but still treat log-volume access as sensitive.
- Backups of `/config` include credentials; store them like password vaults.

### Network expectations

Do **not** expose bare port `8788` to the public internet. Keep Projectionist on a trusted LAN or behind an authenticated reverse proxy. See [SECURITY.md](SECURITY.md) for the operator threat model and finding checklist.

---

## MCP (Model Context Protocol)

MCP lets external tools query your **indexed library**. Mode is determined by the API key (HTTP) or explicit stdio mode settings — not by the client asserting a privilege level.

### Privacy mode (default for sharing)

- **Tools:** sanitized catalog/search browse — library query, facets, aggregate counts, TV progress filters, TMDB discovery. Progress filters (e.g. unwatched / in-progress) may still narrow *owned catalog* results; they do **not** expose household affinity tools.
- **Affinity-biased tools are full-only:** `analyze_watch_patterns`, `recommend_hidden_gems`, purge candidates, watchlist pins, and “tonight”-style bias helpers require the full MCP key (even though raw Plex fields stay stripped in privacy mode, those answers encode household taste).
- **Schema:** public content — titles, years, genres, cast, truncated overviews, `tmdb_id` / `tvdb_id`, optional coarse watch state, **TMDB** image URLs when available.
- **Must not include:** Plex/LAN/`X-Plex-Token` media URLs, `rating_key`, machine identifiers, household user identity, email/avatar, file sizes in bytes, raw view timestamps, `in_radarr` / `in_sonarr`, absolute paths, secrets, or *arr write tools.

### Full / in-stack mode (trusted LAN automation)

- **Tools:** privacy catalog tools with richer **internal** fields, affinity/watch-biased helpers, plus confirm-gated propose tools for Radarr/Sonarr (and optional Seerr) that return a pending token — no silent writes.
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
| Private user memory | SQLite | Own | Youth accounts only | — | — | Current user's agent context |
| Chat transcripts (messages) | SQLite | Own | Own + admin host access | — | — | Y\* (provider) |
| Saved library pages | SQLite | Own | — | — | — | Y (agent tools) |
| Preference facts | SQLite | Own | — | — | — | Current user's agent context |
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

| Step | Who processes it | Stored by Projectionist |
|------|------------------|--------------------|
| Microphone audio | Browser / OS speech service | No raw audio |
| Transcript text | Projectionist chat + LLM\* | As chat messages |
| Spoken replies | Browser `speechSynthesis` | Not stored as audio |

---

## We do not

- Sell your household data or train a Projectionist-hosted foundation model on your chats
- Require a Projectionist cloud account for core library curation
- Expose live `X-Plex-Token` media URLs through privacy MCP or member public library JSON
- Let privacy MCP (or a mode flag) escalate into full / write-capable MCP
- Hand MCP clients your Plex server token, LLM key, or `settings.json`
- Store raw microphone audio on the Projectionist data volume (voice transcripts only)
- Email household invites or scrape contacts from Plex beyond the signed-in profile fields above
- Pretend Plex Lists publish succeeded when the Discover API path is unavailable
- Leave anything behind after a purge — an account purge removes every store listed under **What export and purge cover**

---

## Your choices

- Keep **multi-user off** for a single trusted operator on a private network
- Turn **multi-user on** so chats, watchlists, and ratings partition per Plex identity
- **Export or purge** your account data at any time — same set either way (see **What export and purge cover**)
- **Do not enable** full MCP (or leave `PROJECTIONIST_MCP_FULL_API_KEY` unset) if you only want the privacy schema
- **Rotate** MCP keys if a client or paste leaked
- Choose an **LLM provider** you trust (including fully local Ollama)
- Leave the household by asking the owner to disable or remove your user (when user management is available)
- Read the technical checklist: [SECURITY.md](SECURITY.md)

---

## Related docs

- [SECURITY.md](SECURITY.md) — operator threat model and findings
- [MCP.md](MCP.md) — MCP tools, keys, and transport
- [wiki/Multi-User.md](wiki/Multi-User.md) — Sign in with Plex
- [HELP.md](HELP.md) — in-app Help (`/help`); owner half has the export/purge commands
- In-app copy of this page: **`/privacy`** (no login required)
