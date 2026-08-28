# Projectionist — Docker / Unraid

Deploy Projectionist as a single container with a persistent `/config` volume for `settings.json` and `projectionist.db` (or legacy `curatorx.db`). Everyday tag: **`romwil/projectionist:latest`**. During the compatibility window the same digests are also published as **`**. Pin a minor line (e.g. **`:1.11`**) or an exact build (**`:X.Y.Z`**, see [CHANGELOG.md](../CHANGELOG.md)) when you need a fixed target.

### Python build-context hygiene

Dockerfile `COPY . .` / `COPY projectionist` must not pull host `*.egg-info`, `build/`, or `dist/` into the image. Keep these excludes in `.dockerignore`:

```
*.egg-info/
*.egg
build/
dist/
.eggs/
__pycache__/
*.pyc
```

After a local package rename, also purge the venv editable install before trusting imports — see [TESTING.md](TESTING.md#after-renaming-the-python-package-curatorx--projectionist).

### Build caching (Dockerfile / BuildKit)

The image is **multi-stage**: Node builds the Vite SPA, then a slim Python runtime copies `frontend/dist` and installs `.[web,mcp]`.

Caching that matters:

| Layer / mount | What stays warm | What busts it |
|---|---|---|
| Frontend `npm ci` | `frontend/package-lock.json` unchanged | Lockfile / package.json change |
| BuildKit npm cache (`/root/.npm`) | Download cache across builds | Rare; cleared with builder prune |
| Python deps (`pip install` on stub package) | `pyproject.toml` (+ README/LICENSE) unchanged | Dependency / metadata change |
| BuildKit pip cache (`/root/.cache/pip`) | Wheel cache across builds | Rare; cleared with builder prune |
| App source / SPA rebuild | — | Any `projectionist/` or frontend source edit |
| Identity (`ARG`/`LABEL`/`/app/.build-info`) | Declared **after** apt/pip so version bumps do not reinstall deps | Every release (intentional) |

**BuildKit is required** for `--mount=type=cache`. Docker 23+ and `docker buildx` enable it by default. On older engines:

```bash
export DOCKER_BUILDKIT=1
docker build -t projectionist:local .
```

`scripts/docker-release.sh` exports `DOCKER_BUILDKIT=1` and always uses `buildx` (Hub multi-arch). **Automat `unraid-rollout.sh` only pulls Hub images** — it does not build, so no BuildKit flag is needed on the Unraid host for production rollout.

Maintainer QA Path A (local `docker build` of a WIP tag on Automat) should use BuildKit the same way (`DOCKER_BUILDKIT=1` or buildx) so npm/pip cache mounts apply. Path B/C that only recreate from Hub tags are unchanged.

CI (`docker-smoke`) uses Buildx + GitHub Actions cache (`cache-from`/`cache-to: type=gha`) so PR image smokes reuse layers across runs.

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

Then run Projectionist:

```bash
cd /path/to/projectionist
cp .env.example .env
docker compose up -d --build
```

After reboot: `colima start` (or `brew services start colima`).

Open **http://localhost:8788**.

---

## Docker Compose (all platforms)

```bash
git clone https://github.com/romwil/projectionist.git
cd projectionist
cp .env.example .env
docker compose up -d --build
```

Open **http://localhost:8788**.

Environment variables in `.env` seed first-run settings (Plex, *arr, TMDB, LLM). See [CONFIGURATION.md](CONFIGURATION.md).

### Logs

All application output goes to stdout/stderr. Tail logs with:

```bash
docker compose logs -f projectionist
```

Set `PROJECTIONIST_LOG_LEVEL=DEBUG` in `.env` for verbose sync and agent tool tracing. See [CONFIGURATION.md](CONFIGURATION.md#logging).

---

## Unraid

Install from the Community Applications template (`templates/projectionist.xml` or `unraid/projectionist.xml`; legacy `curatorx.xml` is a compatibility pointer) or add manually:

| Setting | Value |
|---------|-------|
| **Port** | 8788 |
| **Config path** | `/mnt/user/appdata/projectionist/config` → `/config` (legacy …/curatorx/config OK if never migrated) |
| **Image** | `romwil/projectionist:latest` (or a `:X.Y` line / `:X.Y.Z` pin) — multi-arch amd64+arm64 |

Optional advanced env (or generate in **Admin → Advanced**): `PROJECTIONIST_MCP_API_KEY` (privacy) and `PROJECTIONIST_MCP_FULL_API_KEY` (full; must differ). See [MCP.md](MCP.md) and [PRIVACY.md](PRIVACY.md).

### Ollama on the Unraid host

Point Projectionist at the host LLM:

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
| `/mnt/user/appdata/projectionist/rollout.sh` | `docker pull` + stop/rm + `docker run` + log/health confirm (stock Unraid; no Compose required). Canonical: `scripts/unraid-rollout.sh` |
| `/mnt/user/appdata/projectionist/unraid-force-pull.sh` | Pull + verify RepoDigest moved; optional `--rmi-retry` / `--recreate` — then Force Update in the UI. Canonical: `scripts/unraid-force-pull.sh` |
| `/mnt/user/appdata/projectionist/docker-compose.yml` | Optional reference / hosts that have Compose. Canonical: `docker-compose.unraid.yml` |
| `/mnt/user/appdata/projectionist/.env.example` | Optional seed env template. Canonical: `scripts/unraid.env.example` |
| `/mnt/user/appdata/projectionist/config` | Bind-mounted `/config` — never wipe |

```bash
ssh automat
cd /mnt/user/appdata/projectionist
./rollout.sh           # :latest
./rollout.sh 1.27.3    # pin a release tag
# image-only (keep Dockerman template):
# ./unraid-force-pull.sh latest
```

Maintainer Automat LAN hosts, version-truth rules, Hub-first QA (Path B pull vs Path A host build), and QA teardown:
[ops/AUTOMAT.md](ops/AUTOMAT.md). `rollout.sh` is **pull-only** — never treat a host `docker build` as Unraid CA proof.

`rollout.sh` uses plain Docker CLI on Unraid (Compose is usually absent). If `docker compose` / `docker-compose` is available it prefers that instead. Same-named containers are stop/rm only — `./config` is never wiped. Optional seed env: copy `.env.example` → `.env` (secrets usually already live in `config/`).

---

## Troubleshooting

### Unraid "Force Update" pulls 0 B / stays on an old version

**Root cause (Dockerman on Unraid 7.x):** Force Update **does** call Docker Engine pull (`POST /images/create?fromImage=…`), then stop/rm/recreate. **TOTAL DATA PULLED: 0 B** means Engine reported the local tag as already current (or transferred no layer bytes), so Dockerman recreates from the existing local `romwil/projectionist:latest` tag. Hub can already point at a newer digest (confirmed with `docker buildx imagetools inspect` on another machine) while this host’s tag still maps to the previous content.

This is **not** fixed by OCI labels or `/app/.build-info` alone — those make each Hub release unique; they do not force Engine to re-resolve a floating tag. There is **no Community Applications XML attribute** that forces a stronger pull than Force Update already performs. Maintainers still publish with `--provenance=false --sbom=false` so Dockerman sees Docker v2 **manifest lists** (OCI attestation indexes historically showed as “not available”).

**Supported update path for CA users (config preserved — never wipe `/mnt/user/appdata/projectionist/config`):**

```bash
# On the Unraid host (SSH) — preferred one-shot:
cd /mnt/user/appdata/projectionist && ./rollout.sh latest

# Or image refresh only, then Docker UI → Force Update / Apply:
docker pull romwil/projectionist:latest
# or: ./scripts/unraid-force-pull.sh latest
```

**If pull reports up-to-date but Hub is newer**, delete the local tag and pull again (or use the helper):

```bash
./scripts/unraid-force-pull.sh latest --rmi-retry
# equivalent manual:
docker stop projectionist && docker rm projectionist
# legacy container name during compat: curatorx
docker rmi romwil/projectionist:latest
docker pull romwil/projectionist:latest
# Docker → Add Container → User Templates → projectionist
```

**Pin a release** when you want to avoid floating `:latest`: set Repository to `romwil/projectionist:X.Y.Z` (an exact version) or `:X.Y` (a minor line) in the template, then pull that tag. Line tags (e.g. `:1.11`) still float within the minor line.

**Verify the running build:**

```bash
docker images romwil/projectionist --digests
docker exec projectionist cat /app/.build-info
docker logs projectionist 2>&1 | grep -m1 'Projectionist startup'
docker buildx imagetools inspect romwil/projectionist:latest | head -5
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

Full ship checklist (**Hub-first**: publish `romwil/projectionist:X.Y.Z`, then PR/tag, then CA proof via Hub pull — not a host `docker build` / Path A): **[RELEASE.md](RELEASE.md)**. GitHub merge alone is not a release.

Release images are multi-arch Docker Hub **manifest lists** (amd64 + arm64). Use the release script:

```bash
./scripts/docker-release.sh <semver>          # also tags X.Y and latest
./scripts/docker-release.sh 1.11.0 --also-line 1.11
./scripts/docker-release.sh 1.11.0 --date-tag # also :latest-YYYYMMDD (CA testing)
```

**Release checklist (notes):** ensure `CHANGELOG.md` has a `## [X.Y.Z] — YYYY-MM-DD` heading for the release version. The release script runs `scripts/generate-release-notes.sh --require-version <semver>` **before** `docker buildx` and fails if that heading is missing. Output is `frontend/public/release-notes.json` (served as `/release-notes.json` for What’s New / About).

The script builds with `--provenance=false --sbom=false`, passes `PROJECTIONIST_VERSION` / `BUILD_DATE` / `VCS_REF` into OCI labels + `/app/.build-info`, and pushes `romwil/projectionist:{VERSION,X.Y,latest}`.

---

## Non-root container user

Starting with v1.7, the image runs as a dedicated non-root user at **UID/GID 1000** (historically `curatorx`; now `projectionist` — same numeric IDs so bind-mounted appdata stays valid). This limits the impact of a container breakout (security finding S13).

Starting with v1.7.3, the container uses an **entrypoint script** that automatically handles permission migration:

1. Container starts as root (the entrypoint script runs first)
2. If `/config` is not already owned by UID/GID **1000**, `chown -R projectionist:projectionist /config` fixes ownership for existing installs (skipped when ownership is already correct so large DBs do not slow every Unraid Force Update / recreate)
3. Privileges drop to the `projectionist` user via `gosu` before the application starts
4. If the container is already running as non-root (e.g. Kubernetes `runAsUser`), the entrypoint skips the chown and runs the application directly

**New installs:** no action needed. Keep the appdata directory owned by UID/GID 1000 (Unraid default for many templates).

**Existing installs upgrading from pre-1.7.3:** no manual action needed — the entrypoint auto-fixes `/config` ownership on first boot when it is still root-owned. No more host-side `chown` required.

**Kubernetes / rootless runtimes:** if your pod security context sets `runAsUser`, the entrypoint detects it is already non-root and runs the CMD directly without attempting chown.

**PUID/PGID:** not supported yet — the image is fixed at 1000:1000. Map host ownership to that UID/GID rather than expecting arbitrary remapping.

---

## Data layout

| Path | Contents |
|------|----------|
| `/config/settings.json` | Connection settings, LLM config, onboarding flags (file mode `0600`; UI secrets encrypted at rest when a secrets key is available) |
| `/config/projectionist.db` | Library index, embeddings, chat, persona (legacy `curatorx.db` still used if present) |
| `/config/jobs_state.json` | Durable background job history (library sync) |

SQLite uses **WAL** + `busy_timeout=30s` + `synchronous=NORMAL` so the UI can read while library sync writes (especially on Unraid appdata). NORMAL is a durability tradeoff vs FULL: less fsync cost under concurrent load; a crash mid-commit could lose the last transaction.

### Backing up `/config` (WAL-safe)

Copying files while the container is running can capture a torn SQLite database: WAL mode keeps recent commits in `*-wal` / `*-shm` sidecars, so a naive `cp` of only `*.db` may miss or corrupt data.

**Preferred — online consistent snapshot** (container can stay up):

```bash
# From the host, with the config directory mounted (Unraid example):
CONFIG=/mnt/user/appdata/projectionist/config
mkdir -p "$CONFIG/backups"
# Prefer projectionist.db; fall back to legacy curatorx.db.
DB="$CONFIG/projectionist.db"
[ -f "$DB" ] || DB="$CONFIG/curatorx.db"
sqlite3 "$DB" ".backup '$CONFIG/backups/projectionist-$(date +%Y%m%d).db'"
cp -a "$CONFIG/settings.json" "$CONFIG/backups/settings-$(date +%Y%m%d).json"
# If you set PROJECTIONIST_SECRETS_KEY, back that env/secret up with the volume —
# ciphertext in settings.json is useless without the key.
```

**Alternative — stop then copy** the whole directory:

```bash
docker stop projectionist
cp -a /mnt/user/appdata/projectionist/config /mnt/user/backups/projectionist-$(date +%Y%m%d)
docker start projectionist
```

Do **not** rely on copying only the `.db` file while the container is writing. See also [SECURITY.md](SECURITY.md) (rotating secrets and protecting backups).

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
