# 360 Review: Big decisions (2026-11-01)

These are decisions that tickets cannot settle. Each one changes behavior for every household or sets a policy the backlog depends on. Format: ADR-style. Rows in `2026-11-01_backlog.csv` with `DecisionRequired=yes` are blocked on one of these.

**Status of all five:** Proposed. The maintainer decides; this review only recommends.

---

## BD-1: What is Live's place in the product?

**Context.** Live (channels, guide, player, scheduler) shipped broadly in 1.38.0. It works on QA, where 4 channels are on and 3 have shows, but it is hidden from navigation (PRD-003, UX-002). Its guide is not screen-reader usable (A11Y-001). Its focus rings are suppressed (A11Y-004). It has no package boundary (ARCH-007). Product warns that its scope is outrunning one maintainer (PRD-007).

**Options**
1. **Invest.** Fix the launch defects and keep adding Live features (schedules, more channel types).
2. **Freeze.** Fix the launch defects (nav, guide semantics, focus), then accept no new Live scope until E1, E2, and E4 ship.
3. **Lab.** Put Live behind an owner-enabled "Labs" switch, off by default, until the core curator is trustworthy.

**Recommendation: Option 2, Freeze.** The work already exists and works. Hiding it again (Option 3) wastes the 1.38.0 launch. Growing it (Option 1) competes with the trust release for the same maintainer.

**Consequences.** PRD-003, UX-002, A11Y-001, and A11Y-004 ship Now. ARCH-007 shrinks to a thin facade. PRD-007 becomes the written scope freeze.

**Blocks:** PRD-007, ARCH-007.

---

## BD-2: Should authenticated mode be the default for new installs?

**Context.** New installs start in single-owner mode with no login. That is convenient on a trusted LAN. It is unsafe on a shared or hostile one, and it combines with first-login owner claiming (SEC-008) and the unauthenticated default (SEC-010).

**Options**
1. **Keep the default** and add a louder first-run warning.
2. **Authenticated by default**, with single-owner mode as an explicit, documented opt-out.
3. **Bind-based default.** No-login only when bound to localhost; authenticated otherwise.

**Recommendation: Option 2.** It closes SEC-008 and SEC-010 together, and the first-run cost is one Plex sign-in. Option 3 is clever, but Docker networking makes "localhost" ambiguous inside containers.

**Consequences.** First-run docs, CA template, and Hub copy change (GRO-006, GRO-011). Existing installs keep their current mode, and the upgrade shows a banner.

**Open question:** how many households run no-login on untrusted LANs? (Red team Q1.) There is no data, and the recommendation stands without it.

**Blocks:** SEC-010.

---

## BD-3: Who may acquire titles?

**Context.** Members and youth can self-confirm acquisitions that reach the owner's Radarr and Sonarr credentials (PRD-002, SEC-006). The propose → confirm design is a protected strength (PRD-016), but the *confirmer* is not checked against role.

**Options**
1. **Owner-only.** Members propose; only the owner confirms.
2. **Owner plus allow-listed members.** A per-member "may request downloads" flag, with youth always excluded.
3. **Delegate to Seerr/Overseerr.** Members request there; Projectionist never calls Radarr/Sonarr on a member's behalf.

**Recommendation: Option 1 now, Option 2 next.** Option 1 is a small change that closes SEC-006 today. Option 2 restores convenience for trusted adults, with an audit entry for each confirm. Option 3 is the right answer for households that already run Seerr and can be documented as such.

**Consequences.** Members see "Ask the owner" instead of "Confirm". Youth never see an acquisition confirm. Ops gains a "pending requests" queue that should land in "Needs attention" (OPS-006).

**Blocks:** PRD-002, SEC-006.

---

## BD-4: What is the data policy for youth accounts, and what may the owner see?

**Context.** Youth chats go to the same LLM provider as adults (PRIV-007). An owner can toggle Youth mode on an adult, read that adult's private curator memory, and toggle it off without any record (OPS-008, PRIV-003).

**Options**
1. **Policy by documentation.** State what the owner can see; change nothing.
2. **Guardrails.** Youth memory is off by default. Youth LLM routing is configurable (local model or none). Toggling Youth mode on an adult requires confirmation, notifies the member, and writes an audit entry. The Youth toggle does not grant memory access.
3. **Separation.** Youth profiles are a separate account type that cannot be toggled from adult accounts at all.

**Recommendation: Option 2.** It keeps the household model intact, closes the loophole, and gives the owner a real policy lever. Option 3 is cleaner but forces a migration on every existing youth account.

**Consequences.** New owner settings for youth LLM routing and memory. An audit log entry type. Privacy page copy changes (ties to BD-5).

**Blocks:** PRIV-007, OPS-008, PRIV-003.

---

## BD-5: Which privacy promises does Projectionist keep?

**Context.** The public Privacy page promises a full data download, permanent deletion with nothing left behind, and invites that are never emailed. None of these are true at `05274cf` (PRIV-002, PRIV-005, PRIV-006). The structural cause is that the page is written by hand and is not tested against the code (R2 in the cross-examination).

**Options**
1. **Shrink the promise.** Rewrite the page to describe exactly what the code does today.
2. **Keep the promise.** Build in-app export, real purge (including orphans and backups), and a "My data" page (PRIV-005, PRIV-006, PRIV-023).
3. **Both, in order.** Shrink now, then grow each promise back only when a contract test proves it (PRIV-024).

**Recommendation: Option 3.** A truthful page costs a day. Each restored promise lands with the test that keeps it true.

**Consequences.** PRIV-002 ships Now as a copy change. PRIV-005, PRIV-006, PRIV-023, and PRIV-024 ship Next. "Permanently delete" must define what happens to existing backups (ties to PERF-002 and OPS-009).

**Blocks:** PRIV-002, PRIV-005, PRIV-006, PRIV-023.
