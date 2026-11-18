# Department rescore — 2026-11-18

**Build under test:** Automat QA Path B Hub pull `romwil/projectionist:1.40.1` (`rev 6f00de6d`, digest `sha256:c6c5e4adf565…`) on `http://10.10.1.202:8792`.  
**Prod at time of note:** `http://10.10.1.202:8788` → **1.40.1** (same Hub tag; `rollout.sh` OK). smartmap `:8790` left running.  
**Method:** Interactive UI QA skill (authored surfaces) + API probes for trust residuals. Owner + member dual-role. QA spun down after.

This is a **rescore note**, not a full 360. Do **not** treat it as department **A**.

---

## Verdict vs Nov-1 (C+ / Security D)

| Department | Nov-1 | 2026-11-18 | Delta | Why (evidence on running 1.40.1) |
|---|---|---|---|---|
| Security | **D** | **C+** | ↑ | Member `/admin` soft-lands on Settings/Profile; owner Admin rail intact; Youth memory path ships 7d gate + `youth_memory_read` audit symbol. Household Highs from the trust arc are largely closed in-product. Still not hardened for every leftover SEC matrix / step-up item. |
| Privacy | C | **B−** | ↑ | Privacy page still admits gaps; `weekly_newsletter_preview` removed from MCP (`PRIV-004`); Youth review gate present. Not A: packaging/promise leftovers remain. |
| Product | C+ | **B−** | ↑ | Admin hub + Libraries, Ops → Newsletters + Year in Review, Explore For you, Live freeze held. Indexing telemetry owner-side (`/admin/taxonomy` Library knowledge); member Explore has no Admin link / no knowledge-coverage strip. |
| UX | C+ | **B−** | ↑ | Live in primary nav with working Guide; Chat composer disabled copy while opening (“One moment — opening your library.” / `UX-004`); Needs attention on Admin Overview. |
| Visual design | C+ | **B−** | ↑ | Admin density from 1.40.0 redesign is the foothold; brand wordmark + glass login still coherent. Full Button / token adoption still incomplete (E6). |
| Accessibility | C | **C+** | ↑ | Skip link + labeled login fields; Live guide present with station rows. Trailer focus-trap / broader jsx-a11y debt not re-cleared → not B. |
| Ops | C+ | **B** | ↑ | Overview: Needs attention, household backup/export; Newsletters + YIR owner controls; Youth residual closed in code. Invite lifecycle / break-glass / SLOs still open (E5). |

**Overall:** ~**B−** (was C+). Path-to-A is **not** closed — Highs must stay closed in the **running** Hub image before any A claim.

---

## Trust residual spot-checks (1.40.1 image)

| ID | Result |
|----|--------|
| OPS-008 | `YOUTH_MEMORY_REVIEW_TOO_SOON` + `youth_memory_read` present; owner `GET /api/users/{youth}/memory` returns `youth_since` + notes. |
| PRIV-004 | `weekly_newsletter_preview` **removed** from image tree. |
| PERF-009 | `semantic_embeddings` registers `off_loop=True`. |
| PRD-011 | Owner Admin → Library knowledge; member Explore: no Admin nav, no knowledge-coverage strip (Library Pulse remains). |
| GRO-012 | SPA `X-Robots-Tag: noindex, nofollow` + OG meta in `index.html`. **Gap:** `/og-card.png` and `/manifest.webmanifest` **404** — files missing from image `frontend/dist` (meta points at missing asset). |
| UX-004 | Composer `data-testid="composer-input"` disabled with honest opening placeholder. |

---

## Ops check (no prod change)

- Container env on Automat prod: **no** `PROJECTIONIST_TRUST_PROXY_HEADERS` / HSTS-related vars observed.
- Public edge `https://projectionist.automat.vip` is behind **Cloudflare Access** (302/403 to Access login). `Strict-Transport-Security` was **not** observed on the Access challenge response in this check. Treat as **ops follow-up only** — do not flip prod flags without an explicit ask.

---

## Hygiene left parked

- Dependabot minor/patch PRs that were red → left open.
- Vite 8 / React Router 7 majors parked.
- SEC-014 npm audit gate still open if not yet green.

---

## Non-goals confirmed

- Live **PRD-007** freeze held (no new channel types exercised or proposed).
- smartmap `:8790` and prod `:8788` were not stopped for this run.
- QA `:8792` stopped after scoring.

---

## Recommended next theme

With Highs closed enough to leave Security off D and no new High found that blocks the program, default successor workstream: **E6 design-system footholds** and/or **E5 owner operability**, plus a small GRO-012 packaging fix for `og-card.png` / webmanifest in the Hub image.
