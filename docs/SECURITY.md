# CuratorX security assessment

Living pen-test brief for operators and for the Pre-CA / **1.2** hardening track. Status values will move from **Open** to **Mitigated** (or **Accepted**) as Workstream B lands — do not treat this file as a claim that issues are already closed.

## Scope

| In scope | Out of scope (for this brief) |
|----------|-------------------------------|
| Web UI + FastAPI control plane (`curatorx/web/`) | Third-party Plex / *arr / Seerr / LLM hosts |
| Optional multi-user Plex PIN auth + session cookies | Full OIDC / local-password auth (not shipped) |
| Setup connection tests, chat, jobs, sync, *arr confirm tokens | Host OS / Unraid / Docker daemon hardening |
| Plex webhook ingress | Supply-chain / dependency CVE hunting |
| Default Docker / Unraid packaging assumptions | Multi-tenant SaaS isolation |

**Trust assumption today:** CuratorX is a single-owner homelab app. With multi-user **off**, there is no login — anyone who can reach the HTTP port is an effective admin. Multi-user adds an identity layer, SPA login gate, and (as of 1.2) API middleware plus per-user chat/actions partitioning — still assume a trusted LAN for default single-owner mode.

## Threat model

### Trusted LAN

Typical Unraid / Docker deploy on a private network. Neighbors on the same VLAN (or a compromised device) can hit `:8788`. Default bind is all interfaces (S3). Single-owner mode has no auth; multi-user UI gating does not stop raw `curl` to most `/api/*` (S1).

### Guest / IoT Wi‑Fi

Guest SSID clients that share L2/L3 with the host are the same as LAN attackers for this app. Treat guest Wi‑Fi as hostile unless the CuratorX host is firewalled to the trusted VLAN only.

### Accidental WAN

Port-forwarding or exposing `8788` (or a reverse proxy without auth) exposes the full control plane: settings, library sync, chat (LLM spend), *arr propose/confirm when tokens are known, and setup tests that can use stored secrets (S5). Session forging is trivial if `CURATORX_SESSION_SECRET` is left at the public default (S2).

### Multi-user household

Owner vs member roles exist in the DB and gate **some** routes (watchlist, user admin, some Seerr/collections). Chat threads, settings, sync/jobs, and *arr confirm remain effectively household-shared or anonymous at the API (S1, S6, S7). A member (or guest with network access) can read/write other members’ chat and confirm pending actions if they obtain tokens.

```text
SPA AuthGate ──blocks browser──► /login
Most /api/*  ──curl without cookie──► still succeeds when multi_user_enabled
```

### MCP & privacy (dual-mode)

CuratorX exposes optional MCP over stdio and HTTP (`/mcp`). Trust is selected by **which API key** is presented — never by a client-supplied mode flag.

| Mode | Credential | Schema | Tools |
|------|------------|--------|-------|
| **privacy** | `CURATORX_MCP_API_KEY` | Public content (titles/metadata; TMDB CDN images only) | Read-only library tools |
| **full** | `CURATORX_MCP_FULL_API_KEY` (must differ from privacy key) | Internal fields (`rating_key`, watch telemetry, *arr flags) **minus** live `X-Plex-Token` URLs | Read tools + confirm-gated `propose_*` / `confirm_pending_action` |

Stdio: `CURATORX_MCP_MODE=privacy|full`; full requires a distinct `CURATORX_MCP_FULL_API_KEY` in the environment. Shared sanitizers in [`curatorx/privacy/`](../curatorx/privacy/) also redact `/api/library/*` browse JSON for non-owner members when multi-user is on.

See [MCP.md](MCP.md) and [PRIVACY.md](PRIVACY.md).

---

## Findings

Statuses reflect the 1.2 hardening track plus Pre-CA / **1.3** privacy workstreams. Residual risk is what remains after mitigations.

| ID | Severity | Location | Exploit one-liner | Status | Residual risk |
|----|----------|----------|-------------------|--------|---------------|
| **S1** | Critical | [`curatorx/web/app.py`](../curatorx/web/app.py) — e.g. `GET/PUT /api/settings`, `POST /api/chat`, `POST /api/library/sync`, `POST /api/actions/confirm` lack `Depends(get_current_user_dep)` / `require_role`; only a minority of routes use auth deps (watchlist, some users/reviews/Seerr). Helpers in [`curatorx/web/auth.py`](../curatorx/web/auth.py) (`get_current_user`, `require_role`). | With `multi_user_enabled=true`, `curl` settings/chat/sync/confirm without a session cookie. | **Mitigated** | When multi-user is off, the control plane remains open on the LAN by design. |
| **S2** | Critical | [`curatorx/web/session_tokens.py`](../curatorx/web/session_tokens.py) — `_secret()` defaults to `"curatorx-dev-session-secret"` when `CURATORX_SESSION_SECRET` unset. | Forge `curatorx_session` HMAC cookies for any `user_id` (e.g. owner). | **Mitigated** | Auto-generated DATA_DIR secret + refuse enable on public default; still set CURATORX_SESSION_SECRET in production. |
| **S3** | Critical | [`curatorx/web/__main__.py`](../curatorx/web/__main__.py) (`host="0.0.0.0"`, `PORT` default `8788`); Docker / Unraid publish [`Dockerfile`](../Dockerfile), [`docker-compose.yml`](../docker-compose.yml), [`templates/curatorx.xml`](../templates/curatorx.xml). | Reach the control plane from any host interface / accidental WAN map. | **Open** | Do not port-forward bare 8788; bind/firewall to LAN or put behind an authenticated reverse proxy. |
| **S4** | High | [`curatorx/web/auth.py`](../curatorx/web/auth.py) `start_plex_pin_login` / `poll_plex_pin_login`; routes `POST /api/auth/plex/pin`, `GET /api/auth/plex/pin/{pin_id}` in [`app.py`](../curatorx/web/app.py). No PIN-session binding or per-IP rate limit. | Create/poll PINs unbound; race another client’s PIN id once authorized. | **Mitigated** | PIN nonce cookie + per-IP rate limits; residual race risk on shared browser profiles. |
| **S5** | High | [`curatorx/web/app.py`](../curatorx/web/app.py) `/api/setup/test/*`; [`curatorx/web/setup.py`](../curatorx/web/setup.py) `resolve_test_payload` / `test_*` — fills empty fields from stored settings/secrets and fetches arbitrary operator-supplied URLs with no SSRF allowlist. | Post a link-local/metadata URL (or mismatch host) and attach saved API tokens via empty-field fill. | **Mitigated** | Owner-gated + host-matched secrets + link-local/metadata blocks; private LAN targets still allowed for *arr. |
| **S6** | High | [`curatorx/web/app.py`](../curatorx/web/app.py) chat thread list/get/delete/post (`list_chat_threads`, `get_chat_thread` without `user_id`); schema column exists in [`curatorx/library/db.py`](../curatorx/library/db.py) (`chat_sessions.user_id`) but API does not filter. | Enumerate `/api/chat/threads` and read/delete another user’s messages. | **Mitigated** | Chat threads scoped by `user_id` when multi-user is on. |
| **S7** | High | [`curatorx/library/db.py`](../curatorx/library/db.py) `pending_actions` table (token, action_type, payload — no `user_id`); [`app.py`](../curatorx/web/app.py) `POST /api/actions/confirm` pops/executes by token only. | Steal/guess a confirmation token from chat/UI and confirm *arr/Seerr writes. | **Mitigated** | Pending actions store `user_id`; confirm pops only matching tokens. |
| **S8** | High | [`curatorx/web/webhooks.py`](../curatorx/web/webhooks.py) — if `webhook_secret` empty, `POST /api/webhooks/plex` accepts without header. Documented in [`CONFIGURATION.md`](CONFIGURATION.md). | Spoof Plex webhook events to queue sync/side effects. | **Mitigated** | Empty webhook secret → 503; header required when configured. |
| **S9** | Medium | [`curatorx/web/auth.py`](../curatorx/web/auth.py) `set_session_cookie` — `HttpOnly` + `SameSite=Lax`, no `Secure` flag / CSRF double-submit. | On HTTPS sites or cross-site Lax edge cases, cookie theft via MITM or weaker CSRF story. | **Mitigated** | `Secure` cookie when `X-Forwarded-Proto=https`. |
| **S10** | Medium | [`curatorx/agent/tools.py`](../curatorx/agent/tools.py) Seerr path honors `require_confirmation=false` and submits immediately. | Model/tool args skip the confirm gate for Seerr requests. | **Mitigated** | Seerr tool path always returns a confirmation token. |
| **S11** | Medium | Settings JSON under `DATA_DIR` / `/config` (`settings.json`) via [`curatorx/config_store`](../curatorx/config_store.py) + [`app.py`](../curatorx/web/app.py) save path — API keys and tokens in plaintext on disk. | Read volume / backup / host filesystem → fleet credentials. | **Open** | Protect `/config` permissions and backups; treat volume as secret material. |
| **S12** | Low | Docs historically claimed multi-user “enforces” API auth ([`CONFIGURATION.md`](CONFIGURATION.md), [`WEB_UI.md`](WEB_UI.md), [`wiki/Multi-User.md`](wiki/Multi-User.md)). | Operators assume network peers cannot hit `/api` without login. | **Mitigated** | Docs + API middleware aligned for multi-user 1.2. |
| **S13** | Low | [`Dockerfile`](../Dockerfile) — final image runs as root (no `USER`). | Container breakout has root inside the image. | **Open** | Drop privileges / non-root user in a later packaging pass; rely on Docker/Unraid isolation meantime. |
| **P1** | High | MCP / library payloads emitted `poster_url` / `backdrop_url` with live `X-Plex-Token` (Plex thumbs from sync). | Holder of privacy MCP key or member curling `/api/library` exfiltrates server token. | **Mitigated** | Sanitizer allowlists `image.tmdb.org` only; tokenized non-TMDB URLs cleared for all audiences. |
| **P2** | High | Privacy MCP tools returned `rating_key` and other Plex infrastructure ids. | Correlate titles to PMS items / probe the media stack. | **Mitigated** | Public schema drops `rating_key` (and related plex ids); privacy mode rejects rating_key title lookups. |
| **P3** | Medium | Privacy MCP / member APIs exposed raw view/added timestamps, file sizes, `in_radarr`/`in_sonarr`. | Household telemetry + *arr inventory leaks to limited apps / members. | **Mitigated** | Public schema drops telemetry/arr/size; optional `watch_state` enum only. |
| **P4** | High | Single shared MCP key with no mode separation invited oversharing into write-capable or internal-schema clients. | Compromised limited app inherits full library schema / future writes. | **Mitigated** | Dual keys (`CURATORX_MCP_API_KEY` vs `CURATORX_MCP_FULL_API_KEY`); equal keys refuse full mode. |
| **P5** | Medium | Authenticated members received the same internal library JSON as owners. | Member curls dump rating keys, sizes, arr flags. | **Mitigated** | `/api/library/*` browse + title detail sanitize with `audience=member` when multi-user on and role ≠ owner. |
| **P6** | Medium | Full MCP / stdio could be enabled accidentally without a distinct full secret. | Laptop stdio or mis-set env escalates to propose tools. | **Mitigated** | Stdio full requires distinct `CURATORX_MCP_FULL_API_KEY`; HTTP maps key → mode; propose tools error in privacy mode. |

---

## Operator mitigations (until 1.2)

1. **Do not expose `8788` to the internet.** Use LAN-only or an authenticated reverse proxy.
2. Set **`CURATORX_SESSION_SECRET`** to a long random value before enabling multi-user.
3. Set a non-empty **webhook secret** if anything outside the host can POST `/api/webhooks/plex`.
4. Treat multi-user as a **household convenience + UI gate**, not as API isolation — keep the host on a trusted segment.
5. Restrict who can mount/read the `/config` volume.
6. Prefer a **privacy MCP key** for shared/third-party clients; only mint `CURATORX_MCP_FULL_API_KEY` for trusted in-stack automation (keys must differ).

## Related docs

- [PRIVACY.md](PRIVACY.md) — plain-language privacy & data use (household + owner; in-app at `/privacy`)
- [MCP.md](MCP.md) — dual-mode MCP keys, schemas, TMDB image policy
- [TESTING.md](TESTING.md) — API authz regression outline (`tests/test_api_authz.py`)
- [CONFIGURATION.md](CONFIGURATION.md) — feature flags and session secret
- [WEB_UI.md](WEB_UI.md) — UI login vs API surface
- [wiki/Home.md](wiki/Home.md) — operator wiki index
