# Multi-User

CuratorX is a **single-owner** app by default — no login screen.

## Enabling household mode

In Configuration (or `settings.json`):

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

When enabled:

- Visitors must sign in via **Sign in with Plex** (plex.tv PIN / link flow — same pattern as Overseerr / Seerr) before the **SPA** loads the main UI
- The first linked account becomes the **owner**
- Watchlists and some admin routes already use the session; **API-wide enforcement and per-user chat partitioning land in 1.2** — today treat multi-user as a UI gate on a trusted LAN (see [SECURITY.md](../SECURITY.md))

No OAuth callback URL is required for reverse proxies; the server talks to plex.tv and sets CuratorX’s session cookie. Token paste on `/login` is an advanced fallback only.

The **Plex server token** in Config (library sync) is separate from household sign-in.

Honest current state: **UI gate today; API enforcement in progress for 1.2.**

## Not shipped

- OIDC / SSO
- Local username + password accounts

Those flags may appear in settings schemas as placeholders — do not expect them to authenticate users yet.

## Owner tasks

- Start library sync from **Config** (prefer Config over `/sync` in chat when multi-user is on)
- Manage feature flags and service credentials
- Approve / perform fleet-changing Radarr/Sonarr actions; treat the host as trusted until 1.2 API auth ships

See [../CONFIGURATION.md](../CONFIGURATION.md#feature-flags-optional-off-by-default), [../SECURITY.md](../SECURITY.md), and [Seerr](Seerr.md).
