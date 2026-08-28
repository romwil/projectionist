# Automat environments — maintainer runbook

Task-first notes for the **Automat** Unraid host that runs Projectionist production and the maintainer QA sidecar. Audience: developers and Cursor agents working on this repo’s live stack — not end-user install docs (see [wiki/Unraid.md](../wiki/Unraid.md) and [DOCKER.md](../DOCKER.md) for generic Unraid).

Jump to: [LAN hosts](#lan-hosts-source-of-truth) · [Rollout](#rollout--appdata) · [UI verification](#ui-verification) · [Ops UI](#ops-ui-newsletters--mail) · [QA lifecycle](#qa--release-lifecycle) · [See also](#see-also)

---

## LAN hosts (source of truth)

| Role | Base URL | Use for |
|------|----------|---------|
| **Production** | `http://10.10.1.202:8788` | Version, `/api/health`, admin UI, “is prod on X.Y.Z?” |
| **QA sidecar** | `http://10.10.1.202:8790` | Interactive UI QA, multi-role smoke; prefer **Hub-pulled** tag (Path B) for release/CA proof |
| **QA lobby theater** | `http://10.10.1.202:8792` | Open LAN lightbox for the QA sidecar (maps container `8791`) |
| **Public hostname** | `https://projectionist.automat.vip` | Member-facing access only — **not** version or admin truth |

### Why the public URL is not truth

Agents (and humans) have concluded prod was still on an older build by hitting the public hostname or a random SSH tunnel while the household was already on a newer LAN build. Prefer a direct check:

```bash
# Authoritative prod version / health on Automat LAN
curl -s http://10.10.1.202:8788/api/health
# Optional: confirm image build metadata inside the container (on Unraid SSH)
# docker exec projectionist cat /app/.build-info
```

**Gotchas**

- `localhost:8788` on a maintainer laptop is often an **SSH tunnel to prod**, not a local `python -m projectionist.web` or Docker Compose. Do not treat it as “my local build,” and never point Playwright e2e at it by default (see `.cursor/rules/e2e-port-8788.mdc`; mocked e2e uses **8799**).
- Do not invent alternate tunnels or reverse proxies as the version oracle when LAN is reachable.

---

## Public SSL / household perimeter

Automat members reach the household at `https://projectionist.automat.vip`. That hostname is **TLS + reverse proxy**, not an extra auth layer. Treat every inbound packet as hostile; follow [SECURITY.md](../SECURITY.md).

| Topic | Automat note |
|-------|----------------|
| **Bind** | Prod/QA listen on `0.0.0.0:8788` / `:8790` inside Docker. `172.17.0.1` is the bridge — **setup** pre-selects Public Household; **runtime WAN interlock** does **not** lock that peer (would brick Unraid single-owner). RFC 6598 `100.64.0.0/10` (Tailscale/CGNAT) is **not** a visible public peer — runtime WAN interlock and setup halt treat it as LAN. |
| **WAN lock** | Blocks only a **visible public client IP**. Docker-bridge and Tailscale/CGNAT (`100.64.0.0/10`) peers are not WAN. Trusted `X-Forwarded-Proto: https` alone is not WAN. Spoofed forwarded headers without `PROJECTIONIST_TRUST_PROXY_HEADERS` are ignored. |
| **Proxy trust** | Set `PROJECTIONIST_TRUST_PROXY_HEADERS=1` (or the wizard TLS-edge confirm) **only** on the container behind Caddy/NPM. Never on a laptop tunnel. |
| **Bare 8788** | Do not port-forward prod `:8788` to the internet. Public DNS should hit the proxy, not the app port. |
| **MCP** | Keep `/mcp` off the WAN hostname. |
| **SETUP_MODE** | Existing Automat installs already have an owner → `setup_state=active`. Wizard endpoints 404. Do not re-run `/api/setup/commit` against prod. |
| **QA** | Glass-door `/login` / `/join`, honeypot, no `/tour`: Interactive UI QA on **`:8790` only**. |

---

## Rollout / appdata

| Path | Where |
|------|--------|
| Unraid kit | `/mnt/user/appdata/projectionist` |
| macOS mount (common) | `/Volumes/appdata/projectionist` |
| Canonical script in git | `scripts/unraid-rollout.sh` → sync to appdata as `rollout.sh` |

### Canonical prod appdata tree (user install — not a git clone)

Production appdata is a **rollout kit + live `/config` bind mount**, not a copy of this repository. Agents must **not** `git clone` into `/mnt/user/appdata/projectionist` (or the macOS SMB mirror).

```
/mnt/user/appdata/projectionist/
├── config/                  # DATA_DIR — SQLite, settings.json, theater cache, Tunarr, logs (KEEP; never wipe for rollout)
│   ├── projectionist.db
│   ├── settings.json
│   ├── jobs_state.json
│   ├── theater-poster-cache/
│   ├── tunarr/
│   └── …
├── rollout.sh               # from scripts/unraid-rollout.sh (pull-only Hub tag + recreate)
├── unraid-force-pull.sh     # from scripts/unraid-force-pull.sh (image refresh before Dockerman Force Update)
├── docker-compose.yml       # from docker-compose.unraid.yml (optional; plain docker also works on stock Unraid)
├── .env                     # optional host overrides (Plex/TMDB/LLM keys, TZ, MOUNT_DOCKER_SOCK) — not in git
└── .env.example             # from scripts/unraid.env.example (placeholders only)
```

**Do not place in prod appdata:** `.git/`, `frontend/`, `tests/`, `.venv`, CI caches, or any full source tree. Development belongs in a normal git checkout (e.g. maintainer laptop), not on Unraid appdata.

**Sync kit from repo after script changes** (does not restart prod):

```bash
cp scripts/unraid-rollout.sh /mnt/user/appdata/projectionist/rollout.sh
cp docker-compose.unraid.yml /mnt/user/appdata/projectionist/docker-compose.yml
cp scripts/unraid.env.example /mnt/user/appdata/projectionist/.env.example
cp scripts/unraid-force-pull.sh /mnt/user/appdata/projectionist/unraid-force-pull.sh
```

Legacy installs that never migrated may still use `/mnt/user/appdata/curatorx/` with the same layout (`config/` + rollout kit).

### Related maintainer paths (not prod appdata)

| Host path | Role | Git clone? |
|-----------|------|------------|
| `/mnt/user/appdata/projectionist-qa` | QA sidecar **DATA_DIR** only (`settings.json`, `projectionist.db`, …) | No — config volume |
| `/mnt/user/appdata/projectionist-qa-scripts` | QA compose template, `.env.qa`, `seed-qa-roles.sh`, `pentest/`, `qa-runs/` | No — host-local kit (see `qa-runs/QA-LIFECYCLE.md`) |
| `/mnt/user/appdata/projectionist-qa-build/` | Optional **Path A** rsync target (`src/`, `src-lobby/`, `src-theater/`) for host `docker build` on Automat | Source trees only — **not** CA/release proof; prefer Hub pull (Path B) |

`rollout.sh` is **pull-only** from Docker Hub (`romwil/projectionist:X.Y.Z`). It does **not** build from a git tree. Prod promote is step 4 of the Hub-first ship path in [RELEASE.md](../RELEASE.md) — only after Hub publish + CA proof pull.

```bash
# On Unraid (SSH) — preferred one-shot pull + recreate; /config is never wiped
cd /mnt/user/appdata/projectionist && ./rollout.sh 1.33.1

# From a machine with the appdata share mounted:
cd /Volumes/appdata/projectionist && ./rollout.sh 1.33.1
```

Keep the kit synced with the repo (`rollout.sh`, optional `unraid-force-pull.sh`, compose/env examples). Generic Force Update / 0 B pull pathology: [DOCKER.md](../DOCKER.md#unraid-force-update-pulls-0-b--stays-on-an-old-version).

No tokens, Apprise URLs, or other secrets belong in this runbook — they live in `config/settings.json` on the host.

### Anti-patterns on Automat

- **Do not** `docker build` on Automat and treat that image as Unraid CA / release proof (Path A). CA installs pull Hub tags.
- **Do not** promote prod from a host-built or untagged WIP image — only `./rollout.sh X.Y.Z` after Hub has `:X.Y.Z`.
- **Do not** claim prod is on `X.Y.Z` from the public hostname; use LAN `:8788` (table above).


---

## UI verification

When someone reports UI missing or broken — **especially after attaching a screenshot** — verify with a real browser against the **correct LAN host** (prod `:8788` or QA `:8790`), not from:

- grepping the built JS bundle for string presence, or
- arguing that the reporter “didn’t scroll.”

Trust a scrolled-to-bottom report plus screenshot. For authored Interactive UI QA campaigns (absolute baseline / delta), follow [`.cursor/skills/interactive-ui-qa/SKILL.md`](../../.cursor/skills/interactive-ui-qa/SKILL.md): target **`:8790` only**, never production `:8788`.

---

## Ops UI (Newsletters vs Mail)

As of **1.32.2+**:

| Surface | Route / nav | Job |
|---------|-------------|-----|
| **Newsletters** | **Admin → Ops → Newsletters** (`/admin/newsletters`) | Weekly newsletter push + Year in Review (YIR) admin generate / send-test |
| **Mail** | **Admin → Mail** | SMTP / Resend / Apprise **transport** only |

### Historical footgun (why Newsletters exists)

Before the Newsletters page, YIR / weekly controls lived on Mail. On **iPad Safari**, the sticky Save bar could push that content effectively off-screen even when Chromium still had the panels in the DOM — so owners (and agents arguing from DOM mounts) disagreed about whether YIR “existed.” Newsletters mounts those panels on their own page so they stay reachable.

### Year in Review defaults

- Owner **admin test / generate** defaults to the **current calendar year, year-to-date (YTD)**.
- Generate-with-notify creates the same durable **inbox** notification shape as production delivery.
- The **scheduled January drop** still uses the **prior** calendar year (the year just completed).

Member-facing copy and owner API examples: in-app `/help` and [HELP.md](../HELP.md).

---

## QA / release lifecycle

Canonical ship order (full detail: [RELEASE.md](../RELEASE.md)):

0. **Prepare (dot/patch)** — on a PR branch: CHANGELOG `## [X.Y.Z]`, then `./scripts/patch-release.sh [--run-tests]` (lockstep bump + release-notes). Minor features: bump Y manually or extend the script.
1. **Hub** — `./scripts/docker-release.sh X.Y.Z` so `romwil/projectionist:X.Y.Z` exists.
2. **GitHub** — PR → `main` (branch protection — never bypass; use a PR even for hotfixes), then annotated tag + `gh release` **after merge** matching that version.
3. **CA proof** — pull Hub tag onto QA / disposable container (**Path B**). This is the Unraid CA install path.
4. **Prod** — only when asked: `./rollout.sh X.Y.Z` (pull-only). Never stop prod while iterating on QA.

After a successful Docker Hub publish, **spin down** maintainer QA (`projectionist-qa` on `:8790`) unless an active QA/test campaign is in progress. **Never** stop production `projectionist` / port **`:8788`**.

### QA image paths (host `QA-REDEPLOY.md`)

| Path | What | Use for release / CA proof? |
|------|------|------------------------------|
| **B — Hub pull** | `docker pull romwil/projectionist:X.Y.Z` then recreate `projectionist-qa` | **Yes** — required for release-candidate UI QA |
| **A — host build** | `docker build` from a git tree on Automat | **No** — WIP / debug only; not Unraid CA |
| **C — restart** | Restart existing container | **No** — no new image |

Agents must not write “CA / Unraid path verified” after a Path A recreate. Prefer Path B whenever the goal is “what members get from Community Applications.”

Maintainer QA scripts and dated run artifacts live on the host under `/Volumes/appdata/projectionist-qa-scripts/` (not in this git tree). Lifecycle notes there: `qa-runs/QA-LIFECYCLE.md` when present.

### Maintainer pentest (QA `:8790` only)

Authorized campaign against the maintainer’s own QA sidecar — not a general exploit pack, not prod.

```bash
# Sidecar is idle-stopped; start QA only
ssh automat 'docker start projectionist-qa'
cd /Volumes/appdata/projectionist-qa-scripts/pentest
./run.sh    # loads ../.env.qa; refuses :8788 and automat.vip
```

In-process lab checklists remain in git: `python3 scripts/security/pentest/run-checklist.py`. The live kit expands handshake / honeypot / invite / IDOR / WAN-header coverage; reports go to `qa-runs/YYYY-MM-DD-maintainer-pentest/` (no passwords, cookies redacted).

---

## Watch identity attribution (Plex owner local account)

PMS history `accountID` / session `User.id` for the **server owner** is often the local `/accounts` id (commonly `1`), while Projectionist stores plex.tv `id` on `users.plex_user_id`. Shared users usually already use their plex.tv id as the PMS account id.

On startup and each history ingest, Projectionist aliases the local owner account (name match to the PLEX_TOKEN plex.tv username) and repairs NULL `user_id` on events/sessions/completions for mapped keys only. Shared accounts without a linked Projectionist user stay NULL (fail closed).

Owner one-shot (LAN prod, authenticated as owner):

```bash
curl -s -X POST -b "curatorx_session=…" \
  http://10.10.1.202:8788/api/admin/watch-tracker/repair-identities
```

Or wait for the next container start / history ingest after upgrading to **1.32.3+**. Do not wipe `watch_*` tables.

---

## See also

- `.cursor/rules/automat-environments.mdc` — always-on agent summary of this runbook
- `.cursor/rules/e2e-port-8788.mdc` — mocked e2e uses **8799**, not tunnel/prod 8788
- `.cursor/rules/interactive-ui-qa.mdc` + skill — authored QA on `:8790`
- `.cursor/rules/release.mdc` · [RELEASE.md](../RELEASE.md) — version bump, Hub publish, QA teardown
- Maintainer pentest kit (host-local): `/Volumes/appdata/projectionist-qa-scripts/pentest/` — QA `:8790` only
- [DOCKER.md](../DOCKER.md) · [wiki/Unraid.md](../wiki/Unraid.md) — generic Unraid install / Force Update
- [AGENTS.md](../../AGENTS.md) — Cursor Cloud / agent quickstart (links here)
