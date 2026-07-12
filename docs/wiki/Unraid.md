# Unraid

CuratorX is packaged for Unraid Community Applications as a single container with one config volume.

## Install from template

1. In Unraid, open **Apps** (Community Applications).
2. Search for **CuratorX**, or add the template from this repo:
   - `templates/curatorx.xml`
   - `unraid/curatorx.xml`
3. Set:

| Field | Value |
|-------|-------|
| Repository | `romwil/curatorx:1.0` (or `:1.0.3` / `:latest`) |
| Host port | `8788` (or map freely) |
| Config | `/mnt/user/appdata/curatorx/config` → `/config` |

4. Apply / Start, then open the WebUI link.

## First run on Unraid

1. Open `http://<unraid-ip>:8788`
2. Finish **Settings** — Plex, TMDB, LLM; optionally Radarr/Sonarr
3. Map movie and TV Plex libraries
4. Click **Sync library** on the Config maintenance card
5. Watch progress in the status dock (bottom-left of chat)

## Networking tips

- Prefer the **same Docker network** as Plex / Radarr / Sonarr when possible, or use host LAN IPs.
- For Ollama on the Unraid host:

```
LLM_PROVIDER=ollama
LLM_BASE_URL=http://host.docker.internal:11434/v1
```

If `host.docker.internal` is unavailable, use the host’s bridge IP (often `172.17.0.1`) or the server LAN IP.

## Backups

Back up the entire appdata folder:

```
/mnt/user/appdata/curatorx/config/
```

That includes `settings.json`, `curatorx.db`, and `jobs_state.json`.

## Upgrading

Pull a newer tag and recreate the container with the **same** `/config` mount. Interrupted syncs after a restart are marked failed with a clear message — start sync again from Config.

See also: [Installation](Installation.md) · [Troubleshooting](Troubleshooting.md) · [../DOCKER.md](../DOCKER.md)
