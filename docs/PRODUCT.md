# Product map

Living product truth for Projectionist — positioning, surface map, SWOT, sequenced top 10, and parked Tunarr-era non-goals. Baseline tip: Automat **1.37.58** substrate; this ship is **1.37.59**. Media intelligence R1–R4 (1.37.54–57) and the 1.37.58 platform tranche are **done**. Do not reopen those series.

Related: [HELP.md](HELP.md) · [MEDIA_INTELLIGENCE.md](MEDIA_INTELLIGENCE.md) · [DELIGHT-WISHLIST.md](DELIGHT-WISHLIST.md) (BA delight briefs) · [delight-wishlist-delivery](superpowers/plans/2026-10-23-delight-wishlist-delivery.md) · [README](../README.md)

---

## Positioning

**Cinema intelligence for your personal archive** — local-first companion between Plex and *arr. Not another Plex skin.

Runtime watch surfaces: **library Play** (`/watch`) and **native Live** (`/live` + `DATA_DIR/live_lineup.json`). Tunarr is not the Live engine (removed from the running path in **1.37.51+**). Plex Live TV / OTA is the owner’s Plex setup — Projectionist does not manage that tuner stack.

---

## Surface map

| Surface | Role |
|---------|------|
| **Chat** | Library-grounded curator; confirm before *arr writes |
| **Explore** | Browse hub, rails, language landings, Related titles / Tags |
| **Play** (`/watch`) | In-app library playback (HLS via Plex); shrink / pop-out / phone |
| **Live** (`/live`) | Household stations from the native lineup — Guide / Watch / Weather / pop-out |
| **Inbox** | Recommendations, arrivals, digests, access requests, Live nudges |
| **My Journey** | Engagement / pathways |
| **Admin → Live Channels** | Owner craft: stations, rotation, seasonal shelves, continuity |
| **Admin → Libraries / Issues / Ops** | Stewardship, purge, newsletters, health |
| **Lobby Theater** (`:8791`) | LAN-only kiosk lightbox (park polish unless the house relies on it) |

---

## SWOT (short)

| | |
|--|--|
| **Strengths** | Honest why + local index; Play / Explore For you / Inbox / native Live; Named kinship as owner KPI; Hub-first Unraid |
| **Weaknesses** | Surface sprawl; iPad Safari may ignore Play 2x on live-like HLS; Named kinship still catching up vs similar-cache % |
| **Opportunities** | Warm explainable kinship on opened titles; Monday pass as the owner ritual; keep Tunarr-era doors closed |
| **Threats** | Plex / Seerr absorbing discovery; couch breakage → “just use Plex”; scope into a full media OS |

---

## Already shipped (do not reopen)

| Item | Note |
|------|------|
| Native Live without Tunarr | 1.37.51+ |
| Schedule rotation rebuild (one-title loops) | 1.37.53 |
| Media intelligence R1–R4 | 1.37.54–57 |
| Language landing + Movies/TV language filter | 1.37.43 |
| Inbox mailbox + named recommendation reasons | 1.37.44 |
| Full remove without *arr + progress | 1.37.48–50 |
| Explore For you (`watched_bridge`) | 1.37.58 |
| Owner Library health ritual | 1.37.58 |
| Phase 6 triage (shipped vs parked) | 1.37.58 |
| Episode-aware TV bridges | 1.37.58 |
| Play captions + Live flex filler | 1.37.58 |
| Play buffering OSD + hold-to-2x | 1.37.59 |
| For you as first Explore rail | 1.37.59 |
| Monday pass owner ritual | 1.37.59 |

---

## Sequenced top 10

**1.37.58 substrate is done.** This ship (1.37.59) closes remaining owner/user gaps:

1. **Warm explainable kinship** — idle still annotates cosine-only neighbors; Named kinship % is the owner KPI (Automat 1.37.58 snapshot ~72.9% — higher on opened titles, not a fake 100%).
2. **Couch-check Play + Live** — one caption layer + offset; Live flex filler shows a picture. Buffering OSD + hold-to-2x on library Play.
3. **For you as Explore default** — first rail; empty means no named link to something you finished; never cosine filler; one For you, not a leftover weekly persona rail.
4. **Owner Monday pass** — ~20 minutes: Named kinship on opened titles → open issues → purge pressure → Scheduled Tasks catch-up.
5. **Hash-embedding honesty** — `hash-fallback` labeled on Admin knowledge and the Explore coverage strip.
6. **Continue Watching nightly path** — Explore/CW → Play → shrink/resume. Lobby `:8791` and MCP are optional owner tools.
7. **Episode bridges** — finishing a TV episode seeds For you from **that episode’s plot**, not a random movie. No episode KG.
8. **Ghost doors closed** — Tunarr not in README key capabilities or Live HELP lead; guest is not a household role; unmounted inbox is gone.
9. **Phase 6 parked** — gift queue, trust diary, Admin House seasonal veto are not in product. See [DELIGHT-WISHLIST.md](DELIGHT-WISHLIST.md#parked-inventory-do-not-resurrect-as-the-plan).
10. **Play buffering + press-and-hold 2x** — library Play only. Live TV stays 1x. iPad Safari may ignore `playbackRate`; the 2x chip shows only when the element reports rate 2.

---

## Parked / sunset (near-term non-goals)

From the Tunarr dual-watch era and [live-channels-deferred](superpowers/plans/2026-07-29-live-channels-deferred.md) — **do not schedule** unless product intent reverses:

- Projectionist-managed Plex HDHomeRun / XMLTV attach or tuner rebuild
- Tunarr Docker orchestration / admin auth / image pin pilots
- Daypart / Chaos schedule-slots via Tunarr OpenAPI
- Newspaper EPG / re-run starter pack against Tunarr
- Full closed-loop IdleScheduler rewrite (miss queue in 1.37.57 is enough for now)
- Postgres / Redis
- External “on Netflix” where-to-watch
- Lobby kiosk polish (unless the house relies on `:8791`)

Delight Phase 6 / 1.36 is **historical substrate** ([DELIGHT-WISHLIST.md](DELIGHT-WISHLIST.md) Archive). Gift queue, trust diary, and Admin House seasonal preview/veto stay parked — they are not implied doors. Living platform sequencing lives here; next delight work is the BA briefs in [DELIGHT-WISHLIST.md](DELIGHT-WISHLIST.md) sequenced by [delight-wishlist-delivery](superpowers/plans/2026-10-23-delight-wishlist-delivery.md).
