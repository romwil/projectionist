# CuratorX — Docker / Unraid

Deploy CuratorX as a single container with a persistent `/config` volume for `settings.json` and `curatorx.db`.

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
| **Image** | `romwil/curatorx:1.1` (also `:1.1.6`, `:latest`) — multi-arch amd64+arm64 |

### Ollama on the Unraid host

Point CuratorX at the host LLM:

```
LLM_PROVIDER=ollama
LLM_BASE_URL=http://host.docker.internal:11434/v1
```

Or use the host LAN IP if `host.docker.internal` is unavailable.

### Unraid shows “not available” for updates

CuratorX images **must** be published as Docker Hub **v2 manifest lists**, not OCI indexes with provenance attestations. Unraid cannot check OCI indexes reliably → **Version: not available**, and Force Update often reuses the local image.

Publish with:

```bash
./scripts/docker-release.sh 1.1.6
```

(uses `docker buildx build --provenance=false --sbom=false --push`).

Operator workaround until a fixed image is pulled: `docker pull romwil/curatorx:1.1` on the Unraid host, then recreate the container (keep appdata). Details: [wiki/Unraid.md](wiki/Unraid.md#upgrading).

---

## Publishing multi-arch images (maintainers)

```bash
./scripts/docker-release.sh <semver>          # also tags X.Y and latest
./scripts/docker-release.sh 1.2.0 --also-line 1.2
```

Always keep `--provenance=false --sbom=false` for Unraid CA compatibility.

---

## Data layout

| Path | Contents |
|------|----------|
| `/config/settings.json` | Connection settings, LLM config, onboarding flags |
| `/config/curatorx.db` | Library index, embeddings, chat (with `lens_id`), persona, lenses |
| `/config/jobs_state.json` | Durable background job history (library sync) |

SQLite uses **WAL** + `busy_timeout=30s` + `synchronous=NORMAL` so the UI can read while library sync writes (especially on Unraid appdata). NORMAL is a durability tradeoff vs FULL: less fsync cost under concurrent load; a crash mid-commit could lose the last transaction.

Back up the entire `/config` directory before upgrades.

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