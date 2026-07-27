# Projectionist security assessment

Living pen-test brief for operators on the current Projectionist product surface. Status values move between **Open**, **Mitigated**, and **Accepted** as findings land — residual notes describe what remains after mitigations.

## Scope

| In scope | Out of scope (for this brief) |
|----------|-------------------------------|
| Web UI + FastAPI control plane (`projectionist/web/`) | Third-party Plex / *arr / Seerr / LLM hosts |
| Optional multi-user auth (Plex PIN, local password, OIDC) + session cookies | Host OS / Unraid / Docker daemon hardening |
| Setup connection tests, chat, jobs, sync, *arr confirm tokens | Supply-chain / dependency CVE hunting |
| Plex webhook ingress | Multi-tenant SaaS isolation |
| Dual-mode MCP + library privacy sanitizers | |
| Default Docker / Unraid packaging assumptions (non-root `curatorx`) | |

**Trust assumption:** Projectionist is a single-owner homelab app. With multi-user **off**, there is no login — anyone who can reach the HTTP port is an effective admin. With multi-user **on**, configured auth methods (Plex PIN / local / OIDC), session cookies, API middleware, and per-user chat/actions partitioning apply — still assume a trusted LAN for default single-owner mode.

## Threat model

### Trusted LAN

Typical Unraid / Docker deploy on a private network. Neighbors on the same VLAN (or a compromised device) can hit `:8788`. Default bind is all interfaces (S3). Single-owner mode has no auth; keep the host on a trusted segment.

### Guest / IoT Wi‑Fi

Guest SSID clients that share L2/L3 with the host are the same as LAN attackers for this app. Treat guest Wi‑Fi as hostile unless the Projectionist host is firewalled to the trusted VLAN only.

### Accidental WAN

Port-forwarding or exposing `8788` (or a reverse proxy without auth) exposes the control plane: settings, library sync, chat (LLM spend), *arr propose/confirm when tokens are known, and setup tests that can use stored secrets. Session forging is trivial if `PROJECTIONIST_SESSION_SECRET` is left at the public development default (S2 mitigated via auto-bootstrap + refuse-on-default).

### Multi-user household

When multi-user is enabled, middleware requires a session for almost all `/api/*` (allowlist: health, features, access-requests, invite validate/redeem, auth, webhooks). Chat, pending actions, watchlist, reviews, and preferences are scoped by `user_id`. Owner-only routes cover settings, setup tests, sync mutate, and persona/lens writes. Guests cannot request media / *arr writes. The shared library catalog remains household-wide; members see a public-content library browse schema. Login may use Plex PIN, local password (PBKDF2), and/or OIDC depending on `auth_*` flags; `GET /api/features` exposes `auth_methods`. **New** Plex/OIDC identities require a `/join` invite by default (`features.invite_only`); opt into LAN-open auto-provision with `features.open_auto_provision`.

```text
SPA AuthGate ──no session──► /login
Most /api/*  ──no session──► 401 when multi_user_enabled
```

### MCP & privacy (dual-mode)

Projectionist exposes optional MCP over stdio and HTTP (`/mcp`). Trust is selected by **which API key** is presented — never by a client-supplied mode flag.

| Mode | Credential | Schema | Tools |
|------|------------|--------|-------|
| **privacy** | `PROJECTIONIST_MCP_API_KEY` | Public content (titles/metadata; TMDB CDN images only) | Read-only library tools |
| **full** | `PROJECTIONIST_MCP_FULL_API_KEY` (must differ from privacy key) | Internal fields (`rating_key`, watch telemetry, *arr flags) **minus** live `X-Plex-Token` URLs | Read tools + confirm-gated `propose_*` / `confirm_pending_action` |

Stdio: `PROJECTIONIST_MCP_MODE=privacy|full`; full requires a distinct `PROJECTIONIST_MCP_FULL_API_KEY` in the environment. Shared sanitizers in [`projectionist/privacy/`](../projectionist/privacy/) also redact `/api/library/*` browse JSON for non-owner members when multi-user is on.

See [MCP.md](MCP.md) and [PRIVACY.md](PRIVACY.md).

---

## Findings

| ID | Severity | Location | Exploit one-liner | Status | Residual risk |
|----|----------|----------|-------------------|--------|---------------|
| **S1** | Critical | Control-plane routes historically lacked session deps. | With `multi_user_enabled=true`, unauthenticated `curl` to settings/chat/sync/confirm. | **Mitigated** | When multi-user is off, the control plane remains open on the LAN by design. |
| **S2** | Critical | Session secret fell back to a public dev default. | Forge `curatorx_session` cookies for any `user_id`. | **Mitigated** | Auto-generated DATA_DIR secret + refuse enable on public default; still set `PROJECTIONIST_SESSION_SECRET` in production. |
| **S3** | Critical | App binds `0.0.0.0:8788` in Docker / Unraid packaging. | Reach the control plane from any host interface / accidental WAN map. | **Open** | Do not port-forward bare 8788; bind/firewall to LAN or put behind an authenticated reverse proxy. |
| **S4** | High | Plex PIN create/poll without binding / rate limits. | Create/poll unbound PINs; race another client’s PIN once authorized. | **Mitigated** | PIN nonce cookie + per-IP rate limits; residual race risk on shared browser profiles. |
| **S5** | High | Setup tests filled secrets and fetched operator URLs (SSRF). | Hit link-local/metadata URLs with attached saved tokens. | **Mitigated** | Owner-gated + host-matched secrets + link-local/metadata blocks; private LAN targets still allowed for *arr. |
| **S6** | High | Chat threads not filtered by `user_id`. | Read/delete another user’s messages. | **Mitigated** | Chat threads scoped by `user_id` when multi-user is on. |
| **S7** | High | Pending *arr confirms by opaque token only. | Steal/guess a confirmation token and confirm writes. | **Mitigated** | Pending actions store `user_id`; confirm pops only matching tokens. |
| **S8** | High | Empty webhook secret accepted any Plex webhook POST. | Spoof webhook events to queue sync/side effects. | **Mitigated** | Empty webhook secret → 503; header required when configured. |
| **S9** | Medium | Session cookie lacked `Secure` behind HTTPS proxies. | Weaker cookie story on HTTPS / CSRF edge cases. | **Mitigated** | `Secure` cookie when `X-Forwarded-Proto=https`. |
| **S10** | Medium | Seerr path could skip confirmation. | Tool args submit Seerr requests immediately. | **Mitigated** | Seerr tool path always returns a confirmation token. |
| **S11** | Medium | Settings JSON stores API keys in plaintext under `/config`. | Read volume / backup / host filesystem → fleet credentials. | **Mitigated** | File mode `0600` on every save. **H4 Hybrid:** UI-persisted secrets are encrypted at rest (`PROJECTIONIST_SECRETS_KEY` or material derived from the session secret); env-supplied secrets still win and are not written back as plaintext. Back up the secrets key with `/config` (see [Rotating secrets & keys](#rotating-secrets--keys) and [DOCKER.md](DOCKER.md) backups). |
| **S12** | Low | Docs understated multi-user API enforcement. | Operators misread network-peer risk. | **Mitigated** | Docs + middleware aligned for multi-user. |
| **S13** | Low | Final Docker image runs as root (no `USER`). | Container breakout has root inside the image. | **Mitigated** | Entrypoint script auto-chowns `/config` to `curatorx` (UID/GID 1000) and drops privileges via `gosu`. Compatible with existing root-owned volumes and Kubernetes `runAsUser`. |
| **S14** | High | Rate limiter trusted `X-Forwarded-For` on direct LAN binds. | Rotate spoofed IPs to bypass auth throttles / PIN brute force. | **Mitigated** | Ignore forwarded headers unless `PROJECTIONIST_TRUST_PROXY_HEADERS=1`; set that only behind a trusted reverse proxy. |
| **S15** | Medium | FastAPI served `/docs` and `/openapi.json` without auth. | Map mutate endpoints and auth deps from the LAN. | **Mitigated** | Docs disabled by default; set `PROJECTIONIST_EXPOSE_OPENAPI=1` for local development only. |
| **P1** | High | Library payloads emitted live `X-Plex-Token` in thumbs. | Privacy MCP / member browse exfiltrates server token. | **Mitigated** | Sanitizer allowlists `image.tmdb.org` only. |
| **P2** | High | Privacy MCP returned `rating_key` and other PMS ids. | Correlate titles to PMS items / probe the media stack. | **Mitigated** | Public schema drops infra ids; privacy mode rejects rating_key title lookups. |
| **P3** | Medium | Privacy / member APIs exposed telemetry, size, *arr flags. | Household inventory leaks to limited apps / members. | **Mitigated** | Public schema drops telemetry/arr/size; optional `watch_state` enum only. |
| **P4** | High | Single shared MCP key with no mode separation. | Compromised limited app inherits full schema / propose tools. | **Mitigated** | Dual keys; equal keys refuse full mode. |
| **P5** | Medium | Authenticated members received owner-grade library JSON. | Member curls dump rating keys, sizes, arr flags. | **Mitigated** | Member browse uses public-content sanitizer when multi-user is on. |
| **P6** | Medium | Full MCP / stdio without a distinct full secret. | Accidental escalate to propose tools. | **Mitigated** | Stdio full requires distinct full key; HTTP maps key → mode. |

---

## Operator guidance

1. **Do not expose `8788` to the internet.** Use LAN-only or an authenticated reverse proxy.
2. Set **`PROJECTIONIST_SESSION_SECRET`** to a long random value before enabling multi-user (or accept auto-generated secret under Config).
3. Set a non-empty **webhook secret** if anything outside the host can POST `/api/webhooks/plex`.
4. Keep the host on a **trusted LAN segment**; multi-user is household identity, not internet multi-tenant isolation.
5. Restrict who can mount/read the `/config` volume.
6. Prefer a **privacy MCP key** for shared/third-party clients; only mint `PROJECTIONIST_MCP_FULL_API_KEY` for trusted in-stack automation (keys must differ).
7. Leave **`PROJECTIONIST_TRUST_PROXY_HEADERS` unset** on direct LAN binds; enable only when a trusted reverse proxy sets client IP headers.
8. Keep **`PROJECTIONIST_EXPOSE_OPENAPI` unset** in production; use it only for local API exploration.

## Rotating secrets & keys

WAL-safe database backup steps live in [DOCKER.md](DOCKER.md).

Every credential Projectionist holds lives in one of two places: your **`settings.json`** under the config volume (`{DATA_DIR}`, `/config` in the default Docker image) or an **environment variable**. `settings.json` is written **`0600`** (owner read/write only) on every save. UI-saved secrets are **encrypted at rest** when a secrets key is available (`PROJECTIONIST_SECRETS_KEY`, or a key derived from the session secret). **Environment variables still win** when set and are not written back into `settings.json` as plaintext. Treat the volume, its backups, and the secrets key as secret material; rotate promptly whenever a key may have been exposed.

**How it works:** Projectionist never rotates a live credential for you — that's an owner action, because the real secret lives at the *provider* (TMDB, your LLM vendor, Radarr/Sonarr, Plex). Rotation is always two steps: **issue a new secret at the source, then update Projectionist to match.** Updating only one side breaks the integration.

### The golden rule

1. **Revoke/reissue at the provider first** (regenerate the API key in TMDB, roll the token in Plex, etc.).
2. **Update the value in Projectionist** — via the UI or the file.
3. **Verify** the integration still works, then confirm the old secret is dead.

### Update in the UI (recommended)

Sign in as the **owner**, open **Settings**, paste the new value into the matching field (LLM API key, Plex token, Radarr/Sonarr/TMDB keys, webhook secret…), and **Save**. Saving rewrites `settings.json` (encrypted fields) and re-applies `0600` automatically.

### Update by editing the file (headless / scripted)

```bash
# Prefer env for long-lived ops secrets when possible.
# {DATA_DIR} is /config in the default image.
sudo nano /config/settings.json          # set "tmdb_api_key": "YOUR_NEW_TMDB_KEY"
docker compose restart projectionist     # reload settings on boot

# Confirm the file is owner-only (expect: 600)
stat -c '%a %U' /config/settings.json    # → 600 projectionist (or curatorx on older images)
```

### Backups and the secrets key

WAL-safe DB backup steps live in [DOCKER.md](DOCKER.md) (`sqlite3 .backup` or stop-then-copy). If you set **`PROJECTIONIST_SECRETS_KEY`**, store it alongside `/config` backups — without that key, encrypted fields in `settings.json` cannot be recovered. When the key is unset, Projectionist derives encryption material from the session secret (keep session secret + `/config` together).

If your platform doesn't support POSIX permissions (some network mounts), the `0600` step is skipped gracefully — in that case, lean harder on volume-level access controls.

### Secret-by-secret notes

| Secret | Field / var | Rotate at the source by… | Then update in Projectionist |
|--------|-------------|--------------------------|-------------------------|
| **LLM API key** | `llm_api_key` | Revoking the key in your LLM vendor's console and minting a new one | Settings → save (or edit file + restart) |
| **Plex token** | `plex_token` | Signing out other sessions / re-linking Plex to force a fresh token | Settings → save |
| ***arr keys** | `radarr_api_key`, `sonarr_api_key` | Regenerating the API key in Radarr/Sonarr **Settings → General** | Settings → save |
| **Metadata keys** | `tmdb_api_key`, `tvdb_api_key`, `omdb_api_key`, `fanart_api_key` | Regenerating the key in each provider's developer dashboard | Settings → save |
| **Webhook secret** | `webhook_secret` / `PROJECTIONIST_WEBHOOK_SECRET` | Choosing a new random value (`openssl rand -hex 24`) | Settings → save or env, then update the Plex webhook URL to match |
| **MCP keys** | `PROJECTIONIST_MCP_API_KEY`, `PROJECTIONIST_MCP_FULL_API_KEY` (env) | Choosing new random values (privacy and full keys **must differ**) | Update the env vars / Compose and restart |
| **Secrets key** | `PROJECTIONIST_SECRETS_KEY` (env) | Generating a long random value (`openssl rand -base64 48`) | Set env and restart — **note:** rotating without re-saving settings leaves old ciphertext undecryptable |
| **Session secret** | `PROJECTIONIST_SESSION_SECRET` (env) or `session_secret` file | Generating a long random value (`openssl rand -base64 48`) | Set the env var (or delete the file to auto-regenerate) and restart — **note:** rotating this invalidates every signed-in session |

**Honest limits.** Rotating a key here does **not** retroactively scrub it from old container logs, shell history, or prior backups — clean those separately. Encryption-at-rest reduces casual disk reads; it is not a substitute for protecting the `/config` volume and the secrets key.

## Penetration-test protocol

Repeatable full-platform engagements: [docs/security/pentests/README.md](security/pentests/README.md) (Protocol v1.0, harness under `scripts/security/pentest/`). Baseline run: [2026-07-platform-full](security/pentests/2026-07-platform-full/).

## Related docs

- [PRIVACY.md](PRIVACY.md) — plain-language privacy & data use (household + owner; in-app at `/privacy`)
- [MCP.md](MCP.md) — dual-mode MCP keys, schemas, TMDB image policy
- [TESTING.md](TESTING.md) — API authz regression (`tests/test_api_authz.py`)
- [security/pentests/README.md](security/pentests/README.md) — repeatable penetration-test protocol
- [CONFIGURATION.md](CONFIGURATION.md) — feature flags and session secret
- [WEB_UI.md](WEB_UI.md) — UI login vs API surface
- [wiki/Home.md](wiki/Home.md) — operator wiki index
