# Unraid

CuratorX is packaged for Unraid Community Applications as a single container with one config volume.

## Community Applications icon

| Spec | Value |
|------|--------|
| Format | PNG (transparency optional; solid cinema-dark background is fine) |
| Size | **256×256** minimum (also ship **512×512** for sharper CA/Docker UI) |
| Style | Clear at thumbnail size; distinctive mark, not tiny text |
| Repo assets | `unraid/curatorx-icon.png` (256), `unraid/curatorx-icon-512.png` (512) |
| Template `<Icon>` | Raw GitHub URL to the 256 PNG |

Resize from a larger master if needed: `sips -z 256 256 source.png --out unraid/curatorx-icon.png` (macOS) or ImageMagick `convert`.

## Install from template

1. In Unraid, open **Apps** (Community Applications).
2. Search for **CuratorX**, or add the template from this repo:
   - `templates/curatorx.xml`
   - `unraid/curatorx.xml`
3. Set:

| Field | Value |
|-------|-------|
| Repository | `romwil/curatorx:1.3` (or `:1.3.0` / `:latest`) |
| Host port | `8788` (or map freely) |
| Config | `/mnt/user/appdata/curatorx/config` → `/config` |
| TZ (advanced) | e.g. `America/New_York` — needed so preferred `library_sync_hour` matches wall clock |

4. Apply / Start, then open the WebUI link.

## First run on Unraid

1. Open `http://<unraid-ip>:8788`
2. Finish **Settings** (Name → Connections → Libraries) — Plex server URL + server token, TMDB, LLM; optionally Radarr/Sonarr
3. Map movie and TV Plex libraries
4. Click **Sync library** on Config
5. Watch progress in the status dock (bottom-left of chat)

Household **Sign in with Plex** (PIN) is optional — enable multi-user later if you need per-person chats/watchlists.

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

Pull a newer tag and recreate the container with the **same** `/config` mount. An interrupted sync job is marked failed; start sync again from Config — phase checkpoints resume unfinished work when still valid (≤72h).

### “Version: not available” / Force Update keeps the old image

Unraid’s Docker update checker often returns **not available** for images published as **OCI indexes** (Buildx default with provenance/SBOM attestations). Force Update then appears to “succeed” while reusing the **local cache**, so you only get a new build after manually removing the image.

**Maintainer fix (already required for CuratorX releases):** push with Docker v2 manifests via [`scripts/docker-release.sh`](../../scripts/docker-release.sh) (`--provenance=false --sbom=false`). After that, Check for Updates should work like other CA apps.

**On your Unraid box right now:**

```bash
# Unraid terminal — pull a fresh digest, then Force Update / recreate
docker pull romwil/curatorx:1.3
# or pin a patch: docker pull romwil/curatorx:1.3.0
```

Optional advanced env (or generate in **Admin → Advanced**): `CURATORX_MCP_API_KEY` (privacy) and `CURATORX_MCP_FULL_API_KEY` (full; must differ). Privacy notes: in-app `/privacy` or [PRIVACY.md](../PRIVACY.md).

Or: Docker → CuratorX → Remove (keep volumes / keep appdata) → re-add from template / CA so it pulls again. Do **not** delete `/mnt/user/appdata/curatorx/config`.

Optional: install Community Applications’ **Docker Update Patch** plugin if many containers show “not available.”

See also: [Installation](Installation.md) · [Troubleshooting](Troubleshooting.md) · [../DOCKER.md](../DOCKER.md)
