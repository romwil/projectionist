# CuratorX — Docker / Unraid

Deploy CuratorX as a single container with a persistent `/config` volume for `settings.json` and `curatorx.db`. Baseline image line: **`romwil/curatorx:1.3`** (pin `:1.3.0` when you need an exact build).

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
| **Image** | `romwil/curatorx:1.3` (or `:1.3.0` / `:latest`) — multi-arch amd64+arm64 |

Optional advanced env (or generate in **Admin → Advanced**): `CURATORX_MCP_API_KEY` (privacy) and `CURATORX_MCP_FULL_API_KEY` (full; must differ). See [MCP.md](MCP.md) and [PRIVACY.md](PRIVACY.md).

### Ollama on the Unraid host

Point CuratorX at the host LLM:

```
LLM_PROVIDER=ollama
LLM_BASE_URL=http://host.docker.internal:11434/v1
```

Or use the host LAN IP if `host.docker.internal` is unavailable.

Full Unraid steps: [wiki/Unraid.md](wiki/Unraid.md).

---

## Publishing multi-arch images (maintainers)

Release images are multi-arch Docker Hub **manifest lists** (amd64 + arm64). Use the release script:

```bash
./scripts/docker-release.sh <semver>          # also tags X.Y and latest
./scripts/docker-release.sh 1.3.0 --also-line 1.3
```

The script builds with `--provenance=false --sbom=false` and pushes `:VERSION`, `:X.Y`, and `:latest`.

---

## Non-root container user

Starting with v1.7, the CuratorX image runs as user **`curatorx`** (UID **1000**, GID **1000**) instead of root. This limits the impact of a container breakout (security finding S13).

**New installs:** no action needed — the image creates `/config` with the correct ownership.

**Existing installs** with a bind-mounted `/config` directory owned by root:

```bash
# one-time fix on the Docker host
sudo chown -R 1000:1000 /path/to/curatorx/config
```

On **Unraid**, appdata paths are typically owned by `nobody:users` (65534:100). If CuratorX cannot write to `/config` after upgrading, run the `chown` above against your appdata path (e.g. `/mnt/user/appdata/curatorx/config`).

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
