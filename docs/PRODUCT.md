# Product map

Living product truth for Projectionist — positioning, surface map, SWOT, sequenced top 10, and parked Tunarr-era non-goals. Baseline tip: Automat **1.37.57+**. Media intelligence R1–R4 (1.37.54–57) is **done**; do not reopen that series.

Related: [HELP.md](HELP.md) · [MEDIA_INTELLIGENCE.md](MEDIA_INTELLIGENCE.md) · [DELIGHT-WISHLIST.md](DELIGHT-WISHLIST.md) · [README](../README.md)

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
| **Strengths** | Honest why + local index; Play / Explore / Inbox / native Live; owner stewardship; Hub-first Unraid |
| **Weaknesses** | Surface sprawl; couch trust gaps (captions, Live filler); stale Tunarr copy in older docs; cold shelves vs coverage % |
| **Opportunities** | Own the living-room TV path + named kinship as owner KPI; ruthless sunset of Tunarr-era surface area |
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

---

## Sequenced top 10

1. **Ship Play captions** — caption collision / sync trust on Play.
2. **Ship Live flex filler** — flex pad picture / lower-third honesty.
3. **Product-truth + PR triage** — this doc; README/HELP; park Tunarr deferred list; Phase 6 status honesty.
4. **Prove media intelligence on Automat** — explainable % vs raw; More Like This; inbox bridge.
5. **Explore For you** — `watched_bridge` rails (same refusal rules as inbox).
6. **Owner Library health ritual** — single Admin narrative (Named kinship + issues + purge + catch-up).
7. **Sunset pass** — Tunarr copy/ghosts, dead UI, honest hash-embedding label, guest doc drift.
8. **CW / shrunk Play nightly** — iPad open → resume → done.
9. **Phase 6 triage** — finish musts or park leftovers in DELIGHT-WISHLIST so 1.37 is the living roadmap.
10. **Episode-aware bridges** — TV seed depth (media intel next horizon).

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

Delight Phase 6 / 1.36 is **historical substrate** absorbed into 1.37 — see [DELIGHT-WISHLIST.md](DELIGHT-WISHLIST.md). Living platform sequencing lives here, not in Tunarr parking-lot bullets.
