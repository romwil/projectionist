# Drop: warm start — prepare the film while the preroll plays

**From:** Will (via design chat) · **Date:** 2026-11-22 · **Items:** new ENG item (next free number); pairs with session state (preparing/ready/failed) and the warm-up screen drop of the same date

## Why

Prerolls already play before films. Those 10–60 seconds are free time: the server can wake the disk, probe, extract captions and start the engine, or start the Plex transcode, so the film's first frame is ready the moment the preroll ends. The warm-up screen then becomes the rare case, not the normal one.

## Decisions (accepted)

1. **When Play is pressed and a preroll will play** (the owner has prerolls on, and the title is a film or the member's settings call for one), the server creates the film's session **immediately** and starts preparing it in parallel with the preroll:
   - wake the disk, probe, plan, and extract text captions;
   - **engine plans:** start ffmpeg at the resume position (or 0) and write the first segments;
   - **library/Plex plans:** start Plex's transcode at the resume position right away. This matters most for slow 4K and 10-bit starts on CPU-only servers.
2. **Hand-off:** the client preloads the film's playlist and first segments during the last ~5 s of the preroll and switches with no gap.
   - Apple: an `AVQueuePlayer` with the preroll item then the film item.
   - Web: preload into a second media element or hls.js instance, then cross-fade.
   - If the film isn't ready when the preroll ends, the warm-up screen bridges the gap with the real state's lines.
3. **The first-frame fallback still applies**, but its clock starts at the hand-off. If the engine preparation fails during the preroll, the server switches to the library plan *during the preroll*, so the member never sees it.
4. **Cancel cleanly.** Back during the preroll stops the film's preparation (ffmpeg or the Plex transcode) within a few seconds; no orphaned work. Then it counts toward the concurrency caps (audio encodes, Plex transcodes) like any other session.
5. **Light pre-warming before Play (optional, cheap only):**
   - opening a title page, or resting focus on a Continue Watching item for about 2 s, may wake the disk, probe, and queue caption extraction;
   - **never** start ffmpeg or a Plex transcode speculatively;
   - at most one pre-warm per device at a time, dropped when the member moves on.
6. **Session state reports it:** `preparing` during the preroll, `ready` when the first segments exist. Record how long preparation took and whether the film was ready at hand-off, so we can see how often the warm-up screen was needed.

## Done when

- With prerolls on, a film plays the preroll and starts with no visible wait on web and Apple TV.
- *Marriage Story* on the library path starts at preroll end, or within a few seconds of it, instead of timing out.
- Back during the preroll leaves no ffmpeg or Plex transcode running (checked in Plex's sessions and the process list).
- Session records show `ready_at_handoff` for a QA sample.
- The fixture test covers preroll + film hand-off with a slowed source.

---
## Processing note (agent, 2026-11-22)
- Created: ENG-015
- Updated: board status and sequencing; PLAYBACK_ENGINE.md (item, contract, honest limits); NATIVE_CLIENTS.md (proposed capability name only)
- Outbox: 2026-11-22-ENG-015-apple.md
- Needs the person: nothing. The capability name `preroll_warm_start` is proposed and is not on the manifest.
