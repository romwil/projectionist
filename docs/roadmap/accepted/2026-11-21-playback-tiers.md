# Drop: playback tiers — transcode only as much as the file and the hardware need

**From:** Will (via design chat) · **Date:** 2026-11-21 · **Reference server:** 2× Xeon E5-2630 v3 (32 threads), 125 GB RAM, no GPU (Matrox BMC display only), Unraid 7.3.4. Plex already software-transcodes for several users on it · **Items:** re-scopes ENG-006; proposes ENG-011…014 (renumber if taken) · **Owning doc:** `docs/PLAYBACK_ENGINE.md`

## Why

Projectionist will run on everything from a CPU-only NAS to a box with a discrete GPU. The Unraid community launch will bring many households and many kinds of hardware. Real-time video transcoding is the expensive, hardware-dependent part. Most files that can't direct play need something much cheaper. So the planner works down a **stack of tiers**, picks the cheapest one that works for the file, the device and *this server's hardware*, and records why.

## Decision (accepted)

### The stack, cheapest first

| Tier | What happens | Needs |
|------|--------------|-------|
| 1. Direct | Serve the file as it is | Nothing |
| 2. Remux | Change the container only (ENG-003) | Trivial CPU |
| 3. Audio-only transcode | Copy the video; convert the audio (e.g. DTS/TrueHD → AAC or E-AC-3 per device profile) | Modest CPU; every supported server |
| 4. Captions as text | Image subtitles become WebVTT through OCR (ENG-005), so they never force a burn-in | Background job, not real time |
| 5. Source transcode | Ask the media source to transcode (today's Plex path; Jellyfin's transcoder with ENG-010) | The source does the work |
| 6. Own video transcode | ffmpeg: hardware-accelerated when available; software only on CPU-rich servers | Opt-in. Hardware when detected; software only above a detected-CPU threshold, with a low concurrency cap |
| 7. Pre-optimized versions | A background job makes a compatible copy ahead of time; later plays are tier 1 or 2 | Disk space and idle time |

**Planner rules:**
- Always choose the lowest tier that works.
- Tier 6 in software is allowed only when the owner opts in and the server clears a CPU threshold (cores and a benchmark from the startup check). It's capped at a low number of concurrent streams and limited to **1080p H.264 output**. 4K, HEVC/AV1 output and HDR tone-mapping in software are never chosen; those go to tier 5 or a tier-7 copy.
- CPU-rich, GPU-less servers are common in the Unraid community (retired enterprise Xeons), so this path must be good, not an afterthought.
- Record the tier and the reason on every session (ENG-002 already records reasons).
- Burn-in of image subtitles is the last resort. Prefer tier 4; until OCR exists, fall back to tier 5.

### Hardware awareness

- **At startup, detect what this server can do:**
  - CPU core count, architecture (x86-64, arm64), and a short one-time encode benchmark (e.g. seconds to encode a 10 s 1080p H.264 sample) to set the software threshold;
  - Intel Quick Sync / VAAPI (`/dev/dri`);
  - NVIDIA NVENC (with the NVIDIA container runtime);
  - which encoders ffmpeg actually opens. Test-open each encoder; don't trust device files alone.
- **Expose the result:** a `playback_hardware` capability on `/api/features` (fields defined with NAT-003/004) and the planner's input.
- **Concurrency limits** follow the hardware: separate caps for audio transcodes and for video transcodes, defaulting conservatively. The owner can change them.
- **Docs:** `docs/` explains how to pass `/dev/dri` or an NVIDIA GPU through on Unraid (template fields) and plain Docker. No hardware is required to run Projectionist.

## Items

| ID | Item | Done when |
|----|------|-----------|
| **ENG-011** | **Library playability report.** A job runs the planner dry-run across the library for each device profile (web Chrome, web Safari, Apple TV, iPhone/iPad), using the cached ffprobe from ENG-001. The owner sees, under Settings → Playback, what share of titles is direct / remux / audio-only / needs OCR / needs a video transcode. It also lists the top reasons and the specific titles, and says plainly what hardware would change ("a GPU with Quick Sync would let N titles play without Plex"). | The report runs on QA against the real library and matches spot checks of five titles |
| **ENG-012** | **Audio-only transcode tier**: device-profile audio targets, video copied, segments served like remux, concurrency cap | A DTS or TrueHD film plays in Safari and on the Apple TV simulator through the engine with the video untouched |
| **ENG-013** | **Source-transcode tier** formalized: today's Plex fallback becomes a planned tier with a reason, behind the media-source interface so Jellyfin can provide it later | Fallbacks show as `source-transcode` with a reason; no behavior change for members |
| **ENG-006** (re-scoped) | **Own video transcode**: (a) software 1080p H.264 on CPU-rich servers, gated by the benchmark threshold; (b) hardware VAAPI/QSV and NVENC. Opt-in per household, concurrency caps, quality presets per device profile | (a) can be built and tested on the reference server (2× Xeon E5-2630 v3, 32 threads, no GPU). (b) waits for a GPU test box. Both wait until ENG-011 shows enough titles need it |
| **ENG-014** | **Pre-optimized versions**: an owner-triggered or scheduled job makes compatible copies for chosen titles, or "everything the report says needs a video transcode", within a disk budget; the planner prefers them | A title needing video transcode gets a copy, then plays as direct or remux |
| ENG-005 | Image-caption OCR stays as planned; it is the tier-4 answer to burn-in | (unchanged) |

## Order

ENG-004 (WebVTT) → **ENG-011** (report) → **ENG-012** (audio) → **ENG-013** (source tier) → ENG-005 (OCR) → ENG-014 (pre-optimized) → ENG-006 (hardware video, when the report justifies it).

ENG-011 comes early because it's cheap and tells us what the library actually needs. The QA direct-play run happening now is the first sample. Record its remux/fallback table in `docs/PLAYBACK_ENGINE.md` as a baseline.

## Not in scope

Live channel normalization (ENG-009). That may need its own transcode decision, which is noted there.

---
## Processing note (agent, 2026-11-21)
- Created: ENG-011, ENG-012, ENG-013, ENG-014 (accepted, not started)
- Updated: ENG-006 (re-scoped to own video transcode; accepted; waits on ENG-011). ENG-005 stays proposed and is tier 4, unchanged
- Outbox: none (no new client contract in this drop)
- Needs the person: nothing
- Not started: the report, audio tier, source tier, pre-optimized copies, and ENG-006
