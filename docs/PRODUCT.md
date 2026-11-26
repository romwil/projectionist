# Product map

Living product truth for Projectionist — positioning, surface map, SWOT, sequenced priorities, and parked Tunarr-era non-goals. Baseline tip: Automat **1.40.1** (trust residuals on **1.40.0** Admin + YIR). Do not reopen Tunarr dual-watch, Phase 6 gift queue, or Live **new** channel types (PRD-007 freeze).

Related: [HELP.md](HELP.md) · [MEDIA_INTELLIGENCE.md](MEDIA_INTELLIGENCE.md) · [DELIGHT-WISHLIST.md](DELIGHT-WISHLIST.md) · [RELEASE.md](RELEASE.md) · [README](../README.md) · [roadmap board](roadmap/README.md) · [EXPERIENCE.md](EXPERIENCE.md)

---

## Positioning

**Cinema intelligence for your personal archive** — local-first companion between Plex and *arr. Not another Plex skin.

Runtime watch surfaces: **library Play** (`/watch`) and **native Live** (`/live` + `DATA_DIR/live_lineup.json`). Tunarr is not the Live engine (removed from the running path in **1.37.51+**). Plex Live TV / OTA is the owner's Plex setup — Projectionist does not manage that tuner stack.

**Version truth:** Automat LAN `http://10.10.1.202:8788` is prod version / health / admin UI. `https://projectionist.automat.vip` is member-facing CDN/proxy — **not** version truth. Interactive UI QA is `:8792` only. Never stop smartmap `:8790` or prod `:8788` for QA. Do not resurrect Tunarr orchestration, HDHomeRun attach, or Phase 6 gift-queue tables. See [AUTOMAT.md](ops/AUTOMAT.md).

---

## Surface map

| Surface | Role |
|---------|------|
| **Chat** | Library-grounded curator; confirm before *arr writes |
| **Explore** | Browse hub, For you first, rails, language landings, Related titles / Tags (owner indexing telemetry lives in Admin) |
| **Play** (`/watch`) | In-app library playback (HLS via Plex); shrink / pop-out / phone |
| **Live** (`/live`) | Household stations from the native lineup — Guide / Watch / Weather / pop-out |
| **Inbox** | Recommendations, arrivals, digests, access requests, Live nudges |
| **Settings → Profile** | Engagement / pathways (My Journey folded here since 1.38) |
| **Admin** | Owner hub: Overview (Needs attention), Setup, Members, Experience, Health, Advanced |
| **Admin → Libraries** | Sync, *arr jobs, Repair, Rematch, Identify, Plex — path conflicts resolve in place |
| **Admin → Ops → Newsletters** | Weekly letter, member newsletter push, Year in Review send-test |
| **Admin → Library knowledge** | Coverage / kinship / staged augmentations (owner ops telemetry) |
| **Lobby Theater** (`:8791`) | LAN-only kiosk lightbox (enabled when the household relies on it) |
| **Booth Notes** (*planned*) | Commentary-style track during playback — see [TRACKS.md](TRACKS.md) |
| **Class / Study** (*planned*) | Lesson tracks with detours — see [TRACKS.md](TRACKS.md) |
| **Settings → Devices** | Paired companions (Apple TV today; kinds expand under NAT-005) |

---

## SWOT (short)

| | |
|--|--|
| **Strengths** | Honest why + local index; Admin Monday rail; YIR as household artifact; Play / Explore For you / Inbox / native Live; Hub-first Unraid |
| **Weaknesses** | Surface sprawl; Explore e2e flake; Named kinship still catching up vs similar-cache %; Vite 8 / RR 7 parked; GRO-012 packaging gap (`og-card` / webmanifest 404 in Hub image) |
| **Opportunities** | Design-system footholds from Admin density; owner operability (invite lifecycle, break-glass, SLOs); join / growth copy |
| **Threats** | Plex / Seerr absorbing discovery; couch breakage → "just use Plex"; claiming department **A** without Highs closed in the **running** Hub image |

---

## Already shipped (do not reopen)

| Item | Note |
|------|------|
| Native Live without Tunarr | 1.37.51+ |
| Media intelligence R1–R4 | 1.37.54–57 |
| Explore For you + Monday pass substrate | 1.37.58–59 |
| Path-to-A trust Highs (Youth confirm, setup lock, backups, …) | 1.38–1.39 line |
| Admin UX redesign Phase 1 (rail + Libraries hub) | **1.40.0** (#213) |
| Year in Review enrich (strips, rewatches, curator voice) | **1.40.0** (#211) |
| Trust residuals (Youth 7d gate, MCP newsletter removal, embeddings off_loop, OG/noindex, Explore telemetry) | **1.40.1** |
| Post-1.40.1 path-to-A check-in | **2026-11-18** — trust residuals shipped on 1.40.1; path-to-A not claimed yet; next theme is media-engine era + experience convergence |

---

## Sequenced priorities (post-1.40.1)

**Media-engine era** (source of truth: [roadmap board](roadmap/README.md)):

1. **ENG** — own the stream (playback engine) → **SES** shared sessions → **TML** timeline → **TRK** tracks; **NAT** capability contract threaded through.
2. **EXP** — experience convergence ([EXPERIENCE.md](EXPERIENCE.md)): Explore as home (EXP-013), vocabulary / *why* voice, tokens, cinema-first Explore.

**Still in the residual backlog:**

3. **E6 design-system footholds** — overlaps EXP-001; opportunistic Button migration, remaining A11Y; Admin density from 1.40 is the Workbench foothold.
4. **E5 owner operability** — invite lifecycle, break-glass CLI, SLOs (extend with ENG/SES: PERF-014), support bundle.
5. **GRO-012 packaging fix** — ship `og-card.png` + `manifest.webmanifest` into Hub `frontend/dist` when the image still 404s them.
6. **Growth / join leftovers** — GRO-013–017/022; join first-run (PRD-006) aligns with NAT-002.
7. **Explore e2e flake** — CI hygiene when touching Explore.

Live’s **PRD-007** freeze still holds: ENG-009 changes the *stream* under existing stations only.

Path-to-A: after the 2026-11-18 check-in, do **not** claim department **A** until Highs stay closed in the running Hub-pulled build and a later check-in says so. Living sequencing is the [roadmap board](roadmap/README.md).

---

## Live scope freeze (PRD-007)

Live takes **no new channel types and no new schedule features**: no new station kinds, dayparts, slot rules, rotation modes, or lineup sources. Work on Live is limited to fixes, accessibility, captions on existing stations, and performance. Weather channel expansion (existing station) remains the only carve-out.

## Community launch

The public community launch is still last and still has no date. Jellyfin (ENG-010) still comes before that launch. These three items are the start of the track. They follow container hardening (SEC-035) and the two doors (SEC-036). They are accepted and not this run.

| ID | Item | Why | Done when | Depends on | Status |
|----|------|-----|-----------|------------|--------|
| PRD-026 | **First-run setup and the install paths.** The wizard creates the owner with a passkey or a password plus TOTP, connects Plex, proposes a read-only path map from one probe per library, and can record a remote-access choice. It then invites the first member and offers a QR for a device. `docs/INSTALL.md` is the five-minute path for the Unraid template and for compose. After an update, the app can point at the release notes | A new household should reach a playing phone without a scavenger hunt | On a lab container, the wizard, a QR, and the Tailscale or Cloudflare walkthrough are enough to get a member's phone playing | SEC-030, SEC-031, SEC-035, SEC-036 | accepted |
| PRD-027 | **Doctor, the owner console, and a member report.** One check registry runs on demand, after an update, and daily. Each check has a plain explanation, fix steps, and a docs link. The first checks cover a settings file the app user cannot write, database integrity, disk space, Plex, the path map, ffmpeg, the clock, both doors, the exposure card, an available update, and mail. Admin → Household health shows the results. A red check banners the owner at sign-in and writes an inbox letter. A member can send a diagnostic report to that inbox with the device, the app version, the checks, and the error codes, and without viewing data | The product should name the broken thing and the fix | A root-owned settings file, a broken path map, an HTTP-only away address, and a missing owner second factor each produce the right sentence. The banner and the letter fire. A member's report arrives | SEC-035, SEC-036 | accepted |
| PRD-028 | **Guided remote access.** In-app walkthroughs sit beside `docs/REMOTE-ACCESS.md`: Tailscale or a VPN, Cloudflare Tunnel plus Access, a reverse proxy with forward-auth, and port forwarding. An optional Cloudflare assistant shows a plan from a pasted token and applies it only after the owner confirms. The token is not stored unless the owner opts in. Every change keeps an undo list. The assistant defaults to off. A household device on a cellular network can test `away` and `app_away` and report reachability and TLS back to Doctor | The safe path should be the one the wizard walks, and a token should not be stored by surprise | The assistant shows a plan against a mock API and applies nothing without confirmation. A phone test records a result for each address | SEC-036, PRD-027 | accepted |

**Client contract.** *Proposed* capability `doctor` ships with PRD-027. Owners can read the summary. A member report is a post with no viewing data. The platform handoff is `docs/roadmap/outbox/2026-11-26-PRD-027-support.md`. This file does not specify a client screen.

**Privacy.** Doctor checks and member reports stay on the household server. A report has no titles and no play history. The Cloudflare token is used for the confirmed session and is stored only when the owner opts in.

## Parked / sunset (near-term non-goals)

- Projectionist-managed Plex HDHomeRun / XMLTV attach or tuner rebuild
- Tunarr Docker orchestration / admin auth / image pin pilots
- Daypart / Chaos schedule-slots via Tunarr OpenAPI
- Newspaper EPG / re-run starter pack against Tunarr
- Gift queue, trust diary, Admin House seasonal veto
- Postgres / Redis; scraped or deep-linked "on Netflix" availability. Household streaming availability is EXP-023 (TMDB watch providers, JustWatch attribution, the server's own link). It is not a scraped deep link
- Vite 8 / React Router 7 majors until intentionally unparked
- Lobby campaign polish unless the house relies on `:8791`
- Cookie rename Breaking minor; Database god-growth

Delight Phase 6 / 1.36 is **historical substrate**. Living sequencing lives here and in the successor backlog plan under `~/.cursor/plans/`.
