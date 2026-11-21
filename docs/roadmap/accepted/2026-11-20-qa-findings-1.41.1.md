# Drop: QA findings on 1.41.1 — a database-file trap and the Safari stall

**From:** Will (via design chat) · **Date:** 2026-11-20 · **Type:** bugs, highest priority before the next production rollout

## 1. An empty `projectionist.db` hides the real database (fix before any prod rollout)

**Seen on QA:** a 0-byte, root-owned `projectionist.db` from earlier today sat next to the real 183 MB `curatorx.db`. The server prefers `projectionist.db` whenever that file *exists*. It opened the empty file, couldn't write to it, and crash-looped. Removing the empty file fixed it.

**Fix (accepted):**
- When choosing the database file, ignore a candidate that is 0 bytes or isn't a valid SQLite file. Use the established database and log one warning naming the file that was skipped. Never delete or overwrite anything automatically.
- If both files are real, non-empty databases, refuse to start with a plain message saying which two files conflict. Don't guess.
- Find what created the empty root-owned file. Likely candidates: a container start, a test, or a script `touch` under root. Fix it at the source so nothing creates an empty database file before migration runs.
- Add a test for each case: empty preferred file, invalid preferred file, two real files.

**Done when:** QA starts on a data dir that holds an empty `projectionist.db` next to `curatorx.db`, and the test suite covers all three cases. Add a line to `docs/RELEASE.md`'s pre-rollout checklist: check the production data dir for a stray empty database file.

## 2. Safari still stops after one burst (Plex path)

**Seen on QA 1.41.1:**
- The master playlist now advertises `BANDWIDTH=3410779` (the file's average bitrate + 25%).
- Safari fetched `00000.ts` to `00009.ts` and then stopped; playback ends after that burst.
- Several segments run at about 4.7–5.1 Mbps, which is still above what's advertised.

**Notes:**
- In HLS, `BANDWIDTH` is meant to be the *peak* segment bitrate and `AVERAGE-BANDWIDTH` the average. Our `BANDWIDTH` is still below the peak.
- The bigger question is what happens when Safari's buffer drains. Ten segments is roughly Safari's normal read-ahead, so the stall is probably the *next* request failing, not Safari choosing to stop.

**Investigate before changing anything (systematic debugging):**
1. Reproduce on QA in Safari and record the network log through the moment playback stops.
2. Find the first segment request after the burst and record its status, timing and body. Compare it with the same moment in Chrome (hls.js), which plays.
3. Check whether the Plex transcode session is still alive at that point. Things to look at: session timeouts or missing pings while Safari is idle, the proxy's upstream timeout, and segments that aren't transcoded yet.
4. Also try the same title in Safari on production 1.40.1, so we know whether 1.41.1 is worse, the same, or better.

**Then fix:**
- Set `BANDWIDTH` from the measured peak segment bitrate, plus a margin, and keep `AVERAGE-BANDWIDTH` as the average.
- Fix whatever stops the stream after the burst, with a regression test where possible.

**Done when:** a feature film plays in Safari on QA for 15 minutes with seeking, in a fresh session.

This is the Plex path, which the web keeps until ENG-007 is switched on. It still has to work.

---
## Processing note (agent, 2026-11-20)
- No new item IDs. Both findings are defects, recorded on the board and in the owning docs. They are not feature items.
- Updated: [DATA_MODEL.md](../../DATA_MODEL.md#which-database-file-opens) and [FAQ.md](../../FAQ.md#where-is-my-data-stored) for the empty-database trap. [PLAYBACK_ENGINE.md](../../PLAYBACK_ENGINE.md#known-defect-safari-stops-after-one-burst-qa-1411) for the Safari stall. Investigate that stall before any further playlist change.
- Not done here: the database-file fix, the Safari fix, and the pre-rollout line in `docs/RELEASE.md`. The fix lane adds that checklist line when it lands the database fix.
- Needs the person: nothing to record. Production stays on 1.40.1 until the database-file fix lands, unless the person chooses otherwise. The Safari comparison with production 1.40.1 is part of the investigation, not a rollout decision.
