# 360 Review — run 2026-11-01

Invoked as `/review360 all` (all six batches in one coordinator session; each department runs as its own independent subagent). Prior run `2026-10-28-2` is complete and kept. This run does not read it until Batch 6, which uses it only to flag regressions or progress.

| Batch | Status | Completed | Commit reviewed | Notes |
|---|---|---|---|---|
| 1 Foundation | done | 2026-11-02T06:40:00Z | 05274cf | Code: GitHub `main` after PR #189 merge = `05274cf` = tag `v1.38.0`. QA `:8792` reports 1.38.0. Platform map: 26 sacred cows, `map_*` screenshots, owner session only. PRD grade **C+** (15 weaknesses, 6 strengths, 4 opportunities; 7 High, 0 Critical). |
| 2 Experience | done | 2026-11-02T20:35:00Z | 05274cf | UX **C+** (UX-001–013). Visual **C+** (VIS, 22 findings; written by subagent before it was cut off, self-check present). Accessibility **C** (A11Y-001–012), written by the coordinator after the A11Y subagent died without output: code-first plus recon walk evidence, axe not run in a browser. |
| 3 Trust | done | 2026-11-02T18:23:00Z | 05274cf | Files already complete; not rewritten. SEC grade **D** (High: SEC-006–SEC-010, no Critical confirmed). PRIV grade **C** (Critical-class household misattribution called out as PRIV-001; page promises do not match purge). |
| 4 Engineering | done | 2026-11-02T18:57:00Z | 05274cf | Recovered in-process after the batch 4 jobs were lost. ARCH grade **B-** (ARCH-001–014). PERF grade **C+** (PERF-001–014). Pytest reuse: 2815 passed, 43 skipped, 77.01% coverage (`/tmp/review360-arch-pytest.log`); `--timeout=600` failure was a missing plugin, not a product defect. Frontend build reused `/tmp/review360-perf-root` (full tree). Entry chunk `index-CSQsR6Mb.js` 1,054.11 kB, gzip 321 kB, immutable cache confirmed on QA. |
| 5 Growth & Operations | done | 2026-11-02T19:12:00Z | 05274cf | GRO **C** (GRO-001–024). OPS **C+** (19 findings: 5 strengths, 11 weaknesses, 3 opportunities; 0 Critical). Both written by subagents before they were cut off; self-checks present. |
| 6 Synthesis | done | 2026-11-02T20:36:00Z | 05274cf | Written by the coordinator (red team run from documents only, because delegated agents kept getting cut off; see `21_…` independence note). Overall **C+** (same as 10-28-2; 7 departments up, Product and Security down, Ops flat). 184 findings, 44 strengths, 140 backlog rows; 0 Critical, 40 High. Self-check: IDs unique across departments; CSV rows (140) = weaknesses + opportunities + removes (140); no commit drift. Red team corrected `04_…` (A11Y-010 scoped to token level, VIS-003 exception) and `09_…` (dangling PERF-010 → PERF-007), each logged in a changelog. Five big decisions (BD-1 to BD-5). |

**Run status: COMPLETE** (2026-11-02T20:36:00Z). Executive summary: `30_2026-11-01_executive-summary-and-roadmap.md`. Backlog: `2026-11-01_backlog.csv`. Nothing was shipped, tagged, pushed, or rolled out as part of this review.

## Handoff notes

**Code under review:** `05274cf` (merge of [PR #189](https://github.com/romwil/projectionist/pull/189), tag `v1.38.0`, version 1.38.0). It is 14 commits ahead of the previous run's `94fcd3f` (household invite launch phases 1–7 plus Live guide start/end times). Read code from the read-only extracted snapshot `/tmp/review360-05274cf`, or with `git -C /Users/willrompala/code/projectionist show 05274cf:<path>`. The laptop working tree (`c7fb5ee`) is behind and must not be used as code truth. Cite code as `05274cf:path:line`. **Never** edit, checkout, reset, or commit in `/tmp/projectionist-phase*`.

**Survey URL (only):** `http://10.10.1.202:8792` (`GET /api/health` → `{"status":"ok","version":"1.38.0"}`). Live is **on**: the guide has 4 channels (Comedian, Refer, Stand Special, Youth Safe), and 3 of them have shows. LLM chat is **enabled** (Anthropic provider; the saved key decrypts). **Do not start Watch or tune a Live channel** (that opens a shared Plex session). Chat sends are allowed sparingly (at most a few short prompts per department) because they spend provider credit.

**Never:** prod `:8788` (also 1.38.0, but off-limits), smartmap `:8790`, theater `:8791`, `https://projectionist.automat.vip`, `localhost:8788` (tunnel), SSH to `automat`, any push, deploy, or rollout. Read-only HTTP to `:8792` only, with no exploit traffic. Do not read `.env` / `.env.qa`, and write no secrets or personal data into these docs.

**Accounts:** no QA passwords are available to this run (the credential file is off-limits). Use an existing signed-in browser session on `:8792` if one exists, and never sign out or switch accounts. Otherwise review signed-in surfaces from code and state that limit.

**Batch 1 recon handoff (from `00_2026-11-01_platform-map.md`):**
- The shared browser holds a QA **owner** session on `:8792`. Open your own tab and never sign out or switch accounts. No member or youth session exists, so review role gating from code (`primaryNav.ts`, `appNavItems.ts`, `AdminLayout.tsx`, `youth/rating_gate.py`).
- **Screenshots:** `browser_take_screenshot` timed out for recon, but CDP `Page.captureScreenshot` works. Decode the exact JSON file path your own call returns, not the newest file in the shared log folder. For 390px, use `deviceScaleFactor: 1` and clear the override afterward. Save with your department prefix (`ux_`, `vis_`, `a11y_`, `sec_`, `priv_`, `arch_`, `perf_`, `gro_`, `ops_`).
- Recon sent one chat prompt, which created one thread. Keep each department to a few short prompts.
- Features report `live_channels_enabled: true` but `live_channels_ready: false`. Live is missing from nav, while `/live` still renders a guide (including a Weather row), and Admin calls Live "Warming". Do not tune.
- Unknown SPA URLs return raw JSON `{"detail":"Not Found"}`. The title page keeps a generic tab title and has no `<main>` landmark.
- Owners get a bulk "Delete" in the Search and Browse toolbars. The login page renders with the bottom nav for a signed-in user.
- Admin Overview shows Radarr and Sonarr as "connected but has no saved key". QA has zero usage in the last 7 days, so engagement can't be validated from data.
- **Scale:** `web/app.py` is 4,378 lines with 131 inline handlers, out of about 394 handlers in total. SQLite has 81 tables and 60 migrations. Everything runs in one process with a 33-task scheduler.
- Not walked live: signed-out visit (curl only), member/youth, Plex PIN/OIDC, invite redemption, setup wizard, Play/Live tune, theater, MCP, mail.
