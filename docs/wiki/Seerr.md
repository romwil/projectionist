# Seerr

Seerr (Overseerr / Jellyseerr-compatible request apps) is an **optional** integration for household discovery and requests. It is **off by default**.

## Enable

```json
{
  "features": {
    "seerr_enabled": true,
    "multi_user_enabled": true
  },
  "seerr": {
    "url": "http://seerr:5055",
    "api_key": "…",
    "link_on_login": true
  }
}
```

Typical pattern: turn on **multi-user** + **seerr**, sign in with Plex, and let CuratorX link the Seerr user on login when configured.

## What it does

- Lets members request titles through the Seerr path instead of writing directly to Radarr/Sonarr
- Keeps owner fleet credentials in CuratorX Config

## What it does not do

- Replace Radarr/Sonarr for the owner’s confirmation-gated add flow
## Not planned here

- Provide Seerr-native login inside CuratorX (use CuratorX multi-user: Plex PIN, local password, and/or OIDC instead)

See [Multi-User](Multi-User.md) and [../CONFIGURATION.md](../CONFIGURATION.md).
