# 360 Review: Cross-examination (2026-11-01)

**Run:** `docs/reviews/2026-11-01/` · **Code:** `05274cf` (`v1.38.0`) · **QA surface:** `http://10.10.1.202:8792` (1.38.0, Live on, Anthropic chat on)

**Commit drift:** none. All ten department docs reviewed `05274cf`.

**Method:** Department docs were written independently. Batches 1 through 5 did not read each other's writeups. This pass reads all ten for the first time. For each department it records:

- where another department contradicts it,
- where another department independently reached the same conclusion,
- what the department did not look at that a neighbour did,
- whether its top findings move up or down once the whole picture is visible.

Re-ranking here feeds the executive summary (`30_…`). It does not edit the departments' own scores.

---

## Cross-cutting root causes

Seven root causes explain most of the 140 actionable findings. Each one was found by at least two departments that could not see each other's work.

| # | Root cause | Departments that found it | Findings |
|---|-----------|---------------------------|----------|
| R1 | **Authorization is enforced in more than one place, and the places disagree.** REST, agent tools, confirmation tokens, and the Youth toggle each carry their own idea of who may do what. | Product, Security, Ops, Privacy, UX | PRD-002, SEC-006, SEC-009, SEC-007, OPS-008, PRIV-003, UX-005 |
| R2 | **Public promises are written by hand and drift from the code.** The Privacy page, Help, README, Hub, and CA copy all claim things the code does not do. | Privacy, Growth, Ops, Architecture | PRIV-002, PRIV-005, PRIV-006, GRO-006, GRO-007, OPS-007, OPS-012, ARCH-009 |
| R3 | **"Ready" means "configured", not "working".** Live hides from nav because a Tunarr URL is not saved. The ready check does not notice a dead database. Recovery relies on an env var that silently no-ops. | Product, UX, Performance, Ops, A11Y | PRD-003, UX-002, UX-009, PERF-007, OPS-007, A11Y-001 |
| R4 | **Household evidence is presented as personal evidence.** "You watched", "both turn on a took place", and "plays from a pick" all mix household-level data into individual claims. | Privacy, Product, Growth, UX | PRIV-001, PRIV-009, PRD-001, UX-012, GRO-010 |
| R5 | **The owner has no operating loop.** No scheduled backup, no queue or latency metric, people-waiting queues outside "Needs attention", no rollback. | Performance, Ops, Growth | PERF-001, PERF-002, OPS-006, OPS-009, GRO-018 |
| R6 | **Systems were started but not adopted.** The `Button` primitive has zero call sites. `app.py` still holds 131 handlers. jsx-a11y rules are downgraded to warn. mypy skips release-critical packages. | Visual, Architecture, A11Y, Performance | VIS-001, ARCH-005, ARCH-006, A11Y-007, PERF-005 |
| R7 | **Scope keeps growing faster than one maintainer can keep correct.** Live, gamification, newsletters, Year in Review, and MCP each add surface. | Product, Architecture, Ops | PRD-007, PRD-008, ARCH-007, OPS-012 |

---

## 01 Product (C+)

**Conflicts**
- PRD-007 ("stop expanding Live") looks like it contradicts PRD-003/UX-002 ("show Live in the nav"). It does not. Both can hold: expose what already works, and freeze new Live scope. The executive summary carries both as one decision (BD-1).
- PRD-016 praises the propose → confirm acquisition boundary. Security's SEC-006 shows that a member holding a confirmation token reaches owner Radarr/Sonarr credentials anyway. The boundary is the right *design* but is not *enforced* for every role. PRD-016 should be read as "protect the design, fix the enforcement".

**Reinforcements**
- PRD-002 and SEC-006 are the same defect described from the product and threat sides. Product's framing ("decide who may acquire") is the decision. Security's ("restrict to owners") is the default answer.
- PRD-001 ("honest why" is broken) is reinforced by UX-012 (rationale copy) and by Privacy's PRIV-001. All three are cases of the system asserting a reason it cannot back up.
- PRD-017 (server-verified pick→play attribution) is reinforced by GRO-001. Growth's GRO-010 adds the blind spot Product missed: native-Plex playback never joins back.

**Blind spots**
- Product did not weigh the Privacy page's false promises (PRIV-002). For a household product whose differentiator includes "local-first privacy", that is a product-positioning failure, not only a compliance one.
- Product did not consider owner recovery (OPS-007) as part of the core journey. A locked-out owner is a household with no product.

**Re-ranking**
- PRD-002 moves **up**: it now sits under Big Decision BD-3 and blocks SEC-006.
- PRD-003 stays at the top of its quick wins. Product, UX, and A11Y all touch it, and it is XS effort.
- PRD-022 ("Send to TV") moves **down** to Later. Adding a new acquisition-adjacent action before R1 is fixed widens the surface the household can misuse.

## 02 UX (C+)

**Conflicts**
- UX-003 protects the shared nav builder. Architecture's ARCH-005 wants routes extracted from `app.py`. They do not conflict: one is frontend nav, the other backend routing. No re-ranking needed.

**Reinforcements**
- UX-002 = PRD-003 (same root, `live_channels_ready` tied to a saved Tunarr URL; recon confirmed `live_channels_ready=false` with `live_channels_enabled=true`). A11Y-001 adds that once Live is visible, screen-reader users cannot tell stations apart. Ship the three together.
- UX-005 (bulk Delete in the search toolbar) is reinforced by Product's PRD-014 and sacred cow SC-15. It is a destructive-action-placement problem, not only layout.
- UX-004 (composer disabled without explanation) matches A11Y-009 (disabled state not announced).

**Blind spots**
- UX scored the owner reply time (about 7.7 seconds) as a success without a budget. Performance did not set a chat latency SLO either. Neither department owns "how slow is too slow" for chat.
- UX did not review email surfaces. Growth's GRO-008 and GRO-009 found the invite and lifecycle emails broken. Those are UX for invited members, who see them before the app.

**Re-ranking**
- UX-005 moves **up** to Now alongside R1, because a destructive action reachable from search compounds R1's authorization drift.

## 03 Visual design (C+)

**Conflicts**
- **VIS-003 vs A11Y-010.** Accessibility says token contrast passes AA in both themes. Visual measured the Explore primary Search button at **3.04:1** in Lights Up, plus about 40 hard-coded literals that never adapt. Both are right at different layers. The *tokens* pass. The *usage* does not, because the gold **fill** token is used as a text color. A11Y-010 overstated this as a blanket pass, and the red team corrected it (see `21_…` and the changelog in `04_…`).

**Reinforcements**
- VIS-001 (`Button` primitive with zero call sites, 539 bespoke buttons) matches Architecture's adopt-what-you-started theme (ARCH-005, ARCH-006) and A11Y-007 (lint rules downgraded). All three are R6.
- VIS-004 (type floor, 477 leaf nodes at 11.25–12.19px) reinforces A11Y's text-resize concerns. It is the strongest visual finding for the older, low-vision persona.

**Blind spots**
- Visual did not measure the Live guide. A11Y and UX did, and Live is the newest surface, with its own CSS (`12-live.css`) and `outline:none` (A11Y-004).

**Re-ranking**
- VIS-003 stays in Now (XS fix, score 12).
- VIS-001 moves **down** to Later as an epic. It is XL to migrate 539 buttons. Make new code adopt the primitive (a lint rule) instead of a big-bang migration.

## 04 Accessibility (C)

**Conflicts**
- A11Y-010 vs VIS-003, as above. A11Y accepts the correction.

**Reinforcements**
- A11Y-001 and A11Y-004 overlap with UX-002 and UX-009 on Live.
- A11Y-007 (jsx-a11y rules downgraded to warn) and A11Y-012 (no axe in e2e) explain why the defects above reached a release. Architecture's ARCH-003 praises CI gates in general, but none of them are accessibility gates.

**Blind spots**
- Accessibility was written code-first after its subagent failed to return. Axe was not run in a browser. Findings tagged Likely (A11Y-004, A11Y-009) should be confirmed on `:8792` before anyone schedules engineering time on them.
- Email accessibility (plain-text alternatives, link text) was not examined. Growth found links missing entirely (GRO-008).

**Re-ranking**
- A11Y-001 stays High and ships with UX-002.
- A11Y-012 (axe in e2e) moves **up** to Next. It is the cheapest way to stop R6 from recurring on the accessibility side.

## 05 Growth, content, analytics (C)

**Conflicts**
- **GRO-007 vs PRIV-016.** Growth says to drop the "zero-telemetry" claim. Privacy praises "no telemetry leaves the box". Both are right. 1.38.0 added on-box product events (`chat_turn`, `play_start`), so "zero telemetry" is now false, while "nothing leaves your server" is still true. Positioning should use the second phrasing. That keeps Privacy's strength and fixes Growth's weakness.
- GRO-018 ("Household pulse") wants more on-box measurement. Privacy's PRIV-024 wants a personal-data registry first. Order: registry, then pulse, so every new event is registered before it is shown.

**Reinforcements**
- GRO-010 (native-Plex blind spot) reinforces PRD-017 and limits it: attribution is honest but under-counts.
- GRO-006 and GRO-011 (Hub stub, CA overview) match Ops' OPS-012 (maintainer infrastructure in owner docs). All three are R2.

**Blind spots**
- Growth did not weigh that any new install path (GRO-006, GRO-011) inherits SEC-010's unauthenticated default. Growing installs before BD-2 is decided grows the exposed population.

**Re-ranking**
- GRO-006 stays in Now (XS, score 12).
- GRO-009 (invite copy) stays in Now. The invite flow is the 1.38.0 headline.
- GRO-018 moves **down** to Next, behind PRIV-024.

## 06 Security (D)

**Conflicts**
- Security graded **D** with no Critical and five High. Architecture graded the same code **B-**. Both are defensible: Architecture grades structure, and Security grades exploitability by a household member or LAN peer. The red team examines whether D is calibrated (see `21_…`).

**Reinforcements**
- SEC-006 = PRD-002 (R1). SEC-009 (agent review retrieval not scoped) matches Privacy's PRIV-008 class of cross-member exposure.
- SEC-008 (first-login owner claiming) and SEC-010 (unauthenticated default) both reinforce Ops' OPS-007. Owner identity is weak at the first login and at the last-resort recovery.
- SEC-001 and SEC-003 (perimeter and object scoping) agree with Architecture's ARCH-001 and ARCH-002 that the data plane is sound.

**Blind spots**
- Security did not examine the Youth toggle as a privilege escalation for the *owner* (OPS-008, PRIV-003). The owner can read an adult's private curator memory by flipping a flag. That is an authorization defect even though the actor is trusted.
- Security did not weigh backups (PERF-002). A household with no backup has no recovery from a destructive compromise.

**Re-ranking**
- SEC-006, SEC-007, SEC-008, and SEC-009 are the top four items in the whole review.
- SEC-010 becomes Big Decision BD-2 rather than a ticket. Changing the default deployment mode changes first-run for every new install.

## 07 Privacy and compliance (C)

**Conflicts**
- PRIV-023 ("My data" page) and PRIV-005 (in-app export and delete) are feature builds. PRIV-002 (make the page accurate) can be done today by rewriting the page to match the code. The executive summary orders them: truthful page now (PRIV-002), real features next (PRIV-005, PRIV-006, PRIV-023), with Big Decision BD-5 choosing which promises to keep.

**Reinforcements**
- PRIV-001 is reinforced by PRD-001 and GRO-010 (R4).
- PRIV-006 (purge leaves orphans) is reinforced by Architecture's ARCH-009 (account deletion spans two transactions and leaves a stale file).
- PRIV-003 = OPS-008 (Youth toggle reads adult memory).

**Blind spots**
- Privacy did not consider backups. Owner-downloaded zips contain every member's data and have no retention or encryption story (PERF-002, OPS-009). A "permanently delete" promise needs to say what happens to existing backups.

**Re-ranking**
- PRIV-001 moves to the top of Privacy and into the top five overall. It actively misinforms members today.
- PRIV-024 (data registry plus contract tests) is the structural fix for R2. It stays High but moves to Next because it is M effort.

## 08 Architecture (B-)

**Conflicts**
- Architecture's B- is the highest grade in the run. The red team asks whether it is generous given R1 (`21_…`). Architecture's view is that the authorization *seam* is a structural problem it called out as ARCH-007/ARCH-005 territory, without naming the authorization drift directly.

**Reinforcements**
- ARCH-005 (stop adding to `app.py`) reinforces VIS-001 and A11Y-007 (R6).
- ARCH-009 reinforces PRIV-006.
- ARCH-010 (JSON 404 for unknown SPA routes) matches the recon note that unknown URLs return JSON.

**Blind spots**
- Architecture did not trace authorization as a cross-cutting concern. Four departments found R1, and Architecture is the one best placed to propose the single policy point that would end it.

**Re-ranking**
- Add an implied architecture item under E1: "one authorization policy shared by REST, agent tools, and confirmation tokens." It is recorded in the executive summary as epic E1's structural deliverable rather than a new finding ID.
- ARCH-007 (Live boundary, Rethink) is coupled to BD-1. If Live is frozen, the boundary work is smaller.

## 09 Performance, reliability, cost (C+)

**Conflicts**
- None material. PERF-005 (split the 1,054 kB entry chunk) competes for effort with VIS-001 and ARCH-005, but they touch different layers.

**Reinforcements**
- PERF-002 = OPS-009 (backups). PERF-001 reinforces OPS-006 (owner visibility). PERF-007 reinforces R3.

**Blind spots**
- Performance did not set a chat latency budget (see UX).
- Performance did not weigh LLM cost per household. The QA box runs Anthropic `claude-sonnet-4-6`, and cost is an owner-visible concern in self-hosted AI tools.

**Re-ranking**
- PERF-002 moves **up** to Now. Every department's "permanently delete", "recover", and "roll back" story depends on a backup that exists.

## 10 Operations and support (C+)

**Conflicts**
- OPS-007 says Help tells members to "reset it from the login page". UX did not record the login page as missing a reset control. Ops' evidence is code-level and specific, so it stands.

**Reinforcements**
- OPS-006 reinforces PERF-001 (R5). OPS-008 = PRIV-003. OPS-009 = PERF-002. OPS-012 matches GRO-006 and GRO-007 (R2).

**Blind spots**
- Ops did not consider Security's SEC-008. The first-login owner claim is also a support incident: "someone else became owner of my server".

**Re-ranking**
- OPS-006, OPS-007, and OPS-008 stay in Now. OPS-009 merges with PERF-002 in epic E5.

---

## Duplicates to merge at ticket time

The backlog keeps one row per finding, as the spec requires. When the work is ticketed, merge these pairs into one ticket with both IDs:

| Merge | Reason |
|-------|--------|
| PRD-003 + UX-002 | Same root (`live_channels_ready` gate) |
| PRD-002 + SEC-006 | Same defect (member acquisition) |
| PRIV-003 + OPS-008 | Same loophole (Youth toggle reads memory) |
| PERF-002 + OPS-009 | Same gap (no scheduled backup, no restore) |
| PRIV-006 + ARCH-009 | Same deletion path |
| UX-004 + A11Y-009 | Same disabled composer state |
