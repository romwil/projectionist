# Automat environments — maintainer runbook

Task-first notes for the **Automat** Unraid host that runs Projectionist production and the maintainer QA sidecar. Audience: developers and Cursor agents working on this repo’s live stack — not end-user install docs (see [wiki/Unraid.md](../wiki/Unraid.md) and [DOCKER.md](../DOCKER.md) for generic Unraid).

Jump to: [LAN hosts](#lan-hosts-source-of-truth) · [Rollout](#rollout--appdata) · [UI verification](#ui-verification) · [Ops UI](#ops-ui-newsletters--mail) · [QA lifecycle](#qa--release-lifecycle) · [See also](#see-also)

---

## LAN hosts (source of truth)

| Role | Base URL | Use for |
|------|----------|---------|
| **Production** | `http://10.10.1.202:8788` | Version, `/api/health`, admin UI, “is prod on X.Y.Z?” |
| **QA sidecar** | `http://10.10.1.202:8790` | Interactive UI QA, multi-role smoke, WIP image checks |
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

## Rollout / appdata

| Path | Where |
|------|--------|
| Unraid kit | `/mnt/user/appdata/projectionist` |
| macOS mount (common) | `/Volumes/appdata/projectionist` |
| Canonical script in git | `scripts/unraid-rollout.sh` → sync to appdata as `rollout.sh` |

```bash
# On Unraid (SSH) — preferred one-shot pull + recreate; /config is never wiped
cd /mnt/user/appdata/projectionist && ./rollout.sh 1.32.2

# From a machine with the appdata share mounted:
cd /Volumes/appdata/projectionist && ./rollout.sh 1.32.2
```

Keep the kit synced with the repo (`rollout.sh`, optional `unraid-force-pull.sh`, compose/env examples). Generic Force Update / 0 B pull pathology: [DOCKER.md](../DOCKER.md#unraid-force-update-pulls-0-b--stays-on-an-old-version).

No tokens, Apprise URLs, or other secrets belong in this runbook — they live in `config/settings.json` on the host.

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

1. Ship process: [RELEASE.md](../RELEASE.md) and `.cursor/rules/release.mdc`.
2. After a successful Docker Hub publish, **spin down** maintainer QA (`projectionist-qa` on `:8790`) unless an active QA/test campaign is in progress.
3. **Never** stop production `projectionist` / port **`:8788`**.

Maintainer QA scripts and dated run artifacts live on the host under `/Volumes/appdata/projectionist-qa-scripts/` (not in this git tree). Lifecycle notes there: `qa-runs/QA-LIFECYCLE.md` when present.

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
- [DOCKER.md](../DOCKER.md) · [wiki/Unraid.md](../wiki/Unraid.md) — generic Unraid install / Force Update
- [AGENTS.md](../../AGENTS.md) — Cursor Cloud / agent quickstart (links here)
