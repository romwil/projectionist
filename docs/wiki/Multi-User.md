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
    "plex_login_enabled": true
  }
}
```

CuratorX refuses to enable multi-user while the public development session secret is in use.

## Partitioning matrix

| Resource | Scope |
|----------|--------|
| Library, embeddings, facets, sync | Shared household |
| Settings / setup tests / library sync mutate | **Owner-only** |
| Persona / lens definitions | Shared read; **owner write** |
| Chat threads / messages | **Per-user** |
| Watchlist | Per-user |
| Named curated lists | Per-user (local; Plex Lists publish deferred) |
| Reviews / preferences | **Per-user** |
| Jobs status | Any authenticated user; mutate owner-only |
| Pending *arr / Seerr confirms | **Per-user** tokens |
| Guest role | Read + chat + watchlist; **no requests / *arr writes** |

## Auth behavior

- Visitors must **Sign in with Plex** (PIN) before the SPA loads
- Middleware requires a session for almost all `/api/*` (allowlist: health, features, `/api/auth/*`, webhooks)
- PIN create/poll are bound with an HttpOnly `plex_pin_nonce` cookie and rate-limited
- Webhooks require a configured secret (`CURATORX_WEBHOOK_SECRET` / `webhook_secret`)
- Cookie `Secure` is set when `X-Forwarded-Proto: https`

First linked Plex account becomes **owner**.

## Not shipped

- OIDC / SSO
- Local username + password accounts

See [../SECURITY.md](../SECURITY.md), [../CONFIGURATION.md](../CONFIGURATION.md), and [Seerr](Seerr.md).
