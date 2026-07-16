# Multi-User

CuratorX is a **single-owner** app by default — no login screen. With `features.multi_user_enabled`, it becomes a household identity + API trust boundary.

## Enabling household mode

1. Prefer setting `CURATORX_SESSION_SECRET` (or let CuratorX auto-generate `session_secret` under Config).
2. In Configuration (or `settings.json`):

```json
{
  "features": {
    "multi_user_enabled": true
  },
  "auth": {
    "mode": "plex",
    "plex_login_enabled": true,
    "local_login_enabled": false,
    "oidc_enabled": false
  }
}
```

CuratorX refuses to enable multi-user while the public development session secret is in use. You can enable more than one login method; the login page shows whatever `GET /api/features` reports in `auth_methods`.

### Auth methods

| Method | Flags | Notes |
|--------|-------|-------|
| **Plex PIN** | `plex_login_enabled` | Overseerr-style plex.tv link flow; first linked account becomes owner |
| **Local password** | `local_login_enabled` | Owner registration with PBKDF2-HMAC-SHA256 |
| **OIDC** | `oidc_enabled` + issuer / client id / secret / redirect | Authelia, Authentik, Keycloak, etc. |

## Partitioning matrix

| Resource | Scope |
|----------|--------|
| Library, embeddings, facets, sync | Shared household |
| Settings / setup tests / library sync mutate | **Owner-only** |
| Persona / lens definitions | Shared read; **owner write** |
| Chat threads / messages | **Per-user** |
| Watchlist | Per-user |
| Named curated lists | Per-user (local; Plex Lists publish deferred) |
| Peer recommendations | Per-user inbox |
| Reviews / preferences | **Per-user** |
| UI font size | Per-user (`ui_font_size`) |
| Jobs status | Any authenticated user; mutate owner-only |
| Pending *arr / Seerr confirms | **Per-user** tokens |
| Guest role | Read + chat + watchlist; **no requests / *arr writes** |

## Auth behavior

- Visitors must sign in (configured methods) before the SPA loads
- Middleware requires a session for almost all `/api/*` (allowlist: health, features, `/api/auth/*`, webhooks)
- Plex PIN create/poll are bound with an HttpOnly `plex_pin_nonce` cookie and rate-limited
- OIDC uses a state parameter (CSRF) on the authorize flow
- Webhooks require a configured secret (`CURATORX_WEBHOOK_SECRET` / `webhook_secret`)
- Cookie `Secure` is set when `X-Forwarded-Proto: https`

See [../SECURITY.md](../SECURITY.md), [../CONFIGURATION.md](../CONFIGURATION.md), and [Seerr](Seerr.md).
