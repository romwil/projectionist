# CuratorX — Docker / Unraid

Deploy CuratorX as a single container with a persistent `/config` volume for `settings.json` and `curatorx.db`. Everyday tag: **`romwil/curatorx:latest`** (CA default). Pin **`:1.8`** or **`:1.8.14`** when you need a fixed line or exact build.

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
| **Image** | `romwil/curatorx:latest` (or `:1.8` / `:1.8.14`) — multi-arch amd64+arm64 |

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
| `/mnt/user/appdata/curatorx/rollout.sh` | `docker pull` + stop/rm + `docker run` + log/health confirm (stock Unraid; no Compose required). Canonical: `scripts/unraid-rollout.sh` |
| `scripts/unraid-force-pull.sh` | Pull + verify RepoDigest moved; optional `--rmi-retry` / `--recreate` — then Force Update in the UI |
| `/mnt/user/appdata/curatorx/docker-compose.yml` | Optional reference / hosts that have Compose |
| `/mnt/user/appdata/curatorx/config` | Bind-mounted `/config` — never wipe |

```bash
ssh automat
cd /mnt/user/appdata/curatorx
./rollout.sh           # :latest
./rollout.sh 1.8.14    # pin a release tag
# image-only (keep Dockerman template):
# /path/to/curatorx/scripts/unraid-force-pull.sh latest
```

`rollout.sh` uses plain Docker CLI on Unraid (Compose is usually absent). If `docker compose` / `docker-compose` is available it prefers that instead. Same-named containers are stop/rm only — `./config` is never wiped. Optional seed env: copy `.env.example` → `.env` (secrets usually already live in `config/`).

---

## Troubleshooting

### Unraid "Force Update" pulls 0 B / stays on an old version

**Root cause (Dockerman on Unraid 7.x):** Force Update **does** call Docker Engine pull (`POST /images/create?fromImage=…`), then stop/rm/recreate. **TOTAL DATA PULLED: 0 B** means Engine reported the local tag as already current (or transferred no layer bytes), so Dockerman recreates from the existing local `romwil/curatorx:latest` → digest mapping. Hub can already point at a newer digest (confirmed with `docker buildx imagetools inspect` on another machine) while this host’s tag still maps to the previous content.

This is **not** fixed by OCI labels or `/app/.build-info` alone — those make each Hub release unique; they do not force Engine to re-resolve a floating tag. There is **no Community Applications XML attribute** that forces a stronger pull than Force Update already performs. Maintainers still publish with `--provenance=false --sbom=false` so Dockerman sees Docker v2 **manifest lists** (OCI attestation indexes historically showed as “not available”).

**Supported update path for CA users (config preserved — never wipe `/mnt/user/appdata/curatorx/config`):**

```bash
# On the Unraid host (SSH) — preferred one-shot:
cd /mnt/user/appdata/curatorx && ./rollout.sh latest

# Or image refresh only, then Docker UI → Force Update / Apply:
docker pull romwil/curatorx:latest
# or: ./scripts/unraid-force-pull.sh latest
```

**If pull reports up-to-date but Hub is newer**, delete the local tag and pull again (or use the helper):

```bash
./scripts/unraid-force-pull.sh latest --rmi-retry
# equivalent manual:
docker stop curatorx && docker rm curatorx
docker rmi romwil/curatorx:latest
docker pull romwil/curatorx:latest
# Docker → Add Container → User Templates → curatorx
```

**Pin a release** when you want to avoid floating `:latest`: set Repository to `romwil/curatorx:1.8.14` (or `:1.8`) in the template, then pull that tag. Line tags (`:1.8`) still float within the minor line.

**Verify the running build:**

```bash
docker images romwil/curatorx --digests
docker exec curatorx cat /app/.build-info
docker logs curatorx 2>&1 | grep -m1 'CuratorX startup'
docker buildx imagetools inspect romwil/curatorx:latest | head -5
```

**CA submission note:** Force Update works when Engine re-resolves correctly (same as other Hub apps). Document the SSH/`rollout.sh` path for the 0 B case — do not claim Dockerfile cache-busting “fixes Force Update.”

### Trailer says “This content is blocked”

CuratorX permits its privacy-enhanced YouTube player with:

```text
frame-src https://www.youtube.com https://www.youtube-nocookie.com
```

If Unraid, Caddy, Nginx Proxy Manager, Cloudflare, or another reverse proxy replaces or adds a `Content-Security-Policy` header, include those origins in that proxy policy's `frame-src` directive too. Browsers enforce every CSP header they receive, so adding a second permissive policy does not cancel a stricter one; update or remove the proxy's conflicting policy. The trailer modal also provides **Open on YouTube** as a fallback when an upstream policy cannot be changed.

---

## Publishing multi-arch images (maintainers)

Release images are multi-arch Docker Hub **manifest lists** (amd64 + arm64). Use the release script:

```bash
./scripts/docker-release.sh <semver>          # also tags X.Y and latest
./scripts/docker-release.sh 1.8.14 --also-line 1.8
./scripts/docker-release.sh 1.8.14 --date-tag # also :latest-YYYYMMDD (CA testing)
```

**Release checklist (notes):** ensure `CHANGELOG.md` has a `## [X.Y.Z] — YYYY-MM-DD` heading for the release version. The release script runs `scripts/generate-release-notes.sh --require-version <semver>` **before** `docker buildx` and fails if that heading is missing. Output is `frontend/public/release-notes.json` (served as `/release-notes.json` for What’s New / About).

The script builds with `--provenance=false --sbom=false`, passes `CURATORX_VERSION` / `BUILD_DATE` / `VCS_REF` into OCI labels + `/app/.build-info`, pushes `:VERSION`, `:X.Y`, and `:latest`, then prints Hub digests for verification.

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
