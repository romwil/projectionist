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

**Trust assumption today:** CuratorX is a single-owner homelab app. With multi-user **off**, there is no login — anyone who can reach the HTTP port is an effective admin. Multi-user adds an identity layer and **SPA login gate**; it does **not** yet enforce a full API trust boundary (see S1).

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

---

## Findings

All items below are **Open** until mitigations merge. “Residual risk” is what operators should assume **today**.

| ID | Severity | Location | Exploit one-liner | Status | Residual risk |
|----|----------|----------|-------------------|--------|---------------|
| **S1** | Critical | [`curatorx/web/app.py`](../curatorx/web/app.py) — e.g. `GET/PUT /api/settings`, `POST /api/chat`, `POST /api/library/sync`, `POST /api/actions/confirm` lack `Depends(get_current_user_dep)` / `require_role`; only a minority of routes use auth deps (watchlist, some users/reviews/Seerr). Helpers in [`curatorx/web/auth.py`](../curatorx/web/auth.py) (`get_current_user`, `require_role`). | With `multi_user_enabled=true`, `curl` settings/chat/sync/confirm without a session cookie. | **Open** | UI login is cosmetic for API; network peer = admin for unprotected routes. Mitigation planned for 1.2 (global API auth when multi-user is on). |
| **S2** | Critical | [`curatorx/web/session_tokens.py`](../curatorx/web/session_tokens.py) — `_secret()` defaults to `"curatorx-dev-session-secret"` when `CURATORX_SESSION_SECRET` unset. | Forge `curatorx_session` HMAC cookies for any `user_id` (e.g. owner). | **Open** | Anyone who knows/guesses the default secret owns all sessions. Set a long random secret before enabling multi-user; refuse default in 1.2. |
| **S3** | Critical | [`curatorx/web/__main__.py`](../curatorx/web/__main__.py) (`host="0.0.0.0"`, `PORT` default `8788`); Docker / Unraid publish [`Dockerfile`](../Dockerfile), [`docker-compose.yml`](../docker-compose.yml), [`templates/curatorx.xml`](../templates/curatorx.xml). | Reach the control plane from any host interface / accidental WAN map. | **Open** | Do not port-forward bare 8788; bind/firewall to LAN or put behind an authenticated reverse proxy. |
| **S4** | High | [`curatorx/web/auth.py`](../curatorx/web/auth.py) `start_plex_pin_login` / `poll_plex_pin_login`; routes `POST /api/auth/plex/pin`, `GET /api/auth/plex/pin/{pin_id}` in [`app.py`](../curatorx/web/app.py). No PIN-session binding or per-IP rate limit. | Create/poll PINs unbound; race another client’s PIN id once authorized. | **Open** | On exposed installs, abuse plex.tv login flow / steal completed PIN sessions. Bind PIN to HttpOnly nonce + rate-limit in 1.2. |
| **S5** | High | [`curatorx/web/app.py`](../curatorx/web/app.py) `/api/setup/test/*`; [`curatorx/web/setup.py`](../curatorx/web/setup.py) `resolve_test_payload` / `test_*` — fills empty fields from stored settings/secrets and fetches arbitrary operator-supplied URLs with no SSRF allowlist. | Post a link-local/metadata URL (or mismatch host) and attach saved API tokens via empty-field fill. | **Open** | Unauthenticated (today) or owner-compromised tests can probe internal network with secrets. Owner auth + URL allowlist + host-matched secrets planned for 1.2. |
| **S6** | High | [`curatorx/web/app.py`](../curatorx/web/app.py) chat thread list/get/delete/post (`list_chat_threads`, `get_chat_thread` without `user_id`); schema column exists in [`curatorx/library/db.py`](../curatorx/library/db.py) (`chat_sessions.user_id`) but API does not filter. | Enumerate `/api/chat/threads` and read/delete another user’s messages. | **Open** | Household chat is not partitioned at the API. Wire `user_id` on create + filter in 1.2. |
| **S7** | High | [`curatorx/library/db.py`](../curatorx/library/db.py) `pending_actions` table (token, action_type, payload — no `user_id`); [`app.py`](../curatorx/web/app.py) `POST /api/actions/confirm` pops/executes by token only. | Steal/guess a confirmation token from chat/UI and confirm *arr/Seerr writes. | **Open** | Token knowledge = write access, any identity. Bind pending actions to session user in 1.2. |
| **S8** | High | [`curatorx/web/webhooks.py`](../curatorx/web/webhooks.py) — if `webhook_secret` empty, `POST /api/webhooks/plex` accepts without header. Documented in [`CONFIGURATION.md`](CONFIGURATION.md). | Spoof Plex webhook events to queue sync/side effects. | **Open** | Set `CURATORX_WEBHOOK_SECRET` (or Config) on any non-isolated install; reject unsigned webhooks in CA/production profile in 1.2. |
| **S9** | Medium | [`curatorx/web/auth.py`](../curatorx/web/auth.py) `set_session_cookie` — `HttpOnly` + `SameSite=Lax`, no `Secure` flag / CSRF double-submit. | On HTTPS sites or cross-site Lax edge cases, cookie theft via MITM or weaker CSRF story. | **Open** | Prefer HTTPS; set `Secure` when `X-Forwarded-Proto=https` / force flag in 1.2. |
| **S10** | Medium | [`curatorx/agent/tools.py`](../curatorx/agent/tools.py) Seerr path honors `require_confirmation=false` and submits immediately. | Model/tool args skip the confirm gate for Seerr requests. | **Open** | LLM or crafted tool args can fire Seerr writes without UI confirm. Always gate in 1.2. |
| **S11** | Medium | Settings JSON under `DATA_DIR` / `/config` (`settings.json`) via [`curatorx/config_store`](../curatorx/config_store.py) + [`app.py`](../curatorx/web/app.py) save path — API keys and tokens in plaintext on disk. | Read volume / backup / host filesystem → fleet credentials. | **Open** | Protect `/config` permissions and backups; treat volume as secret material. |
| **S12** | Low | Docs historically claimed multi-user “enforces” API auth ([`CONFIGURATION.md`](CONFIGURATION.md), [`WEB_UI.md`](WEB_UI.md), [`wiki/Multi-User.md`](wiki/Multi-User.md)). | Operators assume network peers cannot hit `/api` without login. | **Open** (docs corrected in this assessment pass; code still open under S1) | Trust UI-only messaging until 1.2 API middleware ships. |
| **S13** | Low | [`Dockerfile`](../Dockerfile) — final image runs as root (no `USER`). | Container breakout has root inside the image. | **Open** | Drop privileges / non-root user in a later packaging pass; rely on Docker/Unraid isolation meantime. |

---

## Operator mitigations (until 1.2)

1. **Do not expose `8788` to the internet.** Use LAN-only or an authenticated reverse proxy.
2. Set **`CURATORX_SESSION_SECRET`** to a long random value before enabling multi-user.
3. Set a non-empty **webhook secret** if anything outside the host can POST `/api/webhooks/plex`.
4. Treat multi-user as a **household convenience + UI gate**, not as API isolation — keep the host on a trusted segment.
5. Restrict who can mount/read the `/config` volume.

## Related docs

- [TESTING.md](TESTING.md) — API authz regression outline (`tests/test_api_authz.py`)
- [CONFIGURATION.md](CONFIGURATION.md) — feature flags and session secret
- [WEB_UI.md](WEB_UI.md) — UI login vs API surface
- [wiki/Home.md](wiki/Home.md) — operator wiki index
