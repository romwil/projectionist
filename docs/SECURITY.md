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

**Trust assumption:** TLS encrypts the pipe; it does not replace household auth. Fresh installs start in **SETUP_MODE** (cinematic wizard only). After the wizard commits, **ACTIVE_MODE** is permanent: unauthenticated callers get the exhaustive public handshake below — not library browse, not guest tour, not self-serve signup. Single-owner anonymous admin remains LAN-only and is blocked by the **WAN interlock** when the visible client IP is public. `ipaddress.is_private` is not proof of LAN (Docker `172.16.0.0/12` is RFC1918) and is not proof of WAN (RFC 6598 `100.64.0.0/10` Tailscale/CGNAT).

## Threat model

### Trusted LAN

Typical Unraid / Docker deploy on a private network. Neighbors on the same VLAN (or a compromised device) can hit `:8788`. Default bind is all interfaces (S3). Single-owner mode has no auth; keep the host on a trusted segment.

### Guest / IoT Wi‑Fi

Guest SSID clients that share L2/L3 with the host are the same as LAN attackers for this app. Treat guest Wi‑Fi as hostile unless the Projectionist host is firewalled to the trusted VLAN only.

### Accidental WAN

Port-forwarding or exposing `8788` (or a reverse proxy without auth) used to expose the control plane: settings, library sync, chat (LLM spend), *arr propose/confirm when tokens are known, and setup tests that can use stored secrets. Session forging is trivial if `PROJECTIONIST_SESSION_SECRET` is left at the public development default (S2 mitigated via auto-bootstrap + refuse-on-default).

**Lobby theater port (`8791` by default):** a second listener serves an unauthenticated LAN lightbox (`GET /`, SSE `/api/theater/events`, poster proxy). It is **never** on `:8788`, never in `PUBLIC_HANDSHAKE`, and must **not** be published through Cloudflare / NPM / a public VIP. Every theater request runs an explicit RFC1918 / WAN peer gate (loopback, private, Docker-bridge, and RFC 6598 CGNAT allowed; visible public peers get **403**). Keep host port maps LAN-only.

**Runtime WAN interlock (ACTIVE_MODE, single-owner):** lock `/api/*` except `GET /api/health` and `GET /api/features` when the **visible client IP is public** (not RFC1918 / unique-local / loopback / link-local / RFC 6598 `100.64.0.0/10`). Docker-bridge peers such as `172.17.0.1` on a `0.0.0.0` bind are **not** a runtime lock — Unraid/Docker NAT would otherwise brick LAN single-owner. Tailscale/CGNAT (`100.64.0.0/10`) is also **not** a visible public peer (`is_private` disagrees across CPython 3.12 vs 3.13+). Trusted `X-Forwarded-Proto: https` alone is **not** WAN. A trusted proxy (`PROJECTIONIST_TRUST_PROXY_HEADERS=1`) that reports a public `X-Forwarded-For` **is** WAN. Untrusted forwarded headers never unlock and never set `Secure` cookies (S14).

**Setup handshake is stricter than runtime:** `0.0.0.0` + peer in `172.16.0.0/12` + no trusted proxy → **Public Household** wizard posture (`public_failsafe`). Visible public peer → halt owner create (`halt_wan`): `POST /api/setup/commit` from a raw public client is **403** even with `profile=public` — wizard hide is not the only gate. RFC 6598 `100.64.0.0/10` does not halt. Detection snapshots store bind/peer socket tuples and booleans only — never `Authorization`, cookies, `X-Plex-Token`, or forwarded header values.

### Public household perimeter (ACTIVE_MODE)

There is **no** `/api/auth/` prefix leak. Ingress matches **explicit method+path pairs** in `PUBLIC_HANDSHAKE_EXACT` (`projectionist/web/auth.py`). If a route is not on this list, it needs a session.

**Exhaustive unauthenticated handshake:**

| Method | Path | Notes |
|--------|------|--------|
| `GET` | `/api/health` | Liveness |
| `GET` | `/api/features` | Stripped flags (no guest/tour) |
| `POST` | `/api/access-requests` | Queue only; **3 / IP / hour**; honeypot below |
| `GET` | `/api/invites/validate` | HMAC-verified token; fail closed |
| `POST` | `/api/invites/redeem/local` | Local fallback on the same invite |
| `POST` | `/api/auth/local/login` | Existing local users only |
| `POST` | `/api/auth/plex/pin` | Start PIN; nonce cookie |
| `GET` | `/api/auth/plex/pin/{id}` | Default poll (login/join) completes the household session (cookie + user) even with a leftover cookie. `?peek=1` (Link Plex / ProfilePage) never binds; bind is `POST /api/auth/plex/link`. New Plex identity without invite → **403** |
| `POST` | `/api/auth/plex` | Existing Plex users; new identity without invite → **403** join-link copy |
| `GET` | `/api/auth/oidc/authorize` | If OIDC enabled |
| `GET` | `/api/auth/oidc/callback` | If OIDC enabled |
| `POST` | `/api/auth/logout` | Clears cookie |

Not public: `GET /api/auth/me`, `POST /api/auth/local/register`, `GET /api/guest/tour` (404), whole `/api/auth/` prefix, setup wizard endpoints after ACTIVE_MODE (404). `/api/webhooks/*` stays **secret-gated** (S8). `/mcp` stays **API-key-gated** — do not publish MCP on the WAN hostname.

**Honeypot (`organization_url` on access requests):** hidden field (`display: none`, `aria-hidden`, `tabIndex=-1`). Any non-empty value → **200** with the same `{ "request": { "id", "status", "created_at" } }` shape as a real insert, throwaway UUID **not** written to SQLite, structured log of a ping (peer class / bind — **not** the filled value), **no** owner alert. Bots that fill it never join the queue.

**Invites:** URL token is `invite_id.raw.hmac` (HMAC over session secret). Raw material is hashed at rest. Garbage tokens fail closed without a DB timing oracle. Member insert and `status='redeemed'` happen in **one SQLite transaction**; concurrent double-redeem has one winner. Roles are **owner | member** (+ youth flag). Legacy `guest` rows migrate to `member`.

**Invite-only defaults:** Public Household commit **always** sets invite-only on. Private Household defaults **off** unless the operator explicitly opts in. Private Household commit forces `trust_proxy=false` and clears a sticky TLS-proxy / `household_domain` (choosing Private is not a leftover Public checkbox). `open_auto_provision` is off after wizard commit; lab/CI may set `PROJECTIONIST_ALLOW_OPEN_JOIN=1` for synthetic Plex identities — never the public default.

**Link Plex:** ProfilePage polls `GET /api/auth/plex/pin/{id}?peek=1` (status only — no cookie, no bind). Bind is `POST /api/auth/plex/link` with `{ pin_id, password }` in one payload. Claimed `plex_user_id` is rejected. No display-name matching.

```text
SPA AuthGate ──no session──► /login (glass door) or /join?token=
SETUP_MODE     ──/api/*──► handshake + wizard complete only
ACTIVE_MODE    ──no session──► exhaustive handshake; else 401
```

### Multi-user household

Chat, pending actions, watchlist, reviews, and preferences are scoped by `user_id`. Owner-only routes cover settings, remaining setup tests, sync mutate, and persona/lens writes. The shared library catalog remains household-wide; members see a public-content library browse schema. Login may use Plex PIN, local password (PBKDF2), and/or OIDC depending on `auth_*` flags; `GET /api/features` exposes `auth_methods`. **New** Plex/OIDC identities require a `/join` invite when `features.invite_only` is on (always for Public Household).

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
| **S1** | Critical | Control-plane routes historically lacked session deps. | With `multi_user_enabled=true`, unauthenticated `curl` to settings/chat/sync/confirm. | **Mitigated** | Explicit handshake allowlist; wildcard `/api/auth/` is gone. Single-owner remains LAN-open unless the WAN interlock sees a public client IP. |
| **S2** | Critical | Session secret fell back to a public dev default. | Forge `curatorx_session` cookies for any `user_id`. | **Mitigated** | Auto-generated DATA_DIR secret + refuse enable on public default; still set `PROJECTIONIST_SESSION_SECRET` in production. |
| **S3** | Critical | App binds `0.0.0.0:8788` in Docker / Unraid packaging. | Reach the control plane from any host interface / accidental WAN map. | **Open** | Do not port-forward bare 8788; bind/firewall to LAN or put behind an authenticated reverse proxy. |
| **S4** | High | Plex PIN create/poll without binding / rate limits. | Create/poll unbound PINs; race another client’s PIN once authorized. | **Mitigated** | PIN nonce cookie + per-IP rate limits; residual race risk on shared browser profiles. |
| **S5** | High | Setup tests filled secrets and fetched operator URLs (SSRF). | Hit link-local/metadata URLs with attached saved tokens. | **Mitigated** | Owner-gated + host-matched secrets + link-local/metadata blocks; private LAN targets still allowed for *arr. |
| **S6** | High | Chat threads not filtered by `user_id`. | Read/delete another user’s messages. | **Mitigated** | Chat threads scoped by `user_id` when multi-user is on. |
| **S7** | High | Pending *arr confirms by opaque token only. | Steal/guess a confirmation token and confirm writes. | **Mitigated** | Pending actions store `user_id`; confirm pops only matching tokens. |
| **S8** | High | Empty webhook secret accepted any Plex webhook POST. | Spoof webhook events to queue sync/side effects. | **Mitigated** | Unconfigured or invalid secret → generic 401 (no env var names); header compared with `secrets.compare_digest` when configured. |
| **S9** | Medium | Session cookie lacked `Secure` behind HTTPS proxies. | Weaker cookie story on HTTPS / CSRF edge cases. | **Mitigated** | `Secure` + HSTS only when the request is actually HTTPS (`request.url.scheme` or **trusted** forwarded proto). Untrusted `X-Forwarded-Proto` is ignored. |
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
| **S16** | Medium | Shared repository memory/research returned into any user's LLM context unfenced (stored prompt injection). | Poison a global insight/snapshot; steer another user's tool calls. | **Mitigated** | Tool/memory results fenced as untrusted DATA (`wrap_untrusted_data`); system-prompt clause; CI `tests/test_prompt_injection.py`; pentest `TC-PROMPT-01` runs that suite. Residual: model may still mis-follow fenced text; *arr writes stay confirm-gated. |
| **S17** | High | Docker NAT (`172.17.0.1`) classified as LAN via `is_private`. | Silent Private Household / single-owner on a public VPS bind. | **Mitigated** | Setup handshake treats `0.0.0.0` + `172.16.0.0/12` as Public fail-safe. Runtime WAN interlock **does not** lock Docker-bridge peers (Unraid). RFC 6598 `100.64.0.0/10` (Tailscale/CGNAT) is LAN, not a visible public peer. |
| **S18** | High | Invite redeem created the user then burned the token in a second write. | Crash window: unburned token or orphan user; replay. | **Mitigated** | HMAC on the URL token; hash at rest; insert + redeem in one transaction. |
| **S19** | Medium | Guest role + public `/tour` + open register. | Unauthenticated library browse; third anonymous-ish class. | **Mitigated** | No guest/tour; register 403 for anonymous; `/tour` redirects to `/login`. |
| **S20** | Medium | Access-request form without bot trap / loose rate limit. | Queue flooding; scraper retune. | **Mitigated** | 3/IP/hour; `organization_url` honeypot returns identical 200 JSON, no SQLite row, no owner alert. |
| **S21** | Medium | Two-step Plex link (poll then attach). | Race: bind without password confirm. | **Mitigated** | Single `POST /api/auth/plex/link` with `pin_id` + password; `?peek=1` poll never binds. Default login/join poll still completes the session. |

---

## Operator guidance

1. **Do not expose bare `8788` to the internet.** Put TLS on Caddy/NPM/Cloudflare Tunnel in front; complete the wizard as **Public Household**.
2. Set **`PROJECTIONIST_TRUST_PROXY_HEADERS=1` only behind that trusted proxy.** The wizard “TLS edge” confirm writes the same flag. Untrusted `X-Forwarded-*` is ignored for client IP, rate limits, `Secure` cookies, and WAN unlock.
3. Set **`PROJECTIONIST_SESSION_SECRET`** to a long random value (or accept auto-generated secret under Config). Invite HMACs use this secret.
4. Set a non-empty **webhook secret** if anything outside the host can POST `/api/webhooks/plex`.
5. **Do not publish `/mcp` on the WAN hostname.** Prefer a privacy MCP key for shared clients; full key must differ.
6. Public Household is **invite-only**; mint join links from Admin Access. Private Household invite-only stays off unless you opt in.
7. Restrict who can mount/read the `/config` volume (encrypted secrets + session secret + recovery-key hash).
8. Keep **`PROJECTIONIST_EXPOSE_OPENAPI` unset** in production.
9. After ACTIVE_MODE, setup endpoints **404**. Recovery is owner login + Admin, or `PROJECTIONIST_OWNER_PASSWORD` on LAN — not the wizard.
10. Automat LAN hosts and QA vs prod: [ops/AUTOMAT.md](ops/AUTOMAT.md).

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

How pentest fits with CI, maintainer QA, and Interactive UI QA: [Feature testing environment blueprint](superpowers/specs/2026-07-29-feature-testing-environment-blueprint.md).

## Related docs

- [PRIVACY.md](PRIVACY.md) — plain-language privacy & data use (household + owner; in-app at `/privacy`)
- [MCP.md](MCP.md) — dual-mode MCP keys, schemas, TMDB image policy
- [TESTING.md](TESTING.md) — API authz regression (`tests/test_api_authz.py`)
- [Feature testing environment blueprint](superpowers/specs/2026-07-29-feature-testing-environment-blueprint.md) — layered QA + red-hat protocol
- [security/pentests/README.md](security/pentests/README.md) — repeatable penetration-test protocol
- [CONFIGURATION.md](CONFIGURATION.md) — feature flags and session secret
- [WEB_UI.md](WEB_UI.md) — UI login vs API surface
- [wiki/Home.md](wiki/Home.md) — operator wiki index
