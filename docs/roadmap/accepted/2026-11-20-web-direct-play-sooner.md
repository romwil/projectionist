# Drop: web direct play sooner — ENG-007 right after ENG-003, behind a setting

**From:** Will (via design chat) · **Date:** 2026-11-20 · **Items:** ENG-007 (re-sequenced), ENG-003, ENG-004

## Decision (accepted)

The web gets direct play as soon as the engine can serve it. This doesn't wait for the rest of the ENG series.

1. **Order in the engine lane:** ENG-001 → ENG-002 → ENG-003 → **ENG-007** → ENG-004 → the rest. This replaces "the web stays on the Plex path until ENG-007 comes up in sequence". Apple clients still adopt ENG-003 first (APL-020/021); the web follows straight after, not at the end.
2. **ENG-007 ships behind a per-household setting, off by default.**
   - The owner turns on *Play through Projectionist (beta)* in Settings → Playback. The server exposes it as a capability, and the web player picks the engine session when it's on.
   - Turning it off returns everyone to the Plex path at the next play. No restart.
3. **Fall back, never fail.**
   - Until ENG-004 lands, a title whose chosen caption track (or the member's default subtitle language) needs captions plays on the Plex path, so nobody loses subtitles. Text-subtitle tracks that already convert to WebVTT may use the engine once ENG-004 ships.
   - If the engine's plan says it can't remux (codec or container outside the device profile), use the Plex path.
   - Record the reason with the session, the same way the planner records any other plan.
4. **Fullscreen and controls stay ours.** The web player keeps its own chrome in fullscreen (the earlier decision that the web owns playback); only the source changes.
5. **Rollout:** QA `:8792` first, with the switch on for the owner account only. The person decides when a release carries it and when production turns it on. Merge is not release.

## Done when

- **With the setting on**, a library film starts, seeks, resumes and writes progress on the web through an engine session, in Chrome and Safari on QA.
- **With it off**, nothing changes.
- **A title with captions on** falls back to the Plex path and says so in the session record.
- **The board** shows the new order, and the decision is in the Decisions table.

## Not in scope

ENG-006 transcodes, ENG-008 scrub thumbnails, and Live on the engine (ENG-009).

---
## Processing note (agent, 2026-11-20)
- Updated: ENG-007 accepted and re-sequenced to immediately after ENG-003, behind an off-by-default household setting. Captions stay on the Plex path until ENG-004.
- Outbox: none (the web player is in this repo)
- Needs the person: nothing. Not started. A release that carries it is a separate ask.
