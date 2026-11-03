# 360 Review — run 2026-10-28-2

| Batch | Status | Completed | Commit reviewed | Notes |
|---|---|---|---|---|
| 1 Foundation | done | 2026-10-29T03:40:00Z | 94fcd3f | `new` run (folder `2026-10-28/` kept). Survey QA `:8792` Path A `projectionist-qa:wip` of GitHub main 1.37.72 + PR #188. Hub `:1.37.72` lacks #188 — not CA/prod proof. Never prod `:8788` / smartmap `:8790`. |
| 2 Experience | done | 2026-10-29T14:22:27Z | 94fcd3f | QA `:8792` Path A `1.37.72`. Signed-in Play/Live walk (`qa-youth`, `qa-owner`). Grades: UX C, Visual C, A11Y C−. New: UX-041–045, VIS-028, A11Y-027. Live stayed Off. Never prod `:8788` / smartmap `:8790`. |
| 3 Trust | done | 2026-10-29T14:52:57Z | 94fcd3f | Grades: SEC C+ (18 weaknesses, 3 High, 0 Critical), PRIV C− (16 weaknesses, 1 Critical, 9 High). Code cites are `94fcd3f` (working tree was 36 behind). QA `:8792` observation only; no exploit traffic. No application code changed. |
| 4 Engineering | done | 2026-10-29T15:34:17Z | 94fcd3f | Grades: ARCH C+ (18 weaknesses, 4 High, 0 Critical), PERF C− (18 weaknesses, 6 High, 0 Critical). Code cites are `94fcd3f` (working tree was 36 behind). Measurements from QA `:8792` only (read-only GETs plus 5 parallel Movies reads); host checks read-only via `ssh automat`. No application code changed. |
| 5 Growth & Operations | done | 2026-10-30T22:11:07Z | 94fcd3f | Grades: GRO C− (19 weaknesses, 4 High, 0 Critical), OPS C+ (13 weaknesses; High: OPS-010–012, OPS-014–016 + opportunities OPS-030–031). Code cites `94fcd3f`. QA `:8792` only. OPS checklist gaps closed (Part A cites OPS-030/031; Current state/Root cause on OPS-031/033/034). No application code changed. |
| 6 Synthesis | done | 2026-10-30T23:21:12Z | 94fcd3f | Overall grade **C+**. CSV 237 rows = Weakness+Opportunity+Remove. Red team: 5 factual corrections, no grade changes. No application code changed. |

## Handoff notes

**Survey URL (only):** `http://10.10.1.202:8792` — confirm `GET /api/health` → `{"status":"ok","version":"1.37.72"}`. Image is Path A host build `projectionist-qa:wip` of `origin/main` `94fcd3f`, **not** Hub CA proof. QA theater if needed: `:8795` (not prod `:8791`).

**Never:** prod `http://10.10.1.202:8788`, smartmap `:8790`, VIP CDN, SSH tunnels as version truth. Do not stop those services. Do not bind `:8790`. Do not Hub/Automat **prod** rollout.

**How to start QA:** already running. If down, follow host `/mnt/user/appdata/projectionist-qa-scripts/qa-runs/QA-LIFECYCLE.md` + `QA-REDEPLOY.md` (Path B Hub pull preferred when a tag includes this SHA; until then Path A is recon-only). SSH host alias **`automat`**.

**Accounts:** usernames `qa-owner`, `qa-member`, `qa-youth` from `/mnt/user/appdata/projectionist-qa-scripts/.env.qa` (`QA_OWNER_USER` / `QA_MEMBER_USER` / `QA_YOUTH_USER`). **Do not copy passwords into review docs.** Local username/password only on this sidecar (no Plex PIN on `/login`).

**Observed flags:** `multi_user_enabled`, `setup_state=active`, Live **Off**, LLM **unset**, 5,391 indexed, 88% unwatched, 0% rated. Persona still “Curator” / “The Professor” in chat.

**Prior run:** `docs/reviews/2026-10-28/` is unfinished and contains **prod** screenshots — do not reuse.

**This run screenshots:** `docs/reviews/2026-10-28-2/screenshots/` (`qa_*`). Later batches add their own prefixes (`ux_`, `vis_`, `a11y_`, …). Re-walk QA yourselves; do not read other department docs until Batch 6.

**Follow-ups for later batches:** Youth R-rated thread history still openable (`ux_youth_r_thread_1440.png`) — Trust. Youth Continue Watching listed South Park while Play 403s R-rated URLs and search hid Don't Look Up (UX-044 / Trust). About CHANGELOG DOM size (Perf). Member `/admin` redirect (Security re-prove API). Rating loop (Product): owner end card has no stars and says "last episode" for a movie (UX-012/043). Settings → Sign out vs `clearAuthSnapshot()` (UX-039). Hub `poster_url` `""` (VIS-027). Play: autoplay, idle OSD `aria-hidden`, Escape stays on `/watch` (UX-042 / A11Y-023). Youth 403 offers only Try again (A11Y-027). `/library` Shelves blank (UX-040). `/live` Off: owner told to ask the owner (UX-017); phone 390 stuck on guide stall (UX-045). Live **On** not exercised (left Off).

**Experience screenshots:** `docs/reviews/2026-10-28-2/screenshots/ux_*.png`. Do not read `02_`, `03_`, or `04_` until Batch 6.

**Trust follow-ups (re-prove yourselves; do not read `06_` or `07_` until Batch 6):** Agent tools vs REST role checks (bad-file mark, Seerr approve, self-confirmed *arr). `POST /api/chat/stream` thread ownership. Leftmost `X-Forwarded-For` when proxy headers are trusted. Account purge/deletion vs the Privacy page. Owner taste export and snapshot zip scope. Youth newsletter, Continue Watching, and household "you watched" fallback. Google Fonts on every page including `/privacy`. Settings sign-out leaves the thread id in `localStorage`; creating a local account replaces the owner session cookie. SEC walked QA as guest/owner only (browser was shared); PRIV walked owner, member, and youth. Screenshots: `sec_*.png`, `priv_*.png`. Live stayed Off. LLM unset, so provider payloads were not observed. Never prod `:8788` / smartmap `:8790`.

**Engineering follow-ups (re-prove yourselves; do not read `08_` or `09_` until Batch 6):** Friction clusters around delivery safety and data/policy seams: CI and Lint are red on `main` and do not block merges or rollouts, `settings.json` writes are non-atomic and a parse failure falls back to "no login", account deletion leaves user-keyed rows behind, and youth/authorization checks are spread across many files and entry points. On performance and recovery, heavy library queries block the shared event loop (health and theater stall), the 2.08 MiB (2,178,954 bytes) uncompressed JS bundle is served without compression or cache headers, and prod relies on weekly backups that are unverified and never restore-tested. Chat first token and Play start were not measurable (LLM unset, no live Plex stream). Live stayed Off. Never prod `:8788` / smartmap `:8790`.

**Growth & Operations follow-ups (do not read `05_` or `10_` until Batch 6):** Streaming chat emits almost no interaction events; nothing attributes a play to a recommendation (north star). Newsletters and nudges skip the youth rating gate. Curator naming drift ("The Professor" / CURATOR / storage names in inbox). Connections show Connected ✓ while secrets MAC-mismatch floods Logs and Tasks skip enrichment. Access lacks age/bulk deny; Members table is accident-prone; no owner-mediated local password recovery. Monday pass is copy + Health tiles, not an interactive checklist; Tasks is a full scheduler dump. Screenshots: `gro_*.png`, `ops_*.png`. Live Off, LLM unset, Mail off. Never prod `:8788` / smartmap `:8790`.
