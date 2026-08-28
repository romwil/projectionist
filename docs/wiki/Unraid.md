# Unraid

Projectionist is packaged for Unraid Community Applications as a single container with one config volume. The CA template uses **`romwil/projectionist:latest`**. Pin a minor line (e.g. `:1.12`) or an exact release (e.g. `:1.12.0`) if you prefer a fixed tag.

CA packaging in this repo:

| File | Role |
|------|------|
| `ca_profile.xml` (repo root) | Repository profile for CA submission (Profile, icon, support links) |
| `templates/projectionist.xml` | Canonical Docker template (CA TemplateURL) |
| `unraid/projectionist.xml` | Same template, kept in sync for Unraid asset layout |

## Community Applications icon

| Spec | Value |
|------|--------|
| Format | PNG (transparency optional; solid cinema-dark background is fine) |
| Size | **256×256** minimum (also ship **512×512** for sharper CA/Docker UI) |
| Style | Clear at thumbnail size; distinctive mark, not tiny text |
| Repo assets | `unraid/projectionist-icon.png` (256), `unraid/projectionist-icon-512.png` (512) |
| Template `<Icon>` | Raw GitHub URL to the 256 PNG |

Resize from a larger master if needed: `sips -z 256 256 source.png --out unraid/projectionist-icon.png` (macOS) or ImageMagick `convert`.

## Install from template

1. In Unraid, open **Apps** (Community Applications).
2. Search for **Projectionist**, or add the template from this repo:
   - `templates/projectionist.xml`
   - `unraid/projectionist.xml`
3. Set:

| Field | Value |
|-------|-------|
| Repository | `romwil/projectionist:latest` (or a `:X.Y` line / `:X.Y.Z` pin, e.g. `:1.12` / `:1.12.0`) |
| Host port | `8788` (or map freely) |
| Config (new / migrated) | `/mnt/user/appdata/projectionist/config` → `/config` |
| Config (legacy, never migrated) | `/mnt/user/appdata/curatorx/config` → `/config` — keep that path if you never moved |
| TZ (advanced) | e.g. `America/New_York` — needed so preferred `library_sync_hour` matches wall clock |

4. Apply / Start, then open the WebUI link.

Optional advanced env (or generate in **Admin → Advanced**): `PROJECTIONIST_MCP_API_KEY` (privacy) and `PROJECTIONIST_MCP_FULL_API_KEY` (full; must differ). Use `PROJECTIONIST_MCP_*` only. Privacy notes: in-app `/privacy` or [PRIVACY.md](../PRIVACY.md).

## First run on Unraid

1. Open `http://<unraid-ip>:8788`
2. Finish **Admin / Settings** (Name → Connections → Libraries) — Plex server URL + server token, TMDB, LLM; optionally Radarr/Sonarr
3. Map movie and TV Plex libraries
4. Click **Sync library**
5. Watch progress in the status dock (bottom of the conversation sidebar)

Household sign-in is optional — enable multi-user later if you need per-person chats/watchlists (Plex PIN, local password, and/or OIDC).

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
/mnt/user/appdata/projectionist/config/
```

That includes `settings.json`, `projectionist.db`, and `jobs_state.json`. (Legacy installs that never migrated may still use `/mnt/user/appdata/curatorx/config/`.)

## Updating

**Do not rely on Docker → Force Update alone.** Dockerman *does* call Engine pull, but when the UI reports **TOTAL DATA PULLED: 0 B** it recreates from a stale local `romwil/projectionist:latest` digest even though Hub `:latest` has moved. There is no template XML switch that forces a stronger pull. Supported paths (same `/config` mount — never wipe appdata):

```bash
# Preferred one-shot (pull + recreate; config preserved):
cd /mnt/user/appdata/projectionist && ./rollout.sh latest

# Or refresh the image, then Force Update / Apply in the Docker UI:
docker pull romwil/projectionist:latest
# optional helper from appdata (or the repo):
# ./unraid-force-pull.sh latest
# ./unraid-force-pull.sh latest --rmi-retry   # if pull still no-ops
```

Keep the appdata kit in sync with the repo: `scripts/unraid-rollout.sh` → `rollout.sh`, `docker-compose.unraid.yml` → `docker-compose.yml`, `scripts/unraid.env.example` → `.env.example`, `scripts/unraid-force-pull.sh`. Confirm: `docker exec projectionist cat /app/.build-info` and the `Projectionist startup (version …)` log line. Full root-cause: [../DOCKER.md](../DOCKER.md#unraid-force-update-pulls-0-b--stays-on-an-old-version).

An interrupted sync job is marked failed; start sync again — phase checkpoints resume unfinished work when still valid (≤72h).

See also: [Installation](Installation.md) · [Troubleshooting](Troubleshooting.md) · [../DOCKER.md](../DOCKER.md)
