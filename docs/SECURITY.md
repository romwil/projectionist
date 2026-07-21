# CuratorX security assessment

Living pen-test brief for operators on the current CuratorX product surface. Status values move between **Open**, **Mitigated**, and **Accepted** as findings land — residual notes describe what remains after mitigations.

## Scope

| In scope | Out of scope (for this brief) |
|----------|-------------------------------|
| Web UI + FastAPI control plane (`curatorx/web/`) | Third-party Plex / *arr / Seerr / LLM hosts |
| Optional multi-user auth (Plex PIN, local password, OIDC) + session cookies | Host OS / Unraid / Docker daemon hardening |
| Setup connection tests, chat, jobs, sync, *arr confirm tokens | Supply-chain / dependency CVE hunting |
| Plex webhook ingress | Multi-tenant SaaS isolation |
| Dual-mode MCP + library privacy sanitizers | |
| Default Docker / Unraid packaging assumptions (non-root `curatorx`) | |

**Trust assumption:** CuratorX is a single-owner homelab app. With multi-user **off**, there is no login — anyone who can reach the HTTP port is an effective admin. With multi-user **on**, configured auth methods (Plex PIN / local / OIDC), session cookies, API middleware, and per-user chat/actions partitioning apply — still assume a trusted LAN for default single-owner mode.

## Threat model

### Trusted LAN

Typical Unraid / Docker deploy on a private network. Neighbors on the same VLAN (or a compromised device) can hit `:8788`. Default bind is all interfaces (S3). Single-owner mode has no auth; keep the host on a trusted segment.

### Guest / IoT Wi‑Fi

Guest SSID clients that share L2/L3 with the host are the same as LAN attackers for this app. Treat guest Wi‑Fi as hostile unless the CuratorX host is firewalled to the trusted VLAN only.

### Accidental WAN

Port-forwarding or exposing `8788` (or a reverse proxy without auth) exposes the control plane: settings, library sync, chat (LLM spend), *arr propose/confirm when tokens are known, and setup tests that can use stored secrets. Session forging is trivial if `CURATORX_SESSION_SECRET` is left at the public development default (S2 mitigated via auto-bootstrap + refuse-on-default).

### Multi-user household

When multi-user is enabled, middleware requires a session for almost all `/api/*` (allowlist: health, features, auth, webhooks). Chat, pending actions, watchlist, reviews, and preferences are scoped by `user_id`. Owner-only routes cover settings, setup tests, sync mutate, and persona/lens writes. Guests cannot request media / *arr writes. The shared library catalog remains household-wide; members see a public-content library browse schema. Login may use Plex PIN, local password (PBKDF2), and/or OIDC depending on `auth_*` flags; `GET /api/features` exposes `auth_methods`.

```text
SPA AuthGate ──no session──► /login
Most /api/*  ──no session──► 401 when multi_user_enabled
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

| ID | Severity | Location | Exploit one-liner | Status | Residual risk |
|----|----------|----------|-------------------|--------|---------------|
| **S1** | Critical | Control-plane routes historically lacked session deps. | With `multi_user_enabled=true`, unauthenticated `curl` to settings/chat/sync/confirm. | **Mitigated** | When multi-user is off, the control plane remains open on the LAN by design. |
| **S2** | Critical | Session secret fell back to a public dev default. | Forge `curatorx_session` cookies for any `user_id`. | **Mitigated** | Auto-generated DATA_DIR secret + refuse enable on public default; still set `CURATORX_SESSION_SECRET` in production. |
| **S3** | Critical | App binds `0.0.0.0:8788` in Docker / Unraid packaging. | Reach the control plane from any host interface / accidental WAN map. | **Open** | Do not port-forward bare 8788; bind/firewall to LAN or put behind an authenticated reverse proxy. |
| **S4** | High | Plex PIN create/poll without binding / rate limits. | Create/poll unbound PINs; race another client’s PIN once authorized. | **Mitigated** | PIN nonce cookie + per-IP rate limits; residual race risk on shared browser profiles. |
| **S5** | High | Setup tests filled secrets and fetched operator URLs (SSRF). | Hit link-local/metadata URLs with attached saved tokens. | **Mitigated** | Owner-gated + host-matched secrets + link-local/metadata blocks; private LAN targets still allowed for *arr. |
| **S6** | High | Chat threads not filtered by `user_id`. | Read/delete another user’s messages. | **Mitigated** | Chat threads scoped by `user_id` when multi-user is on. |
| **S7** | High | Pending *arr confirms by opaque token only. | Steal/guess a confirmation token and confirm writes. | **Mitigated** | Pending actions store `user_id`; confirm pops only matching tokens. |
| **S8** | High | Empty webhook secret accepted any Plex webhook POST. | Spoof webhook events to queue sync/side effects. | **Mitigated** | Empty webhook secret → 503; header required when configured. |
| **S9** | Medium | Session cookie lacked `Secure` behind HTTPS proxies. | Weaker cookie story on HTTPS / CSRF edge cases. | **Mitigated** | `Secure` cookie when `X-Forwarded-Proto=https`. |
| **S10** | Medium | Seerr path could skip confirmation. | Tool args submit Seerr requests immediately. | **Mitigated** | Seerr tool path always returns a confirmation token. |
| **S11** | Medium | Settings JSON stores API keys in plaintext under `/config`. | Read volume / backup / host filesystem → fleet credentials. | **Open** | Protect `/config` permissions and backups; treat volume as secret material. |
| **S12** | Low | Docs understated multi-user API enforcement. | Operators misread network-peer risk. | **Mitigated** | Docs + middleware aligned for multi-user. |
| **S13** | Low | Final Docker image runs as root (no `USER`). | Container breakout has root inside the image. | **Mitigated** | Entrypoint script auto-chowns `/config` to `curatorx` (UID/GID 1000) and drops privileges via `gosu`. Compatible with existing root-owned volumes and Kubernetes `runAsUser`. |
| **S14** | High | Rate limiter trusted `X-Forwarded-For` on direct LAN binds. | Rotate spoofed IPs to bypass auth throttles / PIN brute force. | **Mitigated** | Ignore forwarded headers unless `CURATORX_TRUST_PROXY_HEADERS=1`; set that only behind a trusted reverse proxy. |
| **S15** | Medium | FastAPI served `/docs` and `/openapi.json` without auth. | Map mutate endpoints and auth deps from the LAN. | **Mitigated** | Docs disabled by default; set `CURATORX_EXPOSE_OPENAPI=1` for local development only. |
| **P1** | High | Library payloads emitted live `X-Plex-Token` in thumbs. | Privacy MCP / member browse exfiltrates server token. | **Mitigated** | Sanitizer allowlists `image.tmdb.org` only. |
| **P2** | High | Privacy MCP returned `rating_key` and other PMS ids. | Correlate titles to PMS items / probe the media stack. | **Mitigated** | Public schema drops infra ids; privacy mode rejects rating_key title lookups. |
| **P3** | Medium | Privacy / member APIs exposed telemetry, size, *arr flags. | Household inventory leaks to limited apps / members. | **Mitigated** | Public schema drops telemetry/arr/size; optional `watch_state` enum only. |
| **P4** | High | Single shared MCP key with no mode separation. | Compromised limited app inherits full schema / propose tools. | **Mitigated** | Dual keys; equal keys refuse full mode. |
| **P5** | Medium | Authenticated members received owner-grade library JSON. | Member curls dump rating keys, sizes, arr flags. | **Mitigated** | Member browse uses public-content sanitizer when multi-user is on. |
| **P6** | Medium | Full MCP / stdio without a distinct full secret. | Accidental escalate to propose tools. | **Mitigated** | Stdio full requires distinct full key; HTTP maps key → mode. |

---

## Operator guidance

1. **Do not expose `8788` to the internet.** Use LAN-only or an authenticated reverse proxy.
2. Set **`CURATORX_SESSION_SECRET`** to a long random value before enabling multi-user (or accept auto-generated secret under Config).
3. Set a non-empty **webhook secret** if anything outside the host can POST `/api/webhooks/plex`.
4. Keep the host on a **trusted LAN segment**; multi-user is household identity, not internet multi-tenant isolation.
5. Restrict who can mount/read the `/config` volume.
6. Prefer a **privacy MCP key** for shared/third-party clients; only mint `CURATORX_MCP_FULL_API_KEY` for trusted in-stack automation (keys must differ).
7. Leave **`CURATORX_TRUST_PROXY_HEADERS` unset** on direct LAN binds; enable only when a trusted reverse proxy sets client IP headers.
8. Keep **`CURATORX_EXPOSE_OPENAPI` unset** in production; use it only for local API exploration.

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
