# CuratorX — Docker / Unraid

Deploy CuratorX as a single container with a persistent `/config` volume for `settings.json` and `curatorx.db`. Everyday tag: **`romwil/curatorx:latest`** (CA default). Pin **`:1.7`** or **`:1.7.13`** when you need a fixed line or exact build.

---

## Mac (Homebrew)

`brew install docker` installs only the **Docker CLI**. It does not install Compose, Buildx, or a container runtime. Without those, `docker compose up -d --build` fails with errors like `unknown shorthand flag: 'd' in -d`.

Choose **one** runtime:

### Option A — Docker Desktop (GUI)

```bash
brew install --cask docker
open -a Docker
```

Wait until the whale icon in the menu bar is steady, then:

```bash
docker compose version
cd /path/to/curatorx
cp .env.example .env
docker compose up -d --build
```

### Option B — Colima (CLI, no Docker Desktop)

```bash
brew install colima docker-compose
colima start
docker context use colima
```

Homebrew’s `docker-compose` formula is a **CLI plugin**. Tell the Docker client where to find it (once per user):

```bash
mkdir -p ~/.docker
cat > ~/.docker/config.json << 'JSON'
{
  "cliPluginsExtraDirs": [
    "/opt/homebrew/lib/docker/cli-plugins"
  ]
}
JSON
```

On Intel Macs, use `/usr/local/lib/docker/cli-plugins` instead of `/opt/homebrew/...`.

Verify:

```bash
docker compose version
docker info | head -5
```

Then run CuratorX:

```bash
cd /path/to/curatorx
cp .env.example .env
docker compose up -d --build
```

After reboot: `colima start` (or `brew services start colima`).

Open **http://localhost:8788**.

---

## Docker Compose (all platforms)

```bash
git clone https://github.com/romwil/curatorx.git
cd curatorx
cp .env.example .env
docker compose up -d --build
```

Open **http://localhost:8788**.

Environment variables in `.env` seed first-run settings (Plex, *arr, TMDB, LLM). See [CONFIGURATION.md](CONFIGURATION.md).

### Logs

All application output goes to stdout/stderr. Tail logs with:

```bash
docker compose logs -f curatorx
```

Set `CURATORX_LOG_LEVEL=DEBUG` in `.env` for verbose sync and agent tool tracing. See [CONFIGURATION.md](CONFIGURATION.md#logging).

---

## Unraid

Install from the Community Applications template (`templates/curatorx.xml` or `unraid/curatorx.xml`) or add manually:

| Setting | Value |
|---------|-------|
| **Port** | 8788 |
| **Config path** | `/mnt/user/appdata/curatorx/config` → `/config` |
| **Image** | `romwil/curatorx:latest` (or `:1.7` / `:1.7.13`) — multi-arch amd64+arm64 |

Optional advanced env (or generate in **Admin → Advanced**): `CURATORX_MCP_API_KEY` (privacy) and `CURATORX_MCP_FULL_API_KEY` (full; must differ). See [MCP.md](MCP.md) and [PRIVACY.md](PRIVACY.md).

### Ollama on the Unraid host

Point CuratorX at the host LLM:

```
LLM_PROVIDER=ollama
LLM_BASE_URL=http://host.docker.internal:11434/v1
```

Or use the host LAN IP if `host.docker.internal` is unavailable.

Full Unraid steps: [wiki/Unraid.md](wiki/Unraid.md).

### Unraid rollout (automation)

CA XML remains the human install source of truth. For pull/recreate rollouts (post-release testing, CI-style updates), keep files under appdata:

| Path | Purpose |
|------|---------|
| `/mnt/user/appdata/curatorx/rollout.sh` | `docker pull` + stop/rm + `docker run` + log/health confirm (stock Unraid; no Compose required) |
| `/mnt/user/appdata/curatorx/docker-compose.yml` | Optional reference / hosts that have Compose |
| `/mnt/user/appdata/curatorx/config` | Bind-mounted `/config` — never wipe |

```bash
ssh automat
cd /mnt/user/appdata/curatorx
./rollout.sh           # :latest
./rollout.sh 1.8.3     # pin a release tag
```

`rollout.sh` uses plain Docker CLI on Unraid (Compose is usually absent). If `docker compose` / `docker-compose` is available it prefers that instead. Same-named containers are stop/rm only — `./config` is never wiped. Optional seed env: copy `.env.example` → `.env` (secrets usually already live in `config/`).

---

## Troubleshooting

### Unraid "Force Update" not pulling fresh images

Unraid's Docker manager may not detect new images when only metadata (labels) changed between releases. Starting with v1.7.10, CuratorX embeds a unique build timestamp in the image file content to guarantee Docker recognizes every release as new.

If you're on an older version or Force Update still shows stale content:

```bash
docker stop curatorx
docker rmi romwil/curatorx:latest
# Then restart from the Unraid Docker UI — it will pull a fresh image
```

You can verify you have the correct build by checking the startup log or running:

```bash
docker exec curatorx cat /app/.build-info
```

---

## Publishing multi-arch images (maintainers)

Release images are multi-arch Docker Hub **manifest lists** (amd64 + arm64). Use the release script:

```bash
./scripts/docker-release.sh <semver>          # also tags X.Y and latest
./scripts/docker-release.sh 1.7.13 --also-line 1.7
```

The script builds with `--provenance=false --sbom=false` and pushes `:VERSION`, `:X.Y`, and `:latest`.

---

## Non-root container user

Starting with v1.7, the CuratorX image runs as user **`curatorx`** (UID **1000**, GID **1000**) instead of root. This limits the impact of a container breakout (security finding S13).

Starting with v1.7.3, the container uses an **entrypoint script** that automatically handles permission migration:

1. Container starts as root (the entrypoint script runs first)
2. `chown -R curatorx:curatorx /config` fixes ownership for existing installs
3. Privileges drop to the `curatorx` user via `gosu` before the application starts
4. If the container is already running as non-root (e.g. Kubernetes `runAsUser`), the entrypoint skips the chown and runs the application directly

**New installs:** no action needed.

**Existing installs upgrading from pre-1.7.3:** no manual action needed — the entrypoint auto-fixes `/config` ownership on first boot. No more `chown` required on the host.

**Kubernetes / rootless runtimes:** if your pod security context sets `runAsUser`, the entrypoint detects it is already non-root and runs the CMD directly without attempting chown.

---

## Data layout

| Path | Contents |
|------|----------|
| `/config/settings.json` | Connection settings, LLM config, onboarding flags |
| `/config/curatorx.db` | Library index, embeddings, chat (with `lens_id`), persona, lenses |
| `/config/jobs_state.json` | Durable background job history (library sync) |

SQLite uses **WAL** + `busy_timeout=30s` + `synchronous=NORMAL` so the UI can read while library sync writes (especially on Unraid appdata). NORMAL is a durability tradeoff vs FULL: less fsync cost under concurrent load; a crash mid-commit could lose the last transaction.

Back up the entire `/config` directory before major changes.

---

## Resources

- **LLM via Ollama** — allocate RAM on the host for your chosen model.
- **Library sync** — CPU/network-bound during TMDB enrichment; runs as a background job.
- **Embeddings** — optional cloud embedding API; hash fallback works offline.

---

## Related documentation

- [wiki/Unraid.md](wiki/Unraid.md) — Unraid CA install
- [wiki/Installation.md](wiki/Installation.md) — Docker Hub tags
- [ONBOARDING.md](ONBOARDING.md) — first-run wizard
- [ARCHITECTURE.md](ARCHITECTURE.md) — deployment diagram
- [FAQ.md](FAQ.md) — common questions
