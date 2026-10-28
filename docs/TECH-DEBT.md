# Tech debt — postpone parking lot

This file is **only postponed work**. Frozen bets and “not this week” items live here. Active P0/P1 work lives in PRs, not on this page. Do not copy the current build board here.

Developer audience. Product parks that already have a home are **pointers**, not a second plan.

---

## Frozen (reaffirm, do not reopen)

| Item | Why it stays parked |
|------|---------------------|
| **SQLite WAL**, single non-root container | Homelab pragmatism. No Postgres, no Redis, no worker queue. Reopen only if write-lock warnings are measured **and** libraries routinely exceed ~10–20k with heavy idle writes. |
| **No new `Database` god methods** | New domains are stores / mixins that own their tables. Do not grow `projectionist.library.db.Database`. |
| Cookie **`curatorx_session`**, legacy **`curatorx.db`**, compose/CA **`${CURATORX_*}`** twins | Python `CURATORX_*` dual-read already closed (1.34). Yanking the rest is a Breaking minor + Unraid CA note. Do not restore `X-CuratorX-Webhook-Secret`. |
| **Agent tool count frozen** — no plugin framework | Extra MCP personas wait until after the tools registry is split by domain. |
| Hub publish as Docker v2 **manifest lists** | `scripts/docker-release.sh` keeps `--provenance=false --sbom=false`. OCI attestation indexes make Unraid Force Update report “not available” / 0 B. |
| **AGPL coupling** | New releases are already AGPL-3.0-only ([PR #42](https://github.com/romwil/projectionist/pull/42)). Hub tags through **1.36.2** stay MIT. Do not attach leftover license/CA churn to unrelated slices. |

---

## Engineering later

| Item | Gate |
|------|------|
| Live **`publish.py` split** | After Live mounts `TheaterPlayer` (one theater shell). |
| Embeddings full-table **`json.loads`** / O(n) cosine (`get_embeddings`) | Until a **10k-library** measurement. Optional `sqlite-vec` stays a prefilter; `item_neighbors` stays the read cache. Architecture review **H8**. |
| **Jittered connector GET retries** | Idempotent reads only (429/5xx). Architecture review **M3**. |
| Bulk **IdleScheduler → `BaseAugmentationTask`** | After Phase C pilots. No second runner. Greenfield IdleScheduler / global-priority rewrite is out — miss queue in **1.37.57** is enough. |
| **Vite 8** + **React Router 7** | Dependabot may alert; not a 1.37.x program. Today: Vite 5 + RR 6. |
| Full **TSX rewrite** of the JSX SPA (~192 files on origin/main) | Own program, not a drive-by. |

---

## Product parks (do not schedule)

Unless product intent reverses. Detail stays in the linked docs:

- Live **newspaper EPG**, **coax** clone, docker-less AIO, replacing Plex Live chrome, **Tunarr** rewrite, **HDHomeRun** / XMLTV attach — [PRODUCT.md parked](PRODUCT.md#parked--sunset-near-term-non-goals), [live-channels-deferred](superpowers/plans/2026-07-29-live-channels-deferred.md).
- External **“on Netflix/Max”**; **2× on Live** (linear clock stays 1×); **Lobby** kiosk campaign (unless the house relies on `:8791`); **gift queue**; **trust diary** — [DELIGHT-WISHLIST parked inventory](DELIGHT-WISHLIST.md#parked-inventory-do-not-resurrect-as-the-plan).

---

## See also

- [PRODUCT.md](PRODUCT.md) — living product sequencing + Tunarr-era non-goals
- [DELIGHT-WISHLIST.md](DELIGHT-WISHLIST.md) — persona briefs; parked inventory is not the plan
- [ARCHITECTURE.md](ARCHITECTURE.md) — SQLite WAL + write serializer
- [reviews/2026-07-architecture-code-review.md](reviews/2026-07-architecture-code-review.md) — H8 embeddings, M3 GET retries
- [RELEASE.md](RELEASE.md) — Hub manifest lists vs OCI indexes
