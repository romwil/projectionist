# 360 Review: Executive summary and roadmap (2026-11-01)

**Code:** `05274cf` (`v1.38.0`, GitHub `main` after PR #189) · **QA surface:** `http://10.10.1.202:8792` (1.38.0, Live on with 4 channels, Anthropic chat on) · **Commit drift:** none

**Companion files:** cross-examination `20_…`, red team `21_…`, big decisions `31_…`, backlog `2026-11-01_backlog.csv` (140 rows).

This is a review. It does not ship anything, and no release, tag, or rollout happened as part of it.

---

## Leadership briefing

**Overall grade: C+, the same as the 2026-10-28-2 run.** Seven of ten departments improved. The fixes from the last review are real:

- CI now runs the suite and the image (ARCH-003).
- Settings writes are atomic and fail closed (ARCH-001).
- The library query is off the event loop (PERF-004).
- Health no longer touches SQLite (PERF-003).
- The shell is compressed.

The grade did not rise because 1.38.0 made the household real. Invites, members, youth, and Live moved the risk from "does the server work" to "does the server treat each person correctly", and that is where the new findings cluster.

**The one-sentence version:** Projectionist has the right instincts and does not yet enforce them. The curator explains its picks, but some explanations are nonsense (PRD-001). Acquisition is propose → confirm, but members can confirm (SEC-006). The product is private by design, but the Privacy page promises things the code does not do (PRIV-002). Newsletters say "You watched" about someone else's viewing (PRIV-001).

**Threat model for the Security grade (D):**
- No Critical issue was confirmed.
- All five High issues need a household member or a LAN peer.
- Read the D as "not hardened against a hostile household", not "broken on the internet".

**The recommendation is a trust release before any new feature.** It bundles four epics:

- **E1:** one authorization policy.
- **E2:** a Privacy page that tells the truth.
- **E4:** household evidence never phrased as personal.
- **E5:** scheduled backups and a restore drill.

Separately, finish the Live launch (show it in nav and make the guide usable), then freeze Live scope (BD-1).

## Department grades

| Department | Grade | Previous (10-28-2) | Verdict |
|---|---|---|---|
| Product | C+ | B− ↓ | Differentiated, but breadth exceeds what one maintainer keeps correct; the "why" engine is wrong on the first rail |
| UX | C+ | C ↑ | One prompt to one pick works; Live is hidden by a "configured ≠ working" gate |
| Visual design | C+ | C ↑ | Brand is a B+; system adoption (Button primitive unused, small type) is not |
| Accessibility | C | C− ↑ | Token contrast and focus trap are good; the new Live guide is unusable by screen reader |
| Growth, content, analytics | C | C− ↑ | In-app writing is good; Hub, CA, and invite email are what new people see, and they are stale |
| Security | **D** | C+ ↓ | Strong perimeter; five High member/LAN privilege paths (household threat model) |
| Privacy and compliance | C | C− ↑ | No tracking, opt-in defaults; public promises and "You watched" are false |
| Architecture | B− | C+ ↑ | Data plane is sound; `app.py` and Live need boundaries. Red team: misses the authorization drift (RT-3) |
| Performance, reliability, cost | C+ | C− ↑ | Fast on LAN; no queue metric, no latency, no scheduled backup |
| Operations and support | C+ | C+ → | Server health is visible; household queues, recovery, and youth safety are not |

**Findings:** 184 in total. 44 are strengths. 140 are actionable (weaknesses, opportunities, and removes), and every actionable finding is a backlog row.

| Department | Weakness | Opportunity | Strength | High* | Medium* | Low* |
|---|---|---|---|---|---|---|
| Product | 15 | 4 | 6 | 5 | 12 | 2 |
| UX | 10 | 1 | 2 | 2 | 8 | 1 |
| Visual design | 15 | 3 | 4 | 4 | 10 | 4 |
| Accessibility | 9 | 1 | 2 | 1 | 9 | 0 |
| Growth | 15 | 4 | 5 | 6 | 9 | 4 |
| Security | 9 | 2 | 5 | 5 | 4 | 2 |
| Privacy | 15 | 4 | 7 | 7 | 9 | 3 |
| Architecture | 8 | 2 | 4 | 3 | 4 | 3 |
| Performance | 8 | 1 | 4 | 3 | 5 | 1 |
| Operations | 11 | 3 | 5 | 4 | 9 | 1 |
| **Total** | **115** | **25** | **44** | **40** | **79** | **21** |

\*Severity counts cover weaknesses and opportunities only. No department confirmed a Critical.

## Where the departments agree, and where they disagree

**Agree** (found independently by several departments; full list in `20_…`):
- **R1:** Authorization lives in several places that disagree (Product, Security, Ops, Privacy, UX).
- **R2:** Public promises drift from the code (Privacy, Growth, Ops, Architecture).
- **R3:** "Ready" means configured, not working (Product, UX, A11Y, Performance, Ops).
- **R4:** Household evidence is phrased as personal (Privacy, Product, Growth, UX).
- **R5:** The owner has no operating loop: backup, metrics, queues (Performance, Ops, Growth).
- **R6:** Systems are started and not adopted: `Button`, `app.py`, lint rules, mypy (Visual, Architecture, A11Y, Performance).

**Disagree, and how it resolves**
- **Contrast.** A11Y says tokens pass and Visual says the Explore Search button is 3.04:1. Both are right: the tokens pass, the usage does not. The red team corrected A11Y-010.
- **"Zero telemetry."** Growth says drop the claim and Privacy praises no phone-home. 1.38.0 added on-box events, so say "nothing leaves your server".
- **Security D versus Architecture B−.** They grade different things (exploitability versus structure). The red team considers B− generous because Architecture did not name R1.
- **Live.** Product says freeze it, UX and A11Y say fix it. Do both: fix the launch defects, then freeze (BD-1).

## Top 15 priorities

Merged duplicates are listed together; ticket them as one item.

| # | Finding(s) | What | Why now | Effort |
|---|-----------|------|---------|--------|
| 1 | SEC-006 + PRD-002 | Only owners reach Radarr/Sonarr, including through confirmation tokens | A member or youth can queue downloads on owner credentials (BD-3) | S |
| 2 | SEC-007 | Block member-controlled Apprise SSRF | A LAN-pivot primitive from a member account | S |
| 3 | SEC-009 | Scope agent review retrieval to the caller | Cross-member data exposure through chat | S |
| 4 | SEC-008 | End first-login owner claiming | Whoever signs in first owns the server | S |
| 5 | PRIV-001 (+ PRIV-009) | Never say "You watched" about someone else's viewing | Actively misinforms members every week | S |
| 6 | PRIV-002 | Rewrite the Privacy page to match the code | Public promise that is false today (BD-5, step 1) | XS–S |
| 7 | PRD-003 + UX-002 + A11Y-001 | Show Live when stations exist; name channels in the guide | 1.38.0 headline is invisible and not accessible | XS–S |
| 8 | PERF-002 + OPS-009 | Scheduled on-box backup plus one documented restore drill | Every recovery and deletion story depends on it | M |
| 9 | OPS-008 + PRIV-003 | Youth toggle no longer reads adult memory; confirm, notify, and audit | Silent owner read of private memory (BD-4) | S |
| 10 | PRD-001 | Gate "why" sentences on quality; fix the For-you builder | The differentiator says nonsense on the first rail | S |
| 11 | OPS-007 | Make owner/member recovery work and fix Help | A locked-out owner has no product | S |
| 12 | OPS-006 | Put people-waiting queues into "Needs attention" | Requests sit unanswered for months (75+ days on QA) | S |
| 13 | VIS-003 | Stop using the gold fill as text in Lights Up | 3:1 contrast on the primary button; XS | XS |
| 14 | GRO-006 + GRO-007 | Fix the Hub stub; one positioning sentence | 19k-pull page points to a dead repo name | XS |
| 15 | PRIV-006 + ARCH-009 | Make deletion one transaction with no orphans | "Permanently delete" is false (repeat from last run) | M |

## Cut list

Stop doing, or remove:

| Item | Finding |
|------|---------|
| "Chat days in a row" streaks; reward watching and rating instead | PRD-008 |
| Orphaned pages, dead flags, and Tunarr-era settings | PRD-010 |
| Always-on Lobby Theater; make it opt-in | PRD-013 |
| Dead telemetry plumbing (a table that is pruned and never written) | GRO-020 |
| Per-member newsletter preview from full-mode MCP | PRIV-004 |
| CuratorX command names and legacy DB filenames | ARCH-011 |
| New Live scope until the trust release ships | PRD-007 / BD-1 |
| New routes in `projectionist/web/app.py` | ARCH-005 |
| A big-bang 539-button migration; lint new code onto `Button` instead | VIS-001 (red team) |
| "Send to TV" before authorization is unified | PRD-022 (deferred) |

## Strengths to protect

These were found independently and are worth defending in code review:

- **Propose → confirm for every write** (PRD-016) and **the fail-closed youth gate** (PRD-019). Fix the enforcement; keep the design.
- **Explicit fail-closed API perimeter** (SEC-001) and **object-scoped routes**.
- **No tracking, self-hosted browser surface** (PRIV-016), **opt-in communications** (PRIV-018), **own-memory-only prompt injection** (PRIV-019).
- **Server-verified, text-free pick→play attribution** (GRO-001, PRD-017).
- **Atomic settings writes, numbered migrations, foreign keys, a CI gate that runs the suite** (ARCH-001, ARCH-002, ARCH-003).
- **Health off SQLite, library query off the loop** (PERF-003, PERF-004).
- **Server-verified "Needs attention" and the scrubbed Security log** (OPS-001, OPS-002).
- **The Fraunces / DM Sans / amber identity and AA token contrast** (VIS-016, VIS-017, A11Y-010 at token level).

## Epics

| Epic | Goal | Backlog rows | Key findings |
|------|------|-------------|--------------|
| E1 Authorization parity and member boundaries | One policy for REST, agent tools, confirmation tokens, and the Youth toggle | 17 | SEC-006–010, PRD-002, OPS-008, PRIV-003, UX-005 |
| E2 Privacy promise matches the code | Every public claim backed by a contract test | 18 | PRIV-002, PRIV-005, PRIV-006, PRIV-024, ARCH-009, GRO-007, OPS-007 |
| E3 Finish the Live launch | Visible, accessible, then frozen | 7 | PRD-003, UX-002, A11Y-001, A11Y-004, UX-009, ARCH-007, PRD-007 |
| E4 Honest recommendations | No claim the system cannot back up | 6 | PRD-001, PRD-004, UX-012, PRIV-001, PRIV-009, GRO-010 |
| E5 Owner operability, backup, and recovery | The owner can see, back up, restore, and roll back | 17 | PERF-001, PERF-002, PERF-007, OPS-006, OPS-009, GRO-018 |
| E6 Design system and accessibility foundation | Adopt the primitives and gate them in CI | 26 | VIS-001–004, A11Y-002–012 |
| E7 Codebase seams and CI gates | Finish the `app.py` extraction; type-check release packages; split the entry chunk | 13 | ARCH-005, ARCH-006, PERF-005, PERF-008, PERF-009 |
| E8 Acquisition, lifecycle messaging, and measurement | What new people see first is current and consistent | 16 | GRO-006, GRO-008, GRO-009, GRO-011, GRO-012 |
| E9 Navigation, naming, and states | Clean up IA, naming, and empty/loading states | 20 | UX-004, UX-011, PRD-011, PRD-010 |

E1's structural deliverable is a single authorization policy module that REST, agent tools, and confirmation tokens all call. No department filed it as one finding. It comes out of the cross-examination (R1).

## Roadmap

### Now: the trust release

Ship the top 15 above, with one rule: **no new feature work until E1 items 1–4 and PRIV-001 are merged.**

- E1: SEC-006, SEC-007, SEC-008, SEC-009, PRD-002 (BD-3, Option 1), OPS-008, PRIV-003 (BD-4 guardrails), UX-005.
- E2: PRIV-002 copy rewrite (BD-5, step 1), OPS-007, GRO-007.
- E3: PRD-003, UX-002, A11Y-001, A11Y-004.
- E4: PRIV-001, PRIV-009, PRD-001.
- E5: PERF-002 + OPS-009, OPS-006.
- Quick wins: VIS-003, GRO-006, A11Y-002, A11Y-003, A11Y-005, A11Y-008.

**Exit criteria:**
- A member or youth account cannot reach Radarr/Sonarr by any route.
- No member-facing surface says "You" about another person's viewing.
- The Privacy page has no claim without a test or a code path.
- A scheduled backup exists and has been restored once on QA `:8792`.

### Next: make the promises real

- **BD-2:** authenticated mode as the default for new installs (SEC-010).
- **BD-5, step 2:** PRIV-024 registry and contract tests, then PRIV-005 export, PRIV-006 + ARCH-009 deletion, PRIV-023 "My data".
- **BD-4, step 2:** youth LLM routing and memory default (PRIV-007).
- **Visibility:** PERF-001 queue and latency metrics, PERF-007 ready check, then GRO-018 Household pulse on top of the registry.
- **Gates:** A11Y-012 axe in e2e, A11Y-007 jsx-a11y back to error, ARCH-006 mypy on release packages.
- **Growth:** GRO-008 email links and unsubscribe, GRO-009 invite copy, GRO-011 CA card.
- **Code:** ARCH-005 extraction, PERF-005 entry-chunk split.

### Later: grow on a trusted base

- **BD-1 revisit:** whether Live earns new scope.
- **VIS-001:** primitive migration (opportunistic), VIS-004 type scale.
- **GRO-010:** native-Plex "likely" attribution tier, after Red team Q3 is answered.
- **PRD-022:** Send to TV, after E1.
- **Cut list:** the remaining items.

## Questions the review cannot answer

From the red team:

1. How many households run no-login on an untrusted LAN?
2. Do members start in chat or in Explore?
3. What share of plays happen in native Plex?

Each needs either household data or a deliberate on-box event that the data registry (PRIV-024) can describe honestly.
