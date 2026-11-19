# Product map

Living product truth for Projectionist — positioning, surface map, SWOT, sequenced priorities, and parked Tunarr-era non-goals. Baseline tip: Automat **1.40.1** (trust residuals on **1.40.0** Admin + YIR). Do not reopen Tunarr dual-watch, Phase 6 gift queue, or Live **new** channel types (PRD-007 freeze).

Related: [HELP.md](HELP.md) · [MEDIA_INTELLIGENCE.md](MEDIA_INTELLIGENCE.md) · [DELIGHT-WISHLIST.md](DELIGHT-WISHLIST.md) · [RELEASE.md](RELEASE.md) · [README](../README.md) · [2026-11-18 department rescore](reviews/2026-11-18/2026-11-18_department-rescore.md)

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
| Post-1.40.1 department rescore (path-to-A note) | **2026-11-18** — overall ~**B−** (was C+ / Security D); **not A** |

---

## Sequenced priorities (post-1.40.1)

1. **E6 design-system footholds** — opportunistic Button migration, stylelint / tokens, remaining A11Y (trailer focus trap); Admin density from 1.40 is the foothold (no brand rewrite).
2. **E5 owner operability** — invite lifecycle, break-glass CLI, SLOs, support bundle (backups / Needs attention already shipped).
3. **GRO-012 packaging fix** — ship `og-card.png` + `manifest.webmanifest` into Hub `frontend/dist` (meta already points at them).
4. **Growth / join leftovers** — GRO-013–017/022 lifecycle copy; join first-run; keep Live freeze.
5. **Explore e2e flake** — `title-detail-open-full` is CI hygiene when touching Explore (not a merge blocker for trust patches).

Path-to-A rescore: [2026-11-18 note](reviews/2026-11-18/2026-11-18_department-rescore.md). Do **not** claim department **A** until Highs stay closed in the running Hub-pulled build and a later rescore says so.

---

## Live scope freeze (PRD-007)

Live takes **no new channel types and no new schedule features**: no new station kinds, dayparts, slot rules, rotation modes, or lineup sources. Work on Live is limited to fixes, accessibility, captions on existing stations, and performance. Weather channel expansion (existing station) remains the only carve-out.

## Parked / sunset (near-term non-goals)

- Projectionist-managed Plex HDHomeRun / XMLTV attach or tuner rebuild
- Tunarr Docker orchestration / admin auth / image pin pilots
- Daypart / Chaos schedule-slots via Tunarr OpenAPI
- Newspaper EPG / re-run starter pack against Tunarr
- Gift queue, trust diary, Admin House seasonal veto
- Postgres / Redis; external "on Netflix" where-to-watch
- Vite 8 / React Router 7 majors until intentionally unparked
- Lobby campaign polish unless the house relies on `:8791`
- Cookie rename Breaking minor; Database god-growth

Delight Phase 6 / 1.36 is **historical substrate**. Living sequencing lives here and in the successor backlog plan under `~/.cursor/plans/`.
