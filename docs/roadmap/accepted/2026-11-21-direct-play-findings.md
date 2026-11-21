# Drop: direct-play QA findings on 1.42.0 — what to fix before the beta goes wider

**From:** Will (via design chat) · **Date:** 2026-11-21 · **Baseline:** QA run with the library mounted read-only (PR #252). Record the results table in `docs/PLAYBACK_ENGINE.md` as the first playability sample.

## What worked (keep)

- Direct play of MP4 H.264/AAC in Chrome and Safari for 15+ minutes. Far seeks, pause, resume and resume-position all work.
- MKV H.264/AAC remuxes and plays. WebVTT renditions are written for titles with text captions.
- Every case the engine can't serve falls back to Plex and records the reason.

## 1. Engine sessions must only go to clients that can play them (highest priority)

**Seen:**
- With `playback_engine` on, the Apple TV app (current `main`, no APL-020) opened an engine session.
- The preroll played, then the playlist returned **401 twice**.
- The film never started, and nothing fell back to Plex.

**Fix (accepted):**
- **Opt-in by client.** The server hands out an engine session only when the client says it supports one: the session request carries the client's device profile and an engine opt-in.
  - Clients that don't opt in get the library session whatever the household switch says.
  - The `playback_engine` capability means "this server can"; it never means "you must".
- **Find the 401's root cause** before fixing it. Which credential does the engine playlist expect, which does AVPlayer send, and do the header-free session-token URLs (needed for AirPlay and picture-in-picture) work for device credentials? Add a test with a device credential.
- **Fallback covers the start of playback.** If the engine playlist fails before the first frame, the server-side path lets the client retry on the library session. Coordinate with the iOS drop of the same date.

**Done when:** the Apple TV simulator against QA plays *Purgatory* with the switch on and with it off, and the server tests cover the client opt-in.

## 2. The web device profile comes from the browser, not a fixed list

**Seen:**
- HEVC (*Mulholland Drive*) was refused for all web browsers.
- E-AC-3 remuxed for Safari but needed an audio transcode for Chrome.

**Fix:**
- The web player builds its profile from runtime checks (`MediaSource.isTypeSupported` / `MediaCapabilities.decodingInfo`) for HEVC (`hvc1`), AV1, E-AC-3, AC-3 and 10-bit, and sends it with the session request.
- Safari on Apple hardware generally plays HEVC in fMP4 HLS. Chrome's HEVC support depends on the platform's hardware decoder. Let the checks decide rather than assuming either way.
- The planner records which profile answer drove the plan.

**Done when:** *Mulholland Drive* plans `remux` in Safari on a Mac that reports HEVC support, and still falls back where it isn't supported.

## 3. Text captions are ready before Play, not during it (ENG-004 scope)

**Seen:** *Adventures of Zatoichi* (MKV with English SubRip) fell back to Plex because WebVTT wasn't ready within 20 seconds. Extracting a subtitle stream from a large MKV can mean reading most of the file.

**Fix:**
- Extract text subtitle streams to WebVTT ahead of time with the jobs engine. Good triggers:
  - library scan or a new arrival;
  - a title entering Continue Watching or For you;
  - the title page opening.
- Cache the results next to the household subtitle cache.
- At play time, a ready track goes straight into the session. One that isn't ready keeps today's fallback, and the extraction keeps running so the next play is direct.

**Done when:** *Zatoichi* plays through the engine with English captions on a second play, and the playability report (ENG-011) counts "captions pending" separately from "captions need OCR".

## 4. Picture captions

*13 Assassins* fell back as expected. That's ENG-005 (OCR), no change.

## Order

1 → 2 → ENG-004 with §3 → ENG-011 report → ENG-012 audio (the Chrome E-AC-3 case is the first test title).

The beta switch stays off in production until 1 is fixed. With it off, 1.42.0 is fine for web households.

---
## Processing note (agent, 2026-11-21)
- Created: none (changes to existing items)
- Updated: ENG-003 / ENG-007 — `engine_opt_in` is required for a playable engine session. The QA 1.42.0 playlist 401 is written in PLAYBACK_ENGINE.md and fixed on this branch: the path token passes the household gate, and a device-credential test covers the header-free playlist. The 2026-11-21 QA table is the baseline in that doc
- Updated, not started: ENG-007 follow-up (browser runtime profile, findings §2). ENG-004 follow-up (extract text captions ahead of play, findings §3). ENG-005 unchanged (findings §4)
- Outbox: 2026-11-21-engine-opt-in-native.md
- Needs the person: nothing
- Not started: §2, caption extraction, ENG-011
