# Release runbook

Step-by-step maintainer / agent guide for shipping a Projectionist version. Follow this document whenever you bump a version, edit `CHANGELOG.md` for a release, cut a GitHub release, or push Docker images. Do not rediscover the process from chat history.

**Audience:** developers and agents. Voice: direct and technical ([DOCS_STYLE.md](DOCS_STYLE.md) developer column).

**Related:** [DOCKER.md](DOCKER.md) (image publish details) · [TESTING.md](TESTING.md) (CA / e2e layers) · [DOCS_STYLE.md](DOCS_STYLE.md) (Highlights voice) · [ops/AUTOMAT.md](ops/AUTOMAT.md) (Automat LAN / version truth / QA teardown) · host-local QA lifecycle (`/Volumes/appdata/projectionist-qa-scripts/qa-runs/QA-LIFECYCLE.md`)

---

## Authority & coordination

- **Commit / push / tag / `gh release` / Docker Hub push** only when the user explicitly asks to ship a release (or clearly asks to commit/push those steps). Otherwise prepare files and stop.
- Do **not** bump versions or cut a release while another agent is mid-feature on the same branch unless the user coordinates it.
- Prefer `main` (or the branch the user names). Expect a clean enough tree that release-only files are intentional; do not discard unrelated in-progress work.

---

## Preflight

1. Confirm the intended semver `X.Y.Z` (patch for fixes, minor for features, major only when intentionally breaking).
2. Confirm no conflicting in-flight version bump on the branch (`git status`, recent `CHANGELOG.md` / `_version.py`).
3. Ensure Docker buildx + Hub login are available before the image step (`docker buildx version`, `docker info`). On Mac without Desktop, Colima must be running ([DOCKER.md](DOCKER.md)).

### Version parity (required)

Bump **all** of these to the same `X.Y.Z` (`tests/test_version.py` enforces every row except the README badge):

| File | Field / what to set |
|------|---------------------|
| `projectionist/_version.py` | `__version__` (runtime / imports; source of truth for the test) |
| `package.json` | `"version"` |
| `package-lock.json` | top-level `"version"` **and** `packages[""].version` |
| `frontend/package.json` | `"version"` |
| `frontend/package-lock.json` | top-level `"version"` **and** `packages[""].version` |
| `pyproject.toml` | `[project].version` |
| `templates/projectionist.xml` | HTML comment `Projectionist X.Y.Z`; leading `### X.Y.Z` under `<Changes>`; Description pin examples ``:`X.Y` / `:`X.Y.Z`` |
| `unraid/projectionist.xml` | **Identical** to `templates/projectionist.xml` (CA still uses both paths) |
| `README.md` | Version badge (`badge/version-X.Y.Z-…`) — keep in lockstep; not asserted by `test_version` |

Canonical Unraid Repository tag: `romwil/projectionist:latest`. During the compatibility window, `scripts/docker-release.sh` also dual-tags identical digests to `romwil/curatorx:*`. Legacy `templates/curatorx.xml` / `unraid/curatorx.xml` stay as thin CA pointers (not version-lockstep).

Docker image identity does **not** come from those files at build time — `scripts/docker-release.sh` passes `PROJECTIONIST_VERSION` (and `CURATORX_VERSION` alias) into OCI labels and `/app/.build-info`.

---

## Tests (must pass before tag)

From repo root, with the project venv and frontend deps installed:

```bash
# Backend — local addopts enforce --cov-fail-under=74 (see pyproject.toml)
.venv/bin/python -m pytest tests/ -v

# Frontend unit (node --test)
cd frontend && npm run test:unit

# ESLint — 0 errors required; pre-existing warnings are OK
cd frontend && npm run lint

# Production build
cd frontend && npm run build
```

Optional CA / e2e layers: [TESTING.md](TESTING.md). CI (`.github/workflows/ci.yml`) runs frontend unit + build + pytest + Playwright with the same coverage floor as local (`--cov-fail-under=74`).

### Recommended (not CI-mandatory)

Run these before tagging when the ship matches the trigger. Lab / QA only — never prod `:8788`.

| Trigger | Recommended gate | Command / action |
|---------|------------------|------------------|
| Security-touching (authz, MCP, prompt fencing, sessions, webhooks, headers, packaging) | Pentest harness green | `python3 scripts/security/pentest/run-checklist.py` (disposable lab; see [security/pentests/README.md](security/pentests/README.md)) |
| Chrome / gating / role-shell ships | Interactive UI QA **delta** on `:8790` | `.cursor/skills/interactive-ui-qa` — open bugs + tagged IDs; never `:8788` |
| Major chrome / periodic audit | Absolute baseline refresh | Same skill, mode `full` → host `qa-runs/ABSOLUTE_BASELINE.md` |

Layer map: [Feature testing environment blueprint](superpowers/specs/2026-07-29-feature-testing-environment-blueprint.md).

Record pass counts / coverage in the CHANGELOG `### Verification` section (match recent entries).

---

## CHANGELOG (two-part)

1. Move work out of `## [Unreleased]` into a new heading:

   ```markdown
   ## [X.Y.Z] — YYYY-MM-DD
   ```

   Use an em dash `—` (generator also accepts en dash / hyphen). Date is UTC calendar day of the ship.

2. One short summary paragraph (member/owner readable).

3. **`### Highlights`** — 2–4 benefit-led bullets (What’s New modal). No jargon. See [DOCS_STYLE.md](DOCS_STYLE.md#release-notes-highlights-convention).

4. Technical sections as needed: `### Added` / `### Changed` / `### Fixed` / `### Security` / `### Verification` (and others if useful).

5. Leave `## [Unreleased]` as an empty placeholder at the top.

Docs gate: user-facing behavior changes update the relevant guide **in the same change** ([DOCS_STYLE.md](DOCS_STYLE.md)).

---

## release-notes.json

```bash
./scripts/generate-release-notes.sh --require-version X.Y.Z
```

Writes `frontend/public/release-notes.json`. The Docker release script runs this again before `buildx`. Commit the regenerated JSON with the release.

`GET /release-notes.json` is served from `frontend/dist` or `frontend/public` (newer wins) — see `tests/test_release_notes_static.py`.

---

## Commit / tag / push

Only when the user asked to ship:

1. Stage release files + code for this version (do not mix unrelated WIP).
2. Commit message style (recent practice):

   ```text
   vX.Y.Z: <short Highlights-style title>
   ```

   Body: 1–3 sentences of why / user impact.

3. Create an annotated tag matching the version:

   ```bash
   git tag -a "vX.Y.Z" -m "vX.Y.Z"
   git push origin HEAD
   git push origin "vX.Y.Z"
   ```

---

## GitHub release

```bash
gh release create "vX.Y.Z" --title "vX.Y.Z" --notes "$(cat <<'EOF'
## Highlights
- **…** (copy from CHANGELOG ### Highlights)

See CHANGELOG.md for the full technical notes.
EOF
)"
```

Recent example: [v1.19.4](https://github.com/romwil/projectionist/releases/tag/v1.19.4). If `gh` reports the release already exists, update notes only when asked.

---

## Multi-arch Docker Hub

Canonical image: **`romwil/projectionist`**. Compat dual-tag (same digests): **`romwil/curatorx`**. Platforms: `linux/amd64,linux/arm64`.

```bash
./scripts/docker-release.sh X.Y.Z
# optional:
# ./scripts/docker-release.sh X.Y.Z --also-line X.Y   # default already derives X.Y
# ./scripts/docker-release.sh X.Y.Z --date-tag        # also :latest-YYYYMMDD
```

Tags pushed on `romwil/projectionist`: `:X.Y.Z`, `:X.Y`, `:latest` (and `:latest-YYYYMMDD` with `--date-tag`). The script then retags identical manifests to `romwil/curatorx:*` for the compatibility window.

The script sets `--provenance=false --sbom=false` so Unraid Dockerman sees Docker v2 **manifest lists** (not OCI attestation indexes). It prints Hub digests — paste into notes or keep for Unraid verify.

Full Unraid / Force Update caveats: [DOCKER.md](DOCKER.md).

---

## Spin down maintainer QA (after Hub publish)

After a successful Docker Hub publish (`scripts/docker-release.sh`), **spin down the maintainer QA container** (`projectionist-qa` on `:8790`) unless an active Interactive UI QA / Playwright role suite / agent probe is in progress. Spin up again when the next test pass needs `:8790`.

- **Do** stop only QA: `ssh automat 'docker stop projectionist-qa'` (keeps image + volume for a fast `docker start`).
- **Do not** stop, rm, or recreate production `projectionist` / `:8788`.
- Full config / volumes / spin-up / spin-down runbook (host-local, not in this git tree): `/Volumes/appdata/projectionist-qa-scripts/qa-runs/QA-LIFECYCLE.md` (WIP recreate: same folder’s `QA-REDEPLOY.md`).

---

## Post-release verification

```bash
# Hub manifest list (expect docker.distribution.manifest.list.v2+json)
docker buildx imagetools inspect romwil/projectionist:X.Y.Z | head -30

# Digests for :X.Y.Z and :latest should match this ship (and match dual-tagged curatorx)
docker buildx imagetools inspect romwil/projectionist:X.Y.Z --format '{{.Manifest.Digest}}'
docker buildx imagetools inspect romwil/projectionist:latest --format '{{.Manifest.Digest}}'
docker buildx imagetools inspect romwil/curatorx:X.Y.Z --format '{{.Manifest.Digest}}'
docker buildx imagetools inspect romwil/curatorx:latest --format '{{.Manifest.Digest}}'

# GitHub
gh release view "vX.Y.Z"

# Optional Unraid host (config preserved)
# cd /mnt/user/appdata/projectionist && ./rollout.sh X.Y.Z
# docker exec projectionist cat /app/.build-info
```

Confirm About / What’s New shows the new version after the container runs the new image (`/release-notes.json` includes `X.Y.Z`).

A follow-up `chore: refresh release-notes.json timestamp for vX.Y.Z` commit sometimes appears when the generator is re-run after tag — avoid needless churn; one generate-and-commit with the release is enough.

---

## Common failure modes

| Symptom | Cause | Fix |
|---------|--------|-----|
| `generate-release-notes.sh` / docker-release fails on `--require-version` | Missing `## [X.Y.Z] — YYYY-MM-DD` in `CHANGELOG.md` | Add the heading (correct dash/date) |
| Docker build: `release-notes.json missing` | Generator not run before image build | `./scripts/generate-release-notes.sh` (docker-release does this; bare `docker build` does not) |
| Unraid Force Update **0 B** / stale UI | Local `:latest` digest mapping not re-resolved | `docker pull` / `rollout.sh` / `unraid-force-pull.sh` — see [DOCKER.md](DOCKER.md) |
| Dockerman “not available” | OCI index with attestations | Always use `scripts/docker-release.sh` (provenance/sbom off) |
| `test_version` fails | Lockstep mismatch among `_version.py`, package.json(s), lockfiles, `pyproject.toml`, or Unraid XMLs | Align every file in the Version parity table (keep the two XML templates identical) |
| Coverage below 74% | Local pytest addopts / CI `--cov-fail-under=74` | Fix tests or coverage before tagging |
| ESLint errors | New violations | Fix to **0 errors** (warnings may remain) |
| buildx / push fails on Mac | No runtime / not logged in | Start Colima or Desktop; `docker login` |
| Agent cut a release unprompted | Violated commit policy | Stop; only ship when user asks |

---

## Agent checklist (copy)

- [ ] User explicitly asked to release / commit+push this ship
- [ ] No conflicting WIP version bump
- [ ] Versions aligned (`_version.py`, root + frontend `package.json` + lockfiles, `pyproject.toml`, both Unraid XMLs identical, README badge)
- [ ] Tests: pytest (≥74% cov, same floor in CI), `npm run test:unit`, `npm run lint` (0 errors), `npm run build`
- [ ] `CHANGELOG.md`: `## [X.Y.Z]`, Highlights + technical + Verification
- [ ] Docs updated if user-facing
- [ ] *(Recommended)* Security-touching ship: pentest harness green (`python3 scripts/security/pentest/run-checklist.py`)
- [ ] *(Recommended)* Chrome / gating ship: Interactive UI QA delta on `:8790` (never `:8788`)
- [ ] `./scripts/generate-release-notes.sh --require-version X.Y.Z`
- [ ] Commit `vX.Y.Z: …`, tag `vX.Y.Z`, push commit + tag
- [ ] `gh release create` with Highlights
- [ ] `./scripts/docker-release.sh X.Y.Z`
- [ ] Post-release Hub / `gh` / optional Unraid verify
- [ ] Spin down `projectionist-qa` (`:8790`) unless a QA/test campaign is still running — never touch prod `projectionist` / `:8788` (host runbook: `projectionist-qa-scripts/qa-runs/QA-LIFECYCLE.md`)
