# Carry-forward triage: 2026-11-01 review findings vs the media-engine era

Dropped 2026-11-18. The 2026-11-01 360 review (`docs/reviews/2026-11-01/`) produced 140 backlog rows. 74 are referenced in `CHANGELOG.md` or `docs/PRODUCT.md` through 1.40.1, and are treated as shipped (verify on the next rescore). The **66 rows below have no shipped reference**. Each one is triaged against the new era (playback engine, shared sessions, timeline, tracks, native clients; board: [../README.md](../README.md)).

**How this list was made:** the ID of every backlog row was searched for in `CHANGELOG.md` and `docs/PRODUCT.md` on `origin/main` at 1.40.1. "Not mentioned" does not prove "not done". Rows marked **verify** may have shipped under another ID.

Verdicts:
- **Include**: the era depends on it, or it gets cheaper/more valuable inside an era item. Fold it in as a prerequisite or merge.
- **Keep**: still right, independent of the era; stays in its review epic.
- **Supersede**: the era replaces it; close the row with a pointer.

---

## Include (prerequisites or merges)

| Review ID | Title (short) | Why it matters now | Fold into |
|-----------|---------------|--------------------|-----------|
| PERF-011 | Household ceiling on LLM spend | Booth Notes and Class editions are many LLM calls; generation must respect a household budget before TRK ships | Prerequisite of TRK-002 / TRK-004 |
| PRIV-007, PRIV-025 | Youth data policy: LLM routing, memory default | Tracks, “ask about now”, and curator notes reach Youth sessions; routing must exist first | Prerequisite of TRK-004, TML-006 |
| SEC-013 | One SSRF-safe policy for poster fetching | Art-first design depends on a reliable art cache, and TRK-005 public-source fetches need the same egress policy | Prerequisite of TRK-005; art cache work |
| PRIV-026 | “What leaves this server” panel | Public sources (TRK-005) and the push relay (NAT-006) must appear there the day they ship | Ships with TRK-005 / NAT-006 |
| ARCH-005 | Stop adding routes to `app.py` | ENG / SES / TML / TRK add dozens of routes; each goes in its own router module from day one | Rule for every era item |
| ARCH-007 | Boundary around Live | ENG-009 moves Live onto engine streams; build it as the facade ARCH-007 asked for | Merge with ENG-009 |
| ARCH-010 | Serve the SPA for unknown pages | Shared deep links (web ↔ native universal links) need web fallbacks for every title, room, and edition URL | Prerequisite of NAT deep links |
| PERF-014 | Adopt SLOs | Add era SLOs: time to first frame, session event latency (p95 < 500 ms), cue drift (< 300 ms) | Extend with ENG / SES |
| UX-006, PRD-012 | One name for the assistant; one positioning line | “Good to meet you — I'm Curator” still renders on mobile chat; positioning moves to *media intelligence for people who love their collections* | Experience convergence drop |
| UX-007, PRD-009 | One inbox count; consolidate comms | Native badges and “your edition is ready” notifications need one count and one Inbox | Experience convergence drop + TRK-008 |
| PRD-014 | Move owner bulk Delete off shared toolbars | Search is the third primary peer on every client; destructive owner tools belong in Admin → Libraries | Experience convergence drop |
| PRD-015 | Rebalance primary peers | Converge every client on Explore · Live · Chat · Search | Experience convergence drop |
| PRD-006 | Join → home + a 60-second first run | The same first-run applies to iPhone sign-in (NAT-002) | Experience convergence drop |
| VIS-005, VIS-006, VIS-007, VIS-009, VIS-010, VIS-011, VIS-012, VIS-015, VIS-020 | Token completion, status palette, spacing, chips, icons, motion, stylelint | One tokens source of truth generates the web’s CSS variables **and** the native clients’ tokens; finishing the set is cheaper once than twice | Experience convergence drop (design tokens as source) |
| VIS-008 | Keep the app shell on title detail | Reframe: keep navigation reachable, but let the shell go transparent over the hero (cinema density) | Experience convergence drop |
| VIS-021 | Design gallery route with two-theme screenshots | The gallery becomes the visual reference that native clients match | Experience convergence drop |
| VIS-022 | Compact density for Admin | Becomes the **Workbench** density of the shared language (1.40.0 started it) | Experience convergence drop |
| GRO-015 | Plain words for controls; voice for content | Same rule for every client; feeds the voice pass on *why* sentences | Experience convergence drop |
| PRD-005 | Replace the kinship % north star | The era needs an outcome north star, e.g. *evenings that started from a Projectionist pick or track*; requires engine-side attribution | Consider with ENG (attribution through owned playback) |
| PRD-025 | “Who’s watching?” group picks with the youngest viewer’s ceiling | Sessions make this natural: guests joined to a room can tighten the session ceiling | Consider as SES option (see open question) |

## Supersede

| Review ID | Title (short) | Replaced by |
|-----------|---------------|-------------|
| PRD-022 | “Send to TV” on a Plex client | SES-002 / SES-003 rooms and sessions (Projectionist clients as screens). A Plex client as a *screen kind* can be reconsidered later, behind the same session API |
| PRD-024 (in part) | Count picks watched on TV | Plays through the engine are attributed by construction (ENG-003). Only native-Plex plays still need the separate “likely” tier (GRO-010) |

## Keep (independent of the era)

| Epic | IDs |
|------|-----|
| E1 Authorization | PRD-002 (**verify**: may be closed by the SEC-006 fix), PRIV-003 (**verify**: likely closed by OPS-008 in 1.40.1), PRIV-008, SEC-014 |
| E2 Privacy promise | PRIV-010, PRIV-011, PRIV-012, PRIV-013, PRIV-014, PRIV-015 |
| E5 Owner operability | OPS-010, OPS-013, OPS-014, OPS-015, OPS-017, OPS-018, OPS-019 |
| E6 Design / a11y | A11Y-006, VIS-013 (**verify**: 1.40.0 notes “≤1 gold primary per action group”), VIS-014 |
| E7 Codebase | ARCH-011, ARCH-012, ARCH-013, ARCH-014, PERF-013 |
| E8 Growth | GRO-016, GRO-017, GRO-019, GRO-021, GRO-022, GRO-023, GRO-024 |
| E9 | PRD-023 (native request queue, BD-3 option 2) |

## Open question for the person

- **PRD-025 vs “the initiator owns the intent.”** If a Youth member joins an adult’s session as a guest, should the room’s ceiling tighten automatically (group pick logic), or stay the initiator’s with the Youth guest limited to remote + captions (the current SHARED_SESSIONS proposal)?

## Processing notes for the agent

- Close superseded rows in the next rescore ledger with a pointer to the era item.
- Add the “Include” prerequisites to the *Depends on* column of the era items named.
- Do not renumber review IDs; the next review run carries them forward (see the review spec’s carry-forward ledger).
