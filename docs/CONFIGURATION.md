# CuratorX — Configuration

Settings persist to `{DATA_DIR}/settings.json` (default `/config/settings.json` in Docker, `./config` locally). Environment variables override file values when set.

---

## Required

| Setting | Env var | Description |
|---------|---------|-------------|
| Plex URL | `PLEX_URL` | Plex server base URL |
| Plex token | `PLEX_TOKEN` | Plex authentication token |
| Movie section | `PLEX_MOVIE_SECTION` | Plex movie library section key |
| TV section | `PLEX_TV_SECTION` | Plex TV library section key |
| TMDB API key | `TMDB_API_KEY` | Discovery and metadata enrichment |

---

## Recommended

| Setting | Env var | Description |
|---------|---------|-------------|
| Radarr URL / key | `RADARR_URL`, `RADARR_API_KEY` | Add movies after confirmation |
| Sonarr URL / key | `SONARR_URL`, `SONARR_API_KEY` | Add TV shows after confirmation |
| LLM provider | `LLM_PROVIDER` | Preset: `openai`, `anthropic`, `gemini`, `groq`, `mistral`, `together`, `deepseek`, `openrouter`, `ollama`, or `custom_openai_compatible` |
| LLM base URL | `LLM_BASE_URL` | Optional when using a preset provider (defaults apply) |
| LLM API key | `LLM_API_KEY` | Provider key (not required for Ollama) |
| LLM model | `LLM_MODEL` | e.g. `gpt-4o-mini`, `claude-sonnet-4-20250514`, `gemini-2.0-flash` |

---

## Optional

| Setting | Env var | Description |
|---------|---------|-------------|
| Fanart.tv key | `FANART_API_KEY` | Rich poster/backdrop art |
| TVDB key | `TVDB_API_KEY` | TV metadata parity (client present; sync wiring partial) |
| Tautulli URL / key | `TAUTULLI_URL`, `TAUTULLI_API_KEY` | Watch stats for purge scoring |
| Radarr root folder | `RADARR_ROOT_FOLDER` | Default path for movie adds |
| Sonarr root folder | `SONARR_ROOT_FOLDER` | Default path for series adds |
| Quality profile IDs | `RADARR_QUALITY_PROFILE_ID`, `SONARR_QUALITY_PROFILE_ID` | *arr quality profiles |
| Library sync interval | `library_sync_interval_hours` in settings | Minimum hours between auto-syncs (1–168, default 24) |
| Library sync hour | `library_sync_hour` in settings | Optional preferred local hour `0–23` for daily sync; `null` = interval-only. Uses container local time — set `TZ` (e.g. `America/New_York`) on Unraid if needed. |
| TV page size | `tv_page_size` in settings | Plex TV fetch batch size (50–2000, default 500) |
| Library enrich workers | `library_enrich_workers` in settings | Parallel TMDB/Fanart enrichment threads during library sync (1–16, default 6). SQLite upserts stay serial. |
| Sync reviews to Plex | `sync_reviews_to_plex` in settings | When `true`, saving a 1–5 star review writes the matching Plex user rating (2/4/6/8/10) via `PUT /:/rate` |
| Log level | `CURATORX_LOG_LEVEL` or `LOG_LEVEL` | `ERROR`, `WARNING`, `INFO` (default), or `DEBUG` |
| Log format | `LOG_FORMAT` or `CURATORX_LOG_FORMAT` | `text` (default) or `json` |

---

## Feature flags (optional, off by default)

CuratorX ships as a **single-owner homelab app** with no login screen. Household multi-user auth and Seerr integration are **opt-in** and stay disabled until you turn them on in Configuration or `settings.json`.

Default values (also in `config/settings.example.json`):

```json
{
  "features": {
    "multi_user_enabled": false,
    "seerr_enabled": false
  },
  "auth": {
    "mode": "disabled",
    "plex_login_enabled": true,
    "oidc_enabled": false,
    "local_login_enabled": false
  },
  "seerr": {
    "url": "",
    "api_key": "",
    "link_on_login": true,
    "require_linked_user_for_requests": false
  }
}
```

| Flag | Default | What it does when enabled |
|------|---------|---------------------------|
| `features.multi_user_enabled` | `false` | Requires sign-in; enforces owner vs member roles; per-user chat and reviews |
| `features.seerr_enabled` | `false` | Activates Seerr connector for household discovery and requests |
| `auth.mode` | `disabled` | Set to `plex`, `oidc`, or `local` when multi-user is on |
| `seerr.link_on_login` | `true` | After Plex login, bridge identity to Seerr |
| `seerr.require_linked_user_for_requests` | `false` | Block Seerr requests until the user is linked |

**For most installs:** leave everything at the defaults. CuratorX behaves exactly as before — one implicit owner, no login, no Seerr calls.

**To enable multi-user or Seerr later:** open **Config → Multi-user auth** and **Config → Seerr** (or edit `{DATA_DIR}/settings.json`), set `features.multi_user_enabled` to `true`, choose `auth.mode` (`plex` for token login), and save. For Seerr, set `features.seerr_enabled` to `true`, add your Seerr URL and API key, and test the connection. The frontend reads `GET /api/features` to show or hide login, Seerr request buttons, and user-management UI.

### Multi-user Plex login

When `features.multi_user_enabled` is `true`, CuratorX requires sign-in before using the chat UI.

1. **Enable in Config** — Turn on **Enable multi-user auth** and set **Auth mode** to **Plex token login**.
2. **Set a session secret (recommended)** — Export `CURATORX_SESSION_SECRET` to a long random string in your container or `.env`. Without it, CuratorX uses a dev default (fine for LAN testing only).
3. **Sign in** — Open CuratorX; you are redirected to `/login`. Click **Sign in with Plex**, paste a Plex token from [plex.tv account settings](https://app.plex.tv/desktop/#!/settings/account), and submit.
4. **Roles** — The first Plex account to sign in becomes **owner**. Later accounts start as **member**. Owners can promote/demote users under **Config → Multi-user auth → Users**.
5. **Seerr bridge** — With Seerr enabled and **Link Plex users to Seerr on login** checked, CuratorX calls Seerr `POST /auth/plex` during login and stores `seerr_user_id` + permissions on the user row.

| Endpoint | Purpose |
|----------|---------|
| `GET /api/auth/me` | Current signed-in user (401 when multi-user is on and no session) |
| `POST /api/auth/plex` | Validate Plex token, upsert user, optional Seerr bridge, set session cookie |
| `POST /api/auth/logout` | Clear session cookie |
| `GET /api/users` | List household users (owner only) |
| `PATCH /api/users/{id}` | Change role (owner only) |

**Troubleshooting**

- **401 after enabling multi-user** — Expected until you sign in at `/login`.
- **Invalid Plex token** — Regenerate the token in Plex account settings; tokens are user-specific.
- **Seerr not linked** — Confirm Seerr URL/API key, enable **Link on login**, and ensure the Plex account exists in Seerr.

---

## Library sync (maintenance dashboard)

After onboarding, open **Config** to reach the maintenance dashboard. The **Library sync** card lets you pull your Plex libraries into CuratorX on demand.

| Control | What it does |
|---------|----------------|
| **Sync library** | Starts a background job (`POST /api/library/sync`) |
| Movie/show counts | From `GET /api/library/stats` — how many titles are indexed |
| Last sync | When the most recent sync finished (or "Never" if you have not synced yet) |
| Status line | Polls `/api/jobs` every few seconds while a sync is running |

**When to use it:** after adding new movies or shows in Plex, when title cards look stale, or when `/stats` in chat shows an old last-sync time. Automatic sync also runs on a schedule (`library_sync_interval_hours`, default 24 h). Optionally set `library_sync_hour` (0–23) so daily sync prefers a clock hour in the container’s local timezone (`TZ` env) instead of firing purely on elapsed time after the last run.

**If sync fails:** check Plex URL/token and library section keys in Config, then read container logs (`docker compose logs -f curatorx`). The status line shows the error when the job fails.

### Library health dashboard

The maintenance dashboard includes a **Library health** section with three at-a-glance metrics from `GET /api/library/health`:

| Metric | Meaning |
|--------|---------|
| **Unwatched %** | Share of indexed titles with zero plays |
| **Stale adds** | Titles added 90+ days ago that you still have not watched |
| **Rating coverage** | Share of watched titles that have a personal 1–5 star review |

Use these to spot backlog, forgotten imports, and gaps in your review log before asking the curator for purge or rating suggestions.

### Training corpus export

Owners can download a JSON backup of taste-training data from **Config → Training corpus export** (`GET /api/admin/export/training-corpus`). The file includes:

- `message_feedback` — helpful / not-helpful reactions on curator replies
- `preference_facts` — explicit and inferred taste signals
- `user_title_reviews` — your personal star ratings and notes

Use this for offline analysis, backup, or feeding external training pipelines. Nothing is uploaded automatically.

---

## Seerr (optional household requests)

Seerr (Overseerr / Jellyseerr) lets household **members** request movies and shows without direct Radarr/Sonarr access. CuratorX remains the **owner's intelligence layer**; members see **Request in Seerr** on title cards when multi-user mode is enabled.

### Setup steps (novice homelab)

1. **Install Seerr** — Deploy [Seerr](https://github.com/seerr-team/seerr) on your LAN alongside Plex, Radarr, and Sonarr. Complete its setup wizard and link Plex + *arr inside Seerr.
2. **Create an API key** — In Seerr: **Settings → General → API Key**. Copy the key.
3. **Enable in CuratorX** — **Config → Seerr** → check **Enable Seerr integration**, enter URL (e.g. `http://10.0.0.10:5055`) and API key, click **Test connection**.
4. **Certify** — A successful test marks Seerr certified (same as Plex/Radarr). Save settings.
5. **Roles** — Owners keep **Add to Radarr/Sonarr**. Members (when multi-user is on) get **Request in Seerr**. Check `GET /api/features` → `request_path` (`arr` or `seerr`).

### API endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /api/features` | `request_path`, `user.role`, Seerr flags |
| `GET /api/requests` | Proxy to Seerr pending request queue |
| `POST /api/setup/test/seerr` | Validate URL + API key |
| Agent `request_via_seerr` | Queue a title (confirmation optional) |
| Agent `approve_seerr_request` | Owner approves a pending request |

### Troubleshooting

- **401 on test** — Regenerate the Seerr API key and save again in Config.
- **Connection refused** — Verify the URL from the CuratorX host/container (not just your desktop browser).
- **Members still see Radarr** — Requires `features.seerr_enabled` **and** `user.role` = `member` from `GET /api/features`.
- **Request fails after confirm** — Ensure Radarr/Sonarr are configured in Seerr and the service API key has admin/request rights.

---

## Plex review sync

CuratorX can mirror your **personal 1–5 star reviews** back to Plex so they appear as Plex user ratings on movies and shows you own.

| Setting | Default | What it does |
|---------|---------|--------------|
| `sync_reviews_to_plex` | `true` | When enabled, every saved review with a Plex `rating_key` triggers `PUT /:/rate` |

**Star mapping:** CuratorX uses 1–5 stars internally. Plex stores ratings on a 0–10 scale, so CuratorX maps `1→2`, `2→4`, `3→6`, `4→8`, `5→10`.

**Where to turn it on:** Configuration → **Plex library mapping** → check **Sync personal reviews to Plex star ratings**, then save (the toggle saves immediately).

**Requirements:** Plex URL and token must be configured. The reviewed title needs a Plex `rating_key` (usually present after a library sync). If sync fails (Plex offline, missing key), the review is still saved locally; `plex_rating_synced` stays `false` until a later save succeeds.

**Reading Plex ratings:** During library sync, CuratorX reads each title's Plex `userRating` (0–10 scale) and stores it as `plex_user_rating_stars` (1–5) on `library_items`. Episode-level Plex ratings are stored on `library_episodes.plex_user_rating_stars` during TV episode sync.

**Immediate cache update:** When a review syncs to Plex (including after you choose **Replace on Plex**), CuratorX updates the local `plex_user_rating_stars` cache immediately — you do not need to wait for the next library sync to see the new rating in chat or library queries.

**Rating conflicts:** If Plex already has a different star rating when you save a review with sync enabled, the API returns **409** with `code: plex_rating_conflict` and the message `Plex has X★ — keep or replace?`. Your review is saved locally either way. Choose **Keep Plex rating** to leave Plex unchanged, or **Replace on Plex** (resubmit with `replace_plex_rating: true`) to overwrite Plex.

**Collections (curator tools):** The agent can propose creating Plex collections or adding owned titles to an existing collection when `features.plex_collections_enabled` is `true`. These writes require the same confirmation tokens as Radarr/Sonarr adds — nothing is sent to Plex until you confirm in chat. Turn this on in Configuration → **Plex library mapping** → **Allow curator to manage Plex collections**.

---

## Plex webhooks (near-completion rating prompts)

CuratorX can receive **Plex webhook** events so rating prompts appear soon after you finish a movie or episode — without waiting for the next library sync.

### Webhook URL

Point Plex at this endpoint (replace host/port with your CuratorX server):

```text
http://YOUR_CURATORX_HOST:8765/api/webhooks/plex
```

Examples:

| How you run CuratorX | Typical URL |
|----------------------|-------------|
| Docker on Unraid (`8765:8765`) | `http://YOUR_UNRAID_IP:8765/api/webhooks/plex` |
| Same machine as Plex | `http://127.0.0.1:8765/api/webhooks/plex` |
| Reverse proxy | `https://curatorx.yourdomain.com/api/webhooks/plex` |

Plex must be able to reach this URL from the Plex Media Server host (LAN IP is fine; `localhost` only works if Plex and CuratorX share the same container/network namespace).

### Webhook authentication (optional)

If your CuratorX instance is reachable from outside your trusted LAN, set a shared secret so random callers cannot queue rating prompts.

| Setting | Env var | Header |
|---------|---------|--------|
| `webhook_secret` | `CURATORX_WEBHOOK_SECRET` | `X-CuratorX-Webhook-Secret` |

When `webhook_secret` is non-empty, every `POST /api/webhooks/plex` must include the header with the same value. Requests without a matching header receive **401 Unauthorized**. When the secret is empty (default), webhooks work as before with no header required.

**Homelab tip:** Generate a long random string (e.g. `openssl rand -hex 32`), add it to `.env` as `CURATORX_WEBHOOK_SECRET=...`, restart CuratorX, then configure your reverse proxy or a small script to inject the header when forwarding Plex webhooks — Plex itself does not send custom headers, so the secret is most useful behind a proxy you control or on a LAN-only URL.

### Setup steps (novice homelab / Unraid)

1. **Confirm CuratorX is reachable** — Open the CuratorX UI in your browser. Note the host IP and port (default **8765** in `docker-compose.yml`).
2. **Open Plex webhook settings** — Plex Web App → your avatar → **Account Settings** → **Webhooks** (or Plex Media Server → **Settings** → **Webhooks**, depending on Plex version).
3. **Add the URL** — Paste `http://YOUR_CURATORX_IP:8765/api/webhooks/plex` and save.
4. **Test with a short watch** — Play a movie or episode past **85%**, then stop playback. Within a few seconds, open CuratorX chat; a persona-voiced rating card should appear at the bottom of the thread.
5. **Optional: Tautulli** — If you use Tautulli, configure it under **Config → Tautulli**. Library sync will also use Tautulli `get_metadata` for completion % when Plex `viewOffset` is missing locally.

### What CuratorX listens for

| Plex event | Behavior |
|------------|----------|
| `media.stop` | If `viewOffset / duration ≥ 85%`, queue a rating prompt |
| `media.scrobble` | Plex marks a title watched (~90%+); queue a rating prompt |
| `media.pause` | Same completion check as stop (useful on some clients) |

Prompts are skipped when you already saved a review, or if you dismissed the same title within the last 30 days.

### Troubleshooting

- **No prompt after finishing** — Confirm the webhook URL is saved in Plex and CuratorX logs show `Plex webhook` entries. Try a full stop (not just back-button) past 85%.
- **Connection refused** — Use the LAN IP CuratorX listens on, not `localhost`, unless Plex runs on the same host.
- **Prompt only after sync** — Webhook not reaching CuratorX; fix URL/firewall. Sync-based detection still works via `viewOffset` during library sync.
- **Duplicate prompts** — One row per `rating_key` in `rating_prompt_queue`; re-watching updates completion but won't spam if you already reviewed.

---

## Logging

CuratorX logs to **stdout/stderr** for Docker and systemd deployments. Set the level in `.env` or `docker-compose.yml`:

| Level | What you see |
|-------|----------------|
| **ERROR** | Failures only (sync crashes, tool errors, HTTP hard failures) |
| **WARNING** | HTTP errors/timeouts, episode sync skips, LLM chat errors, invalid settings |
| **INFO** | Startup, sync start/finish, scheduler triggers, action propose/confirm, phase counts |
| **DEBUG** | Per-job progress, TMDB/Fanart enrichment skips, agent tool calls, env/settings merge |

Examples:

```bash
# Follow live logs
docker compose logs -f curatorx

# Verbose troubleshooting
CURATORX_LOG_LEVEL=DEBUG docker compose up -d

# Errors only
CURATORX_LOG_LEVEL=ERROR docker compose up -d
```

API keys and tokens are never written to logs (URLs and error bodies are redacted).

---

## LLM providers

| Provider | Default base URL | Notes |
|----------|------------------|-------|
| **openai** | `https://api.openai.com/v1` | OpenAI API |
| **anthropic** | `https://api.anthropic.com` | Native Claude API (`LLM_API_KEY` + `LLM_MODEL`) |
| **gemini** | `https://generativelanguage.googleapis.com/v1beta/openai` | Google Gemini via OpenAI-compatible layer |
| **groq** | `https://api.groq.com/openai/v1` | Groq inference |
| **mistral** | `https://api.mistral.ai/v1` | Mistral API |
| **together** | `https://api.together.xyz/v1` | Together AI |
| **deepseek** | `https://api.deepseek.com/v1` | DeepSeek API |
| **openrouter** | `https://openrouter.ai/api/v1` | OpenRouter gateway |
| **ollama** | `http://localhost:11434/v1` | Local inference; no API key required |
| **custom_openai_compatible** | User-defined | Set `LLM_BASE_URL` manually (LiteLLM, vLLM, etc.) |

Embeddings use `LLM_EMBEDDING_MODEL` and optional `LLM_EMBEDDING_BASE_URL`. Without an embedding API, deterministic hash embeddings (384-dim) are used.

---

## Curator persona (database-backed)

Persona settings live in SQLite (`curator_persona_metrics`), not only `settings.json`:

| Field | API | Description |
|-------|-----|-------------|
| Curator name | `PUT /api/persona` | Display name; injected into system prompt |
| Vocabulary density | `val_bro_prof` | 0.0 (bro) → 1.0 (professorial) |
| Interaction friction | `val_dipl_snark` | 0.0 (diplomatic) → 1.0 (snarky) |
| Automation autonomy | `val_pass_auto` | 0.0 (passive) → 1.0 (autonomous) |

Curator name can also be stored in `curator_system_config` via `PUT /api/system-config`.

---

## Curation lenses

| Concept | Storage | API |
|---------|---------|-----|
| Active lens | `curator_system_config.active_lens_id` | `GET/PUT /api/lenses/active` |
| Lens registry | `curation_lenses` table | `GET/POST /api/lenses` |
| Taste weights | `lens_taste_profile` | Per-lens cluster tags with optional explicit lock |
| Chat scope | `lens_id` on sessions/messages | Pass `lens_id` on `POST /api/chat` |

Default lens: **`general`**.

---

## Secrets handling

API keys are stored in `settings.json` on the config volume when saved via the UI. Environment variables (including values from `.env` when running locally or via Docker `env_file`) override file values at runtime and are **not** written back unless you explicitly save a new value in Settings.

`GET /api/settings` masks secret fields and returns `{field}_set: true` plus `{field}_source` (`env` or `file`) instead of raw values. The config UI shows placeholders such as “Configured via environment (.env)” for env-backed secrets.

Local dev: copy `.env.example` to `.env` — the web app loads it on startup (`load_dotenv_file`). Docker Compose also passes `.env` via `env_file`.

---

## Related documentation

- [ONBOARDING.md](ONBOARDING.md) — first-run flow
- [DATA_MODEL.md](DATA_MODEL.md) — full schema reference
- [DOCKER.md](DOCKER.md) — container env seeding
