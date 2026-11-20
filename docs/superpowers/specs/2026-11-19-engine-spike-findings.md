# Engine remux spike findings (Lane A)

**Date:** 2026-11-19 (client retest 2026-11-20)  
**Branch:** `spike/engine-remux` (throwaway code — **not** merged)  
**Related:** [PLAYBACK_ENGINE.md](../../PLAYBACK_ENGINE.md) · next-steps step 4

## What we remuxed

| Field | Value |
|-------|-------|
| Title | *3 Ninjas* (1992) |
| Plex rating key | `121986` |
| Source | `/data/media/movies/3 Ninjas (1992)/3 Ninjas (1992).mkv` (Automat library) |
| Video | H.264 High, 1920×1080, ~23.98 fps |
| Audio | AC-3 stereo 192 kb/s (English) |
| Embedded text sub | SubRip (not used in the HLS package) |
| Household captions | `DATA_DIR/subtitles/121986/en.srt` → WebVTT |

**Scope:** first **600 s** only (`-t 600`), so the package stayed ~436 MB instead of remuxing the full 4 GB file. Seek / caption behavior inside a complete VOD playlist is what this spike needed.

### Remux command (A/V, `-c copy`)

```bash
ffmpeg -y -ss 0 -t 600 -i "3 Ninjas (1992).mkv" \
  -map 0:v:0 -map 0:a:0 \
  -c copy \
  -f hls -hls_time 6 -hls_playlist_type vod \
  -hls_segment_type fmp4 \
  -hls_fmp4_init_filename init.mp4 \
  -hls_segment_filename "av/seg_%04d.m4s" \
  av/stream.m3u8
```

Household SRT → single WebVTT file + a one-segment VOD subtitle playlist; master playlist wires `TYPE=SUBTITLES` (`GROUP-ID="subs"`). Helper: `scripts/spike-engine-remux.sh` on the spike branch.

**Remux cost:** ~179× realtime on Automat (I/O bound). Segment boundaries followed keyframes (~10 s typical), not the nominal `hls_time 6`.

## How it was served

Temporary routes (env-gated, **not** for main):

| Step | Detail |
|------|--------|
| Gate | `SPIKE_ENGINE_REMUX=1` registers routes; `POST /api/spike/engine-remux/session` uses `require_role("owner")` |
| Media auth | Unguessable path token in `/api/spike/engine-remux/{token}/…` — **no** `Authorization` header on playlist/segments (AVPlayer / Safari friendly) |
| Package | `SPIKE_ENGINE_REMUX_DIR` → pre-built `master.m3u8` + `av/` + `subs/` |
| Local test host | `http://127.0.0.1:8793` with `PROJECTIONIST_SETUP_STATE=active` (fresh `DATA_DIR` otherwise 404s non-setup APIs) |
| Player | `/player` loads native HLS on real Apple WebKit; otherwise same-origin vendored hls.js (CSP blocks inline scripts) |

## Per-client results

| Client | Plays? | Seek without restart? | Captions switchable? | CPU while serving |
|--------|--------|------------------------|----------------------|-------------------|
| **Safari / WebKit** (Playwright WebKit + native HLS) | Yes — 1920×1080, duration 600.066 s | Yes — jumped ~5 s → ~125 s, `readyState=4`, still playing | Yes — `textTracks` English; mode `showing` | Server idle **~0%** CPU; RSS ~160 MB. Parallel segment fetch burst briefly pegged one core; not sustained encode load |
| **Chrome / Chromium** (hls.js 1.5.17) | **No** — `manifestIncompatibleCodecsError` (fatal). Master advertises `ac-3`; desktop Chromium cannot decode it | n/a | n/a (manifest rejected) | Same (file serve only) |
| **Apple TV simulator** (`simctl spawn` + AVPlayer, tvOS 27.2) | Yes — `readyToPlay`, duration 600.066 s | Yes — seek to 120 s, continued at rate 1.0 | Yes — legible group, 1× English option, selectable | Same file-serve profile |

macOS AVPlayer (same framework family) matched the tvOS result: play, seek, English captions.

### Honest limits of this test

- Clip length 10 min, not the full title.
- Desktop Safari UI automation (Apple Events JS) was off; Safari-class behavior is from **Playwright WebKit** + **AVPlayer**, not a hooked Safari.app window.
- Chrome failure is codec (AC-3), not fMP4/HLS packaging. An AAC (or transcoded) audio rendition would be the ENG-006 path.
- QA sidecar (`:8792`) had no media mounts / empty subtitle cache; spike used **prod** library paths + subtitle cache read-only, remuxed into a local package. Prod and smartmap were not stopped.

## Decisions this spike informs (ENG-001…004)

1. **Remux `-c copy` → fMP4 HLS is enough for Apple** (Safari/WebKit + tvOS AVPlayer): VOD playlist seeks without a server restart; household WebVTT in `SUBTITLES` is selectable natively.
2. **Device profiles must drive audio plan before remux.** H.264+AC-3 remux is correct for Apple TV / Safari and **wrong** as the only package for desktop Chrome — planner should choose **audio transcode** (or dual audio) for browser profiles that lack AC-3/E-AC-3.
3. **Session URLs should carry a path token** (no auth header on segments). Matches the proposed ENG-003 contract; AVPlayer on the simulator consumed LAN URLs this way.
4. **Pre-built / cached segments are optional for remux.** Serving static fMP4 segments was ~0% CPU idle; on-the-fly remux was not required for this sample. Keep “on-the-fly first; cache if measured” unless concurrent viewers force I/O contention.
5. **Household subtitle cache → WebVTT works as the default ENG-004 path.** A single VTT + short VOD subtitle playlist was enough for WebKit/AVPlayer; segmented VTT can come later if players demand it.
6. **ENG-001 path mapping remains the blocker for real sessions** — the spike hard-coded a known file + cache path. Planner dry-run needs mapped paths + cached ffprobe.

## Open decisions updates

Recorded in [PLAYBACK_ENGINE.md § Open decisions](../../PLAYBACK_ENGINE.md#open-decisions).

## Spike code disposition

Left on `spike/engine-remux` only (`spike_engine_remux_routes.py`, env registration, `scripts/spike-engine-remux.sh`). **Do not merge** into `main`.
