# Projectionist security assessment

Living pen-test brief for operators on the current Projectionist product surface. Status values move between **Open**, **Mitigated**, and **Accepted** as findings land — residual notes describe what remains after mitigations.

## Scope

| In scope | Out of scope (for this brief) |
|----------|-------------------------------|
| Web UI + FastAPI control plane (`projectionist/web/`) | Third-party Plex / *arr / Seerr / LLM hosts |
| Optional multi-user auth (Plex PIN, local password, OIDC) + session cookies | Host OS / Unraid / Docker daemon hardening |
| Setup connection tests, chat, jobs, sync, *arr confirm tokens | Supply-chain / dependency CVE hunting |
| Plex webhook ingress | Isolating several households on one server |
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

**Library art (`GET /api/library/art/...`):** session or device-credential only. The server fetches a poster or backdrop from an exact public art host over HTTPS, or from the configured Plex origin for a library thumb path. Redirects that leave that policy are refused, including a public host that bounces to a private address. The response is `Cache-Control: private`.

**Runtime WAN interlock (ACTIVE_MODE, single-owner):** lock `/api/*` except `GET /api/health` and `GET /api/features` when the **visible client IP is public** (not RFC1918 / unique-local / loopback / link-local / RFC 6598 `100.64.0.0/10`). Docker-bridge peers such as `172.17.0.1` on a `0.0.0.0` bind are **not** a runtime lock — Unraid/Docker NAT would otherwise brick LAN single-owner. Tailscale/CGNAT (`100.64.0.0/10`) is also **not** a visible public peer (`is_private` disagrees across CPython 3.12 vs 3.13+). Trusted `X-Forwarded-Proto: https` alone is **not** WAN. The first `X-Forwarded-For` hop is not the client. A listed connector (`PROJECTIONIST_TRUSTED_PROXIES` or `network.trusted_proxies`) that sends `cf-ray` or one `cf-connecting-ip` **is** outside the house, even when the socket address is private (SEC-020). Untrusted forwarded headers never unlock and never set `Secure` cookies (S14). The rate-limit key does not use that first hop: `CF-Connecting-IP` counts only when the socket peer is on that same list (SEC-017).

**Setup handshake is stricter than runtime:** `0.0.0.0` + peer in `172.16.0.0/12` + no trusted proxy → **Public Household** wizard posture (`public_failsafe`). Visible public peer → halt owner create (`halt_wan`): `POST /api/setup/commit` from a raw public client is **403** even with `profile=public` — wizard hide is not the only gate. RFC 6598 `100.64.0.0/10` does not halt. Detection snapshots store bind/peer socket tuples and booleans only — never `Authorization`, cookies, `X-Plex-Token`, or forwarded header values.

### Public household perimeter (ACTIVE_MODE)

There is **no** `/api/auth/` prefix leak. Ingress matches **explicit method+path pairs** in `PUBLIC_HANDSHAKE_EXACT` (`projectionist/web/auth.py`), plus pattern matches: the pair-code poll, and engine playlist and segment URLs. If a route is not one of those, it needs a session.

**Exhaustive unauthenticated handshake:**

| Method | Path | Notes |
|--------|------|--------|
| `GET` | `/api/health` | Liveness |
| `GET` | `/api/features` | Stripped flags (no guest/tour). Also `api_contract` and `capabilities` — names and numbers only, no household secrets |
| `POST` | `/api/access-requests` | Queue only; **3 / IP / hour**; honeypot below |
| `GET` | `/api/invites/validate` | HMAC-verified token; fail closed. Returns the inviter’s display name, role, expiry, Youth flag, and allowed methods — not another member’s email |
| `POST` | `/api/invites/redeem/local` | Local fallback on the same invite. A `client` object returns a device credential instead of a cookie |
| `POST` | `/api/auth/local/login` | Existing local users only. A `client` object returns a device credential instead of a cookie |
| `POST` | `/api/auth/plex/pin` | Start PIN. Browser gets a nonce cookie. A `client` object gets `pin_nonce` in the body and no cookie |
| `GET` | `/api/auth/plex/pin/{id}` | Default poll (login/join) completes the household session (cookie + user) even with a leftover cookie. Native callers send `X-Projectionist-Pin-Nonce` and receive a device credential once. `?peek=1` (Link Plex / ProfilePage) never binds; bind is `POST /api/auth/plex/link`. New Plex identity without invite → **403** |
| `POST` | `/api/auth/plex` | Existing Plex users; new identity without invite → **403** join-link copy. A `client` object returns a device credential instead of a cookie |
| `GET` | `/api/auth/oidc/authorize` | If OIDC enabled. Browser start |
| `POST` | `/api/auth/oidc/authorize` | If OIDC enabled. Native start: PKCE S256, `client` required. The provider redirect stays the configured server callback |
| `GET` | `/api/auth/oidc/callback` | If OIDC enabled. Native state answers 302 to `projectionist://auth/callback` with a single-use code, never the credential |
| `POST` | `/api/auth/oidc/exchange` | If OIDC enabled. Exchanges that code plus the PKCE verifier for a device credential. Single-use, two minutes |
| `POST` | `/api/auth/logout` | Clears cookie |
| `GET` | `/api/mail/unsubscribe` | Signed one-click token (GRO-008); shows a confirm button, changes nothing |
| `POST` | `/api/mail/unsubscribe` | RFC 8058 one-click: turns off one program's email for one person; rejected after "Delete my data" or for another person; security-logged |
| `POST` | `/api/devices/pair/issue` | Apple TV sign-in code. Short code, expiry, pending id. No library data, no device credential. Rate limited |
| `POST` | `/api/devices/pair/rotate` | New code for a pending id. The previous code dies. Unknown or already claimed: tell the TV to issue again |
| `GET` | `/api/devices/pair/pending/{id}` | Pattern match, like the Plex PIN poll. Pending, or the device credential **once** after claim. Not a library read |
| `GET` | `/api/playback/sessions/{id}/{token}/…` | Pattern match. The token in the path is the credential for that session's playlist and segments. Opening the session, progress, and stop still need a member credential. A missing or wrong token is **404**, not a library listing |

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
| **S4** | High | Plex PIN create/poll without binding / rate limits. | Create/poll unbound PINs; race another client’s PIN once authorized. | **Mitigated** | PIN nonce is a cookie for the browser and a response field the native client sends back as `X-Projectionist-Pin-Nonce`. Per-IP rate limits. Residual race risk on shared browser profiles. |
| **S5** | High | Setup tests filled secrets and fetched operator URLs (SSRF). | Hit link-local/metadata URLs with attached saved tokens. | **Mitigated** | Owner-gated + host-matched secrets + link-local/metadata blocks; private LAN targets still allowed for *arr. |
| **S6** | High | Chat threads not filtered by `user_id`. | Read/delete another user’s messages. | **Mitigated** | Chat threads scoped by `user_id` when multi-user is on. |
| **S7** | High | Pending *arr confirms by opaque token only. | Steal/guess a confirmation token and confirm writes. | **Mitigated** | Pending actions store `user_id`; confirm pops only matching tokens. |
| **S8** | High | Empty webhook secret accepted any Plex webhook POST. | Spoof webhook events to queue sync/side effects. | **Mitigated** | Unconfigured or invalid secret → generic 401 (no env var names); header compared with `secrets.compare_digest` when configured. |
| **S9** | Medium | Session cookie lacked `Secure` behind HTTPS proxies. | Weaker cookie story on HTTPS / CSRF edge cases. | **Mitigated** | `Secure` + HSTS only when the request is actually HTTPS (`request.url.scheme` or **trusted** forwarded proto). Untrusted `X-Forwarded-Proto` is ignored. |
| **S10** | Medium | Seerr path could skip confirmation. | Tool args submit Seerr requests immediately. | **Mitigated** | Seerr tool path always returns a confirmation token. |
| **S11** | Medium | Settings JSON stores API keys in plaintext under `/config`. | Read volume / backup / host filesystem → fleet credentials. | **Mitigated** | File mode `0600` on every save. **H4 Hybrid:** UI-persisted secrets are encrypted at rest (`PROJECTIONIST_SECRETS_KEY` or material derived from the session secret); env-supplied secrets still win and are not written back as plaintext. Back up the secrets key with `/config` (see [Rotating secrets & keys](#rotating-secrets--keys) and [DOCKER.md](DOCKER.md) backups). |
| **S12** | Low | Docs understated multi-user API enforcement. | Operators misread network-peer risk. | **Mitigated** | Docs + middleware aligned for multi-user. |
| **S13** | Low | Final Docker image runs as root (no `USER`). | Container breakout has root inside the image. | **Mitigated** | Entrypoint script auto-chowns `/config` to `curatorx` (UID/GID 1000) and drops privileges via `gosu`. Compatible with existing root-owned volumes and Kubernetes `runAsUser`. |
| **S14** | High | Rate limiter trusted `X-Forwarded-For` on direct LAN binds. | Rotate spoofed IPs to bypass auth throttles / PIN brute force. | **Mitigated** | The rate-limit key never uses the first `X-Forwarded-For` hop. `CF-Connecting-IP` is used only when the direct peer is on the trusted-proxy list (SEC-017). `PROJECTIONIST_TRUST_PROXY_HEADERS` still gates `Secure` cookies and forwarded protocol, not the rate-limit key. |
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
2. Set **`PROJECTIONIST_TRUST_PROXY_HEADERS=1` only behind that trusted proxy.** The wizard “TLS edge” confirm writes the same flag. It allows `Secure` cookies and a forwarded protocol. It does not choose the rate-limit address. Set **`PROJECTIONIST_TRUSTED_PROXIES`** to the tunnel connector (one IP or CIDR, comma-separated), for example `127.0.0.1`. Only that peer may supply `CF-Connecting-IP`. A wide range means every peer in it can name the client. Untrusted forwarding headers never change the rate-limit key.
3. Set **`PROJECTIONIST_SESSION_SECRET`** to a long random value (or accept auto-generated secret under Config). Invite HMACs use this secret.
4. Set a non-empty **webhook secret** if anything outside the host can POST `/api/webhooks/plex`.
5. **Do not publish `/mcp` on the WAN hostname.** Prefer a privacy MCP key for shared clients; full key must differ.
6. Public Household is **invite-only**; mint join links from Admin Access. Private Household invite-only stays off unless you opt in.
7. Restrict who can mount/read the `/config` volume (encrypted secrets + session secret + recovery-key hash).
8. Keep **`PROJECTIONIST_EXPOSE_OPENAPI` unset** in production.
9. After ACTIVE_MODE, setup endpoints **404**. Recovery is owner login + Admin, or `PROJECTIONIST_OWNER_USERNAME` + `PROJECTIONIST_OWNER_PASSWORD` and a restart (the username must match the existing owner) — not the wizard. See [Owner recovery](HELP.md#owner-recovery).
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

## Roadmap items

Public front door (accepted 2026-11-24). The household sign-in is the login on the public hostname. These items close the gaps that login has to stand on. SEC-017 through SEC-022 are the gate: they have to be on production and checked before anyone removes the extra login in front of the hostname. That removal is a separate decision. Nothing here publishes a new image.

How the rate-limit address works today:

```bash
# Connector address. Only this peer's CF-Connecting-IP becomes the client key.
PROJECTIONIST_TRUSTED_PROXIES=127.0.0.1
```

The same list can live in `{DATA_DIR}/settings.json` under `network.trusted_proxies`. The environment variable wins when it is set.

| ID | Title | Why | Done when | Depends on | Status |
|----|-------|-----|-----------|------------|--------|
| SEC-017 | Use the tunnel client address for rate limits | A person on the public hostname is counted as themselves. A caller who invents a forwarding header is not. | A peer that is not on the trusted-proxy list keeps its socket address as the rate-limit key when `X-Forwarded-For` and `CF-Connecting-IP` are set. A listed peer uses `CF-Connecting-IP` when that header is one valid IP. Two such clients get separate buckets. The first `X-Forwarded-For` hop is never the key. | — | done |
| SEC-018 | Throttle sign-in failures per account | Guessing a password or an invite cannot be spread across addresses. | Ten failed local sign-ins for one username, and ten failed invite redeems for one invite, lock for 15 minutes. Further groups of failures double that, up to 24 hours. A success clears the count. The error is the same whether or not the account or invite exists. The owner sees the lock in Admin → Health and Logs. | SEC-017 | done |
| SEC-019 | Require a second factor for owner accounts | An owner password alone is not enough on a public hostname. | The owner, and any admin role, signs in with Plex or OIDC, or with a local password plus TOTP. Enrollment returns recovery codes once. Members may keep a local password; a new or changed one is refused when it is too short or on the bundled common-password list. An owner setting can require TOTP for every local password. | SEC-018 | done |
| SEC-020 | Treat the tunnel as outside the house | A request that arrived through the connector is external even when the socket address is private. | A request that carries `cf-ray` or `cf-connecting-ip` from a trusted connector is external. When a public base URL is set, household login cannot be turned off, and setup cannot be re-entered from an external request. | SEC-017 | done |
| SEC-021 | Keep private responses out of shared caches | A shared cache must not store a member's art, playlist, subtitle, avatar, or API response. | Art, engine and library-path playlists and segments, subtitles, avatars, and every `/api/` response send `Cache-Control: private, no-store` or `private, max-age=…`. Content-addressed static assets stay long-lived and public. Tests cover each group. | — | done |
| SEC-022 | Give anonymous callers only the sign-in card | The sign-in screen learns how to sign in, and not where the house lives or what is on the shelf. | A session-less `GET /api/features`, with household login on, returns capability flags and sign-in methods. It does not return home or away addresses, the household domain, library or *arr facts, or the server version string. | — | done |
| SEC-023 | Check the origin on cookie writes | A browser on another site cannot use the household cookie. | Unsafe methods whose `Origin` or `Referer` is not the configured public origin or the LAN origin are rejected when the caller is using the session cookie. Bearer-token clients are exempt. | SEC-020 | accepted |
| SEC-024 | Keep MCP on the LAN unless the owner says otherwise | The tool endpoint is not part of the public sign-in surface. | An external request (SEC-020) to `/mcp` is refused unless the owner turns on remote MCP. Failed MCP authentication is logged. | SEC-020 | accepted |
| SEC-025 | Notice a new sign-in | The owner and the account holder hear about a new device or browser. | A new device or browser signing in to any account writes an inbox letter for the owner and, when an email is set, for the account holder. Push stays the existing content-free path (NAT-006) and is not sent by this item. The owner can revoke the device from Settings → Devices. | NAT-005 | accepted |
| SEC-026 | Review the public handshake | The routes that answer before sign-in are listed, and each token is hard to guess. | Every `PUBLIC_HANDSHAKE_EXACT` entry and the path-token patterns (engine media, PIN poll, pair pending) are checked for at least 128 bits of token entropy, a TTL, and a rate limit. No response reveals whether an account exists. The findings are written in this file. | SEC-017, SEC-018 | accepted |

**Honest limits.** Until the connector is listed, everyone behind it shares the connector's rate-limit bucket. That is tighter than a spoofed address, and it is not a separate bucket per person. A listed connector that sends `cf-ray` or `cf-connecting-ip` is outside the house, even when its socket address is private. The first `X-Forwarded-For` hop is not that signal, and it is not the home address. Single-owner mode has no sign-in, so `GET /api/features` on the LAN still returns the household payload. A public address keeps household login on, and an external request cannot open setup again. Every `/api/` response is private, so a shared cache does not keep art, playlists, segments, subtitles, or avatars. Content-addressed frontend files stay public for a year. TOTP secrets and recovery-code hashes are household credentials, stored like other secrets, and are not written to logs. The common-password check is a bundled list on disk. It does not call out to a breach API. The browser that finishes first-run setup is signed in for that session. The next local sign-in needs the code. Until a code is confirmed, a correct password returns the setup key instead of a session.

**Client contract.** SEC-017 through SEC-021 and SEC-023 through SEC-024 do not add a route. SEC-019 adds an optional sign-in code on the existing local login. A wrong password and a missing account stay the same error. After the password matches, a missing code can say that a sign-in code is required. SEC-022 keeps the anonymous `GET /api/features` shape already returned when household login is on: `features` (only `multi_user_enabled` and `access_requests_enabled`), `auth_methods`, `sign_in`, `setup_state`, `authenticated`, `user`, `api_contract`, and `capabilities`. SEC-025 uses the inbox the household already has. No new capability number is required for these items. Push remains `push: 0` until NAT-006.

**Privacy.** Rate-limit keys and lock timers stay in process memory. A lock audit row names the account or the invite id, not the password or the invite token. A new-sign-in letter names the account and the kind of sign-in, not the film library.

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
