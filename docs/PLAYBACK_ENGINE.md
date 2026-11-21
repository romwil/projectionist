# Playback engine

How Projectionist plays a title from your library: one stream engine, owned by Projectionist, shared by every client — the web app, native apps, and anything that speaks the API. Plex is the first **media source**, not the player.

**Status:** ENG-001 and ENG-002 are in the tree. A title can be mapped and probed, and `GET /api/playback/plan` records whether the next step would be direct play, an fMP4 remux, an audio transcode, a full transcode, or the Plex path. Playback still uses the Plex universal transcode described in [Today](#today-the-plex-transcode-path) until ENG-003 serves a session. Item IDs (`ENG-…`) are tracked in [docs/roadmap/](roadmap/README.md).
**Audience:** Developers / contributors, owners for the honest limits.
**Related:** [SHARED_SESSIONS.md](SHARED_SESSIONS.md) · [TIMELINE.md](TIMELINE.md) · [TRACKS.md](TRACKS.md) · [NATIVE_CLIENTS.md](NATIVE_CLIENTS.md) · [ARCHITECTURE.md](ARCHITECTURE.md)

Jump to: [Why](#why-own-the-stream) · [Today](#today-the-plex-transcode-path) · [Target](#the-target-engine) · [Stream plans](#stream-plans) · [Captions](#captions) · [Devices](#device-profiles) · [Sources](#media-sources) · [Limits](#honest-limits) · [Items](#roadmap-items) · [Open decisions](#open-decisions)

---

## Why own the stream

Every playback pain the web player has fought traces to one root: the stream belongs to Plex’s transcoder, and Projectionist draws around it.

| Symptom today | Root cause |
|---------------|------------|
| Captions are a DOM overlay; image captions (PGS / VobSub) fall back to **burn-in**, which restarts the transcode and drops timing controls | Captions are not tracks in the stream |
| iPhone Safari fullscreen loses captions and custom controls | `webkitEnterFullscreen()` hands the `<video>` to the system player, which cannot see the overlay |
| Seeks feel heavy | `seek_playback` usually restarts the Plex transcode at the new offset |
| Hold-to-2× is unreliable on iPad Safari | Live-like Plex HLS playlists; the element ignores `playbackRate` |
| Plex is required to play anything | The only stream path is `/video/:/transcode/universal` |

When Projectionist produces the HLS itself — caption tracks inside the playlist, a seekable VOD playlist, video copied rather than re-encoded where the device allows — those symptoms disappear on every client at once, and Plex becomes optional. Projectionist already knows every file path and its streams (library sync, `episode_investigate/ffmpeg.py`), and the container already ships `ffmpeg` + `ffprobe` (see `Dockerfile`).

---

## Today: the Plex transcode path

The shipped path, for reference (`projectionist/library/playback.py`):

1. `POST /api/library/playback/start` opens a Plex universal session: `protocol=hls`, `directPlay=0`, `directStream=1`, `directStreamAudio=1`, `copyts=1`, `subtitles=none` (or `burn` with `advancedSubtitles=burn` for the last-resort image-caption path).
2. Projectionist rewrites the playlist onto `/api/library/playback/{session_id}/…`, so the Plex token never reaches a client.
3. The web player plays it with **hls.js** (`TheaterPlayer.tsx`, `LivePlayer.tsx`); captions come from `/api/library/items/{key}/subtitles/{id}/file` (WebVTT) and are drawn as an overlay (`lib/subtitleCues.ts`), with the element’s own text tracks muted.

This path stays as the **Plex fallback plan** (below) until the engine covers every case it does.

### Known defect: Safari stops after one burst (QA 1.41.1)

Seen on QA 1.41.1, on this Plex path, which the web keeps until ENG-007 is switched on. The master playlist advertised `BANDWIDTH=3410779` (the file’s average bitrate plus 25%). Safari fetched `00000.ts` through `00009.ts` and then stopped. Several segments still run at about 4.7–5.1 Mbps, above that advertisement. In HLS, `BANDWIDTH` is the peak segment bitrate and `AVERAGE-BANDWIDTH` is the average, so the advertised `BANDWIDTH` is still below the peak.

Ten segments is about a normal Safari read-ahead. The stall is likely the *next* request failing, not Safari deciding to stop. **Investigate before changing the playlist:**

1. Reproduce on QA in Safari and keep the network log through the moment playback stops.
2. Find the first segment request after the burst. Record its status, timing, and body. Compare that moment with Chrome (hls.js), which plays through.
3. Check whether the Plex transcode session is still alive then. Look at session timeouts or missing pings while Safari is idle, the proxy’s upstream timeout, and segments that are not transcoded yet.
4. Play the same title in Safari on production 1.40.1, so the comparison says whether 1.41.1 is worse, the same, or better.

**Then, after that cause is written down:** set `BANDWIDTH` from the measured peak segment bitrate plus a margin, keep `AVERAGE-BANDWIDTH` as the average, and fix whatever stops the stream after the burst. Add a regression test where one can be written. **Done when:** a feature film plays in Safari on QA for 15 minutes, with seeking, in a fresh session.

Not started. This record does not change the playlist.

---

## The target engine

```
             ┌────────────────────────────────────────────────┐
 client ───► │ POST /api/playback/sessions                     │
 (+ device   │   title, start offset, device profile           │
  profile)   └───────────────┬────────────────────────────────┘
                             ▼
                 ┌───────────────────────┐
                 │ Planner               │  probe (ffprobe, cached per file)
                 │  source × profile ⇒   │  + device profile ⇒ stream plan
                 │  stream plan          │
                 └──────────┬────────────┘
                            ▼
   ┌──────────────┬─────────────────┬───────────────────┬────────────────┐
   │ direct       │ remux           │ audio transcode   │ full transcode │
   │ (file as-is) │ (copy → fMP4    │ (copy video,      │ (last resort,  │
   │              │  HLS)           │  encode audio)    │  HW if present)│
   └──────────────┴─────────────────┴───────────────────┴────────────────┘
                            ▼
      /api/playback/sessions/{id}/master.m3u8
        ├─ video rendition(s)
        ├─ audio renditions (languages, commentary)
        └─ SUBTITLES group: WebVTT renditions (text + OCR’d image tracks)
```

Principles:

- **Copy before you encode.** Most libraries are H.264 / HEVC with AAC / AC-3 / E-AC-3. Repackaging into fragmented-MP4 HLS (`ffmpeg -c copy`) costs a little I/O and almost no CPU, so a homelab box can serve several rooms at once.
- **A real VOD playlist.** Segments are planned from the file’s keyframes up front, so the playlist covers the whole title. Seeking is the client’s job inside a complete playlist, not a server restart.
- **Captions are tracks.** Every usable caption is a WebVTT rendition in the master playlist’s `SUBTITLES` group. Players switch them natively; the system player keeps them in fullscreen and picture-in-picture.
- **The token boundary holds.** Clients only ever see `/api/playback/sessions/{id}/…`. No file paths, Plex tokens, or source URLs cross the API — the same rule `library_privacy.py` enforces for browse.
- **Session URLs work without headers.** Playlist and segment URLs carry a short-lived, unguessable session token in the path, scoped to one session. Starting a session needs the member’s credential; fetching its segments does not need an `Authorization` header — because AirPlay receivers, picture-in-picture, and some system players cannot send one.
- **Source-agnostic.** The planner asks a **media source** for a readable file and its streams. Plex is one source; a local path map is another; Jellyfin can be a third.

---

## Stream plans

The planner picks the cheapest plan the device can play, in this order:

| Plan | When | Cost | Notes |
|------|------|------|-------|
| **Direct** | Container + codecs already playable (e.g. MP4/H.264/AAC on Safari) | ~0 | Byte-range file serving behind the session URL. Captions still ship as WebVTT sidecar tracks |
| **Remux** | Codecs playable, container is not (e.g. MKV with HEVC + E-AC-3 on Apple TV) | Low (I/O) | `-c copy` into fMP4 HLS. The common case for Apple clients |
| **Audio transcode** | Video playable, audio is not (e.g. DTS / TrueHD on a browser) | Low–moderate | Copy video, encode AAC (and keep E-AC-3 where supported) |
| **Full transcode** | Video codec unsupported (e.g. HEVC on desktop Chrome without HEVC decode, AV1 on old devices) | High | Uses hardware encode (VAAPI / QSV / NVENC / VideoToolbox) when the owner enables it; otherwise CPU with a conservative ladder |
| **Plex fallback** | The engine cannot read the file (no path mapping) or the owner turned the engine off | Plex’s | Today’s path, unchanged |

Each plan is recorded on the session (`plan`, `reason`) so Admin and the client can say *why* a title is transcoding — honest provenance applied to playback.

**Example (owner):** inspect what the engine would do for a title on an Apple TV without starting playback.

```bash
# Proposed endpoint (ENG-002) — dry-run plan for a device profile
curl -s -H "Authorization: Bearer YOUR_DEVICE_CREDENTIAL" \
  "http://your-host:8788/api/playback/plan?rating_key=12345&profile=apple-tv-4k-3" \
  | python3 -m json.tool
# → {"plan": "remux", "reason": "MKV container; HEVC Main10 + E-AC-3 playable on profile",
#    "captions": [{"id": "cached-en", "kind": "text", "lang": "en"},
#                 {"id": "s3", "kind": "image-ocr", "lang": "fr", "ready": false}]}
```

---

## Captions

One caption model for every client:

1. **Text tracks** (SRT, ASS/SSA, mov_text, WebVTT) are converted to WebVTT and segmented into the playlist’s `SUBTITLES` group. ASS styling is flattened to plain cues with positioning where WebVTT can express it.
2. **The household cache comes first.** `DATA_DIR/subtitles/{rating_key}/{language}.srt` (from `library/subtitle_cache.py`, filled by the idle *subtitle enrichment* task) is always offered as the default household-language track, so captions never wait on a download.
3. **Image tracks** (PGS / VobSub / DVB) are converted to text once by an **OCR job** (jobs engine, off the request loop), cached beside the household file, and then behave like any text track. Until the job finishes, the track is listed with `ready: false` and the client offers the honest line: *“These captions are being prepared.”* Burn-in remains a last resort for a viewer who needs that track immediately.
4. **Timing offset** is a per-viewer client setting (the web’s existing delay control). The server never rewrites cue times per person.

Why it matters: captions you can switch in the system player, in fullscreen, in picture-in-picture, on a phone in your hand ([SHARED_SESSIONS.md](SHARED_SESSIONS.md#handheld-captions)), and as a time-coded text source for the curator ([TIMELINE.md](TIMELINE.md)).

---

## Device profiles

A client declares what it can decode; the planner never guesses from a user-agent string.

```jsonc
// Sent with POST /api/playback/sessions (ENG-003)
{
  "profile": {
    "id": "apple-tv-4k-3",           // stable name, or "custom"
    "containers": ["mp4", "hls-fmp4", "hls-ts"],
    "video": [{"codec": "hevc", "max_level": "5.1", "hdr": ["hdr10", "dolby-vision-8.1"]},
              {"codec": "h264", "max_level": "5.2"}],
    "audio": ["aac", "ac3", "eac3", "alac", "flac"],
    "max_bitrate_kbps": null,        // null = LAN, no cap
    "captions": ["webvtt"]
  }
}
```

- Native Apple clients send an accurate profile from `AVURLAsset.isPlayableExtendedMIMEType` / `AVPlayer.eligibleForHDRPlayback` probes.
- The web app sends a profile built from `MediaSource.isTypeSupported` / `canPlayType`.
- Profiles are capped by a **network hint** (`lan` / `remote` + measured throughput) so a remote phone gets a sensible bitrate ladder.

---

## Media sources

The engine reads files through a small adapter interface. Every adapter answers the same three questions:

| Question | Plex source (first) | Path-map source | Jellyfin source (future) |
|----------|--------------------|------------------|--------------------------|
| Where is the file for this title? | Plex part path → owner’s container path mapping | Library sync path | Jellyfin item path |
| What streams does it have? | `ffprobe` (cached per file + mtime) | same | same |
| What is the identity? | `rating_key` ↔ TMDB / IMDB | TMDB / IMDB from sync | Jellyfin id ↔ TMDB / IMDB |

Owners map Plex’s paths to the container’s mounts once. The longest prefix wins, and a prefix only matches a directory boundary (`/data/media` does not claim `/data/media-extra`). A file Plex already names with a path this container can read needs no mapping. The media intelligence stays keyed on TMDB / IMDB identity, so a future source does not fork the knowledge graph.

`GET /api/playback/media/{rating_key}` tells a signed-in member whether the engine can read that title and which streams `ffprobe` found. The response has codecs, duration, and TMDB / IMDB identity. It never includes a file path, a Plex token, or a source URL.

```bash
# Owner: map Plex's movie folder onto the container mount.
# Saving mappings is owner-only.
curl -s -X PUT -H "Authorization: Bearer YOUR_OWNER_CREDENTIAL" \
  -H "Content-Type: application/json" \
  -d '{"mappings":[{"plex_prefix":"/data/media/movies","container_prefix":"/movies"}]}' \
  "http://your-host:8788/api/playback/path-mappings"
```

Probes are cached under the data directory by file path, size, and modification time. Replacing the file probes it again. A failed probe does not invent streams.

---

## The web player adopts the engine

The web app benefits as much as any native client:

- **Desktop browsers and iPad Safari** keep element fullscreen, so Projectionist’s own controls, hold-to-2×, caption styling, and curator overlays ([TRACKS.md](TRACKS.md)) stay on screen in fullscreen.
- **iPhone Safari** still hands fullscreen to the system player (an Apple rule). The difference: the system player now has real caption tracks and a VOD playlist, so fullscreen stops being a downgrade. Projectionist overlays do not show there; the native iPhone app is the premium path.
- `lib/subtitleCues.ts` overlay drawing becomes the **styling layer** on top of native text tracks rather than the only caption path.

---

## Honest limits

- **Browsers decode less than Apple devices.** Desktop Chrome and Firefox commonly lack HEVC and AC-3 / E-AC-3 / DTS; those titles will audio-transcode or full-transcode on the web.
- **Full transcodes are expensive.** Without hardware encode, a 4K HEVC → H.264 transcode can saturate a homelab CPU. The planner limits concurrent full transcodes (owner setting) and says so: *“This title needs a full transcode; another room is already using it.”*
- **Dolby Vision profile 7** (dual-layer UHD rips) cannot be passed through to Apple devices as-is; the plan falls back to HDR10 base layer or transcode, and says which.
- **OCR is not perfect.** Image-caption OCR can misread italics and stylized fonts. OCR’d tracks are labeled as such in the caption menu.
- **The engine needs file access.** If Projectionist cannot read the media (no mount, no mapping), the Plex fallback plan remains the path.
- **Live Channels** keep their scope freeze (PRD-007): the engine replaces the *stream* under existing stations; it adds no channel types.

---

## Roadmap items

| ID | Item | Depends on |
|----|------|------------|
| ENG-001 | Media source interface + Plex path mapping + cached `ffprobe` | — |
| ENG-002 | Planner (`direct` / `remux` / `audio` / `full` / `plex-fallback`) with recorded reason; dry-run `GET /api/playback/plan` | ENG-001 |
| ENG-003 | Session API `POST /api/playback/sessions` with device profiles; VOD fMP4 HLS remux; session-scoped segment URLs. *Proposed:* attribution for “evenings that started from a Projectionist pick” (PRD-005 north star) rides owned playback | ENG-002 |
| ENG-004 | WebVTT caption renditions in the master playlist (household cache first) | ENG-003 |
| ENG-005 | Image-caption OCR job (jobs engine, cached, labeled) | ENG-004 |
| ENG-006 | Audio + full transcode plans; hardware encode opt-in; concurrency limits | ENG-003 |
| ENG-007 | Web player adoption, immediately after ENG-003, behind a per-household setting that is off by default (*Play through Projectionist*). The web keeps its own fullscreen chrome. Captions fall back to the Plex path until ENG-004. A plan the engine cannot remux falls back to Plex and records the reason. Turning the setting off returns the next play to the Plex path | ENG-003 |
| ENG-008 | Scrub thumbnails (trickplay image sprites / I-frame playlist) | ENG-003 |
| ENG-009 | Live Channels on engine sessions (same stations, new stream). Build as the Live facade ARCH-007 asked for; PRD-007 freeze still holds (no new channel types) | ENG-003; ARCH-007 |
| ENG-010 | Jellyfin media source | ENG-001 |

## Open decisions

- **Client order (decided 2026-11-20, re-sequenced the same day):** Apple clients adopt ENG-003 first. The web follows immediately as ENG-007, behind a household setting that is off by default, not after the rest of the engine series. Until that setting is on, the web stays on the Plex path.
- **Path naming:** keep `/api/library/playback/*` and switch its backend, or introduce `/api/playback/sessions/*` and deprecate the old routes after ENG-007. *Proposed:* new namespace, old routes stay as the Plex fallback until parity. **Spike (2026-11-19):** path-token session URLs under a new namespace worked for Safari/WebKit and tvOS `AVPlayer` without `Authorization` headers — keeps the proposed ENG-003 shape.
- **Segment cache:** on-the-fly remux per session vs. a short-lived on-disk segment cache under `DATA_DIR` shared by concurrent viewers. *Proposed:* on-the-fly first; cache only if measurements demand it. **Spike:** serving a pre-built `-c copy` fMP4 package was ~0% CPU idle; no evidence yet that remux needs a shared disk cache for single-viewer Apple playback.
- **HDR on the web:** whether to tone-map or refuse HDR → SDR on browsers without HDR support.
- **Browser audio vs remux (ENG-002 / ENG-006):** *3 Ninjas* H.264+AC-3 remux played on Apple clients and was **rejected** by desktop Chromium/hls.js (`manifestIncompatibleCodecsError`). *Proposed:* treat AC-3/E-AC-3 remux as Apple-profile; browser profiles that lack those codecs get **audio transcode** (or an AAC rendition) before the web player adopts the engine.
- **Caption packaging (ENG-004):** household `DATA_DIR/subtitles/{rating_key}/{lang}.srt` → WebVTT in a master `SUBTITLES` group was selectable in WebKit and tvOS AVPlayer. *Proposed:* ship a single VTT (or coarse VOD subtitle playlist) first; segment VTT only if a client requires it.
- **Spike evidence:** [2026-11-19-engine-spike-findings.md](superpowers/specs/2026-11-19-engine-spike-findings.md) (throwaway code on `spike/engine-remux`, not merged).

## See also

- [SHARED_SESSIONS.md](SHARED_SESSIONS.md) — sessions as shared objects: owner, guests, remote, handheld captions
- [TIMELINE.md](TIMELINE.md) — the time-coded layer that captions feed
- [NATIVE_CLIENTS.md](NATIVE_CLIENTS.md) — device credentials, capabilities, API contract
- [DESIGN.md](DESIGN.md) — player behavior on the web today (hold-to-2×, fullscreen)
