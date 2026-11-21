# Playback engine

How Projectionist plays a title from your library: one stream engine, owned by Projectionist, shared by every client — the web app, native apps, and anything that speaks the API. Plex is the first **media source**, not the player.

**Status:** ENG-001 through ENG-004, ENG-007, and the library playability report (ENG-011) are in the tree. The web player uses an engine session only when the owner turns on Play through Projectionist. That household switch is `features.play_through_projectionist` (also `PUT /api/playback/engine-setting`) and it is off by default. Turning it off changes the next play, with no restart. An engine session is also opt-in on the request: `POST /api/playback/sessions` starts a remux only when `engine_opt_in` is true. `playback_engine` on `GET /api/features` means this server can. It does not mean a client must. When the engine can turn a title's captions into WebVTT — the household subtitle file first, then an embedded text track — that title plays through the engine and the session does not record a caption fallback. Picture captions still stay on the Plex path until ENG-005, and the session records why. A plan the engine cannot remux does the same. Fullscreen controls stay the web player's. Item IDs (`ENG-…`) are tracked in [docs/roadmap/](roadmap/README.md).
**Audience:** Developers / contributors, owners for the honest limits.
**Related:** [SHARED_SESSIONS.md](SHARED_SESSIONS.md) · [TIMELINE.md](TIMELINE.md) · [TRACKS.md](TRACKS.md) · [NATIVE_CLIENTS.md](NATIVE_CLIENTS.md) · [ARCHITECTURE.md](ARCHITECTURE.md)

Jump to: [Why](#why-own-the-stream) · [Today](#today-the-plex-transcode-path) · [Target](#the-target-engine) · [Stream plans](#stream-plans) · [Captions](#captions) · [Devices](#device-profiles) · [Playability report](#library-playability-report) · [Sources](#media-sources) · [QA baseline](#qa-baseline-2026-11-21) · [Playlist 401](#playlist-401-on-a-device-credential-2026-11-21) · [Limits](#honest-limits) · [Items](#roadmap-items) · [Open decisions](#open-decisions)

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

Seen on QA 1.41.1, on this Plex path, which the web keeps until ENG-007 is switched on. The master playlist advertised `BANDWIDTH=3410779` (the file’s average bitrate plus 25%). Safari fetched `00000.ts` through `00009.ts` and then stopped. Several segments still ran at about 4.7–5.1 Mbps, above that advertisement. In HLS, `BANDWIDTH` is the peak segment bitrate and `AVERAGE-BANDWIDTH` is the average.

The write-up is `docs/specs/2026-11-20-safari-playback-stall.md`. Safari stops requesting the next segment when a segment’s bitrate exceeds the variant `BANDWIDTH`.

**Shipped in 1.41.2.** `BANDWIDTH` is the measured peak segment bitrate plus 10 percent. `AVERAGE-BANDWIDTH` is the container average. Plex start parameters are unchanged. **Still to prove:** a feature film plays in Safari on QA for 15 minutes, with seeking, in a fresh session.

---

## The target engine

```
             ┌────────────────────────────────────────────────┐
 client ───► │ POST /api/playback/sessions                     │
 (+ device   │   title, start offset, device profile,          │
  profile,   │   engine_opt_in                                 │
  opt-in)    └───────────────┬────────────────────────────────┘
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
      /api/playback/sessions/{id}/{token}/master.m3u8
        ├─ video rendition(s)
        ├─ audio renditions (languages, commentary)
        └─ SUBTITLES group: WebVTT renditions (text + OCR’d image tracks)
```

Principles:

- **Copy before you encode.** Most libraries are H.264 / HEVC with AAC / AC-3 / E-AC-3. Repackaging into fragmented-MP4 HLS (`ffmpeg -c copy`) costs a little I/O and almost no CPU, so a homelab box can serve several rooms at once.
- **A real VOD playlist.** Segments are planned from the file’s keyframes up front, so the playlist covers the whole title. Seeking is the client’s job inside a complete playlist, not a server restart.
- **Captions are tracks.** Every usable caption is a WebVTT rendition in the master playlist’s `SUBTITLES` group. Players switch them natively; the system player keeps them in fullscreen and picture-in-picture.
- **The token boundary holds.** Clients only ever see `/api/playback/sessions/{id}/…`. No file paths, Plex tokens, or source URLs cross the API — the same rule `library_privacy.py` enforces for browse.
- **Session URLs work without headers.** Playlist and segment URLs carry a short-lived, unguessable session token in the path, scoped to one session. Starting a session needs the member’s credential and `engine_opt_in: true`. Fetching its segments does not need an `Authorization` header — AirPlay receivers, picture-in-picture, and some system players cannot send one. When the household has accounts, the gate lets that playlist and segment path through and the route checks the token. A wrong token is 404. Progress and stop still need the member credential.
- **Opt-in is the client’s choice.** `playback_engine` means this server can open an engine session. A request without `engine_opt_in` gets `plan: "library"`, `playable: false`, and an empty `master_url`, whatever the household switch says. The client then uses `POST /api/library/playback/start`. The web sends the opt-in only from Play through Projectionist.
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

ENG-004 ships the text half of that model. A file at `DATA_DIR/subtitles/{rating_key}/{language}.srt` becomes one WebVTT rendition in the master playlist’s `SUBTITLES` group, ahead of any embedded text track in a language the cache already covers. The playlist is a single VTT inside a one-segment VOD subtitle playlist. An embedded text track (SRT, ASS, mov_text, WebVTT) is extracted to WebVTT **before Play**, by the jobs engine, and cached beside that household file at `DATA_DIR/subtitles/{rating_key}/prepared/`. A new arrival, Continue Watching, For you, or opening the title page queues the title. A library scan does not enqueue every title. The title being played is extracted first. One ffmpeg runs at a time, at low priority, and a restart continues the queue. Play does not run ffmpeg and does not use the old 20-second limit. A track that is already WebVTT goes straight into the session. A text track that is not ready yet still uses the Plex path, the session records *“These captions are not ready yet, so this title stays on the Plex path.”*, and the extraction keeps running so the next play can be direct. That sentence is not a path-mapping error. Picture tracks are not converted here. A title that needs captions and has only those still uses the Plex path, and the session records *“These captions are not ready as WebVTT, so this title stays on the Plex path.”* The playability report can count those two sentences apart: captions still being prepared, and captions that are pictures.

Why it matters: captions you can switch in the system player, in fullscreen, in picture-in-picture, on a phone in your hand ([SHARED_SESSIONS.md](SHARED_SESSIONS.md#handheld-captions)), and as a time-coded text source for the curator ([TIMELINE.md](TIMELINE.md)).

---

## Device profiles

A client declares what it can decode; the planner never guesses from a user-agent string.

```jsonc
// Sent with POST /api/playback/sessions (ENG-003)
{
  "engine_opt_in": true,             // without this, the answer is the library path
  "profile": {
    "id": "apple-tv-4k-3",           // stable name, or "custom"
    "containers": ["mp4", "hls-fmp4", "hls-ts"],
    "video": [{"codec": "hevc", "max_level": "5.1", "bit_depth": 10, "hdr": ["hdr10", "dolby-vision-8.1"]},
              {"codec": "h264", "max_level": "5.2"}],
    "audio": ["aac", "ac3", "eac3", "alac", "flac"],
    "max_bitrate_kbps": null,        // null = LAN, no cap
    "captions": ["webvtt"]
  }
}
```

- Native Apple clients send an accurate profile from `AVURLAsset.isPlayableExtendedMIMEType` / `AVPlayer.eligibleForHDRPlayback` probes.
- The web app builds the same profile at play time. It asks `canPlayType`, `MediaSource.isTypeSupported`, and `MediaCapabilities.decodingInfo` about HEVC (`hvc1`, 8-bit and 10-bit), AV1, AC-3, and E-AC-3. Any yes is a yes, so Safari can report HEVC when Media Source does not list it. The level and bit depth are the rows that passed. A named profile that omits `bit_depth` does not reject 10-bit.
- The plan records that answer in `profile_answer` (`hevc up to 5.1, 10-bit`, `hevc not in profile`, `eac3`, `eac3 not in profile`). The session reason includes the same words. A browser that does not report HEVC still gets plan `full`.
- Profiles are capped by a **network hint** (`lan` / `remote` + measured throughput) so a remote phone gets a sensible bitrate ladder.

---

## Library playability report

ENG-011 is a dry run. It runs only when the owner refreshes Settings → Playback. Opening Settings, starting the server, scanning the library, and the jobs-engine timer do not start it. The first result is the planner applied to the stream metadata Plex already returns: container, codecs, profile, level, and bit depth. Shares appear then. ffprobe confirms each file afterwards, one at a time and at low priority, and a restart continues instead of starting over. While that confirmation runs, Settings polls progress only: how many titles were planned from Plex metadata, how many ffprobe has confirmed, the message, and each profile’s shares. Title names load one page at a time when an owner opens a tier (`profile` and `tier` on the same route). The file on disk still holds every title, so a restart can continue. A Play that needs ffprobe does not wait on that walk or on caption extraction, and it does not run at idle priority. Refresh can also send this browser’s profile, the same object a session already accepts. The report does not transcode, remux, or extract captions.

For one title the row is the planner’s plan, the tier an owner should read, and the reason. Captions that are text but not WebVTT yet stay apart from picture captions. A video codec the profile cannot play is “ask the media source to transcode.” A file the engine cannot read is “not playable through the engine.”

| Tier | What the owner sees | Planner plan |
|------|---------------------|--------------|
| `direct` | Serve the file | `direct` |
| `remux` | Remux | `remux` |
| `audio` | Audio-only | `audio` |
| `captions-pending` | These captions are not ready yet | would have been direct, remux, or audio |
| `needs-ocr` | Picture captions that are not text yet | would have been direct, remux, or audio |
| `source-transcode` | Ask the media source to transcode | `full` |
| `not-playable` | Not playable through the engine | `plex-fallback` |

Shares count those tiers. `hardware` says how many titles on that profile need a video transcode: “A GPU with Quick Sync would let N titles play without Plex.” Audio-only and picture captions are not in that count. Later tiers (audio transcode, source transcode as a served plan, OCR, pre-optimized copies, our own video transcode) are not started.

```bash
# Owner: progress and shares, without every title row. No file paths.
curl -s -H "Authorization: Bearer YOUR_OWNER_CREDENTIAL" \
  "http://your-host:8788/api/playback/playability?view=progress" \
  | python3 -m json.tool

# One page of title names for a tier. `limit` is capped at 40.
curl -s -H "Authorization: Bearer YOUR_OWNER_CREDENTIAL" \
  "http://your-host:8788/api/playback/playability?profile=safari&tier=remux" \
  | python3 -m json.tool
```

One title row. The saved report keeps it inside `profiles[].titles`. A title page returns the same fields:

```json
{
  "rating_key": "remux",
  "title": "Remux Feature",
  "tier": "remux",
  "label": "Remux",
  "plan": "remux",
  "reason": "MKV container; H.264 + AAC playable on safari (h264 up to 5.2; aac)",
  "profile_answer": {"video": "h264 up to 5.2", "audio": "aac"}
}
```

How it works: Refresh from Settings posts this browser’s profile and stores the result under `DATA_DIR/engine/playability.json`. The same planner as `GET /api/playback/plan` runs on Plex’s stream list first. `planned_from_plex`, `confirmed_by_ffprobe`, and `running` are on that document while ffprobe is still going. The jobs-engine task `playability_report` stays registered and disabled so an older install stops walking on a timer.

Honest limits: the named Safari and Chrome profiles are the dry-run shortcuts, not a measurement of one household’s browser. The browser profile on Refresh is the measurement. The report does not play anything, and it does not start ENG-012, ENG-013, ENG-005, ENG-014, or ENG-006.

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

## QA baseline (2026-11-21)

First playability sample on QA, image `romwil/projectionist:1.42.0`, digest `sha256:ddc59f71969e1d9d682d9cf5305dad7a79fbe60959432fe49e6cdd04d52e02a0`, revision `6f5f9256`. The library was mounted read-only at the same container paths production uses: movies `/movies`, television `/tv`, preroll `/preroll`. The owner path map was `/data/media/movies` → `/movies`, `/data/media/tv` → `/tv`, `/data/media/preroll` → `/preroll`. Production mounts were not changed. Play through Projectionist was on for the owner only, then turned off.

| Client | Title | Container / codec | Plan | Result |
|---|---|---|---|---|
| Chrome | Purgatory | MP4, H.264, AAC | direct | Resumed near 7:30. Seek past the buffer (about 10:23 to 25:23) played. Pause and resume worked. Still the engine path after 18 minutes. |
| Safari | Purgatory | MP4, H.264, AAC | direct | After reload, resumed at 25:55. One far seek waited until the full playlist was present (933 segments). The next seek, to about 53:20, played. Pause and resume worked. 15 minutes 49 seconds after that seek. |
| Chrome and Safari | The Swan Princess: Escape from Castle Mountain | MKV, H.264, AAC | remux | Playable session. |
| Chrome and Safari | Mulholland Drive | MKV, HEVC | full | Not playable. HEVC is above what the web profile accepts. |
| Chrome and Safari | Peep Show “Local Zero” | MKV, H.264, AAC | remux | Playable, and the session wrote a WebVTT rendition. |
| Chrome profile | The Dick Van Dyke Show S3E16 | MKV, H.264, E-AC-3 | audio | Not playable. E-AC-3 would have to be transcoded. |
| Safari profile | The Dick Van Dyke Show S3E16 | MKV, H.264, E-AC-3 | remux | Playable, with a WebVTT rendition. |
| Chrome and Safari | Adventures of Zatoichi | MKV, English SubRip | plex-fallback | Captions were not ready as WebVTT within 20 seconds. |
| Chrome and Safari | 13 Assassins | picture captions only | plex-fallback | Captions are not ready as WebVTT. |

Apple TV, same run: an engine session opened, the playlist returned 401, and playback did not fall back to the library session. That 401 is the next section. This table is the failure, recorded before the fix.

Direct MP4 H.264/AAC, MKV H.264/AAC remux, and WebVTT for a text caption all stay. Every case the engine cannot serve falls back to Plex and records the reason. That part of the run is the baseline to keep.

Text captions are now extracted before Play, off the 20-second limit that stopped *Adventures of Zatoichi* on this image. A text track that is already WebVTT plays through the engine. One that is still being prepared falls back and records that the captions are not ready yet, which is not a path error. *13 Assassins* still falls back because its captions are pictures.

The HEVC row is what a profile without an HEVC answer planned, including a Safari-shaped body whose id was `web`. The web player now asks the browser at play time. *Mulholland Drive* plans `remux` where those checks report HEVC at a level and bit depth the file fits, and stays `full` where they do not. E-AC-3 remuxes only when the profile lists it.

## Playlist 401 on a device credential (2026-11-21)

On that QA image, with `playback_engine` at 1 and accounts turned on, a paired Apple TV opened an engine session for *Purgatory*. `POST /api/playback/sessions` returned 200. The playlist request then returned 401 twice. The preroll played. The film did not. The app did not open a library session.

The post succeeded because the household gate accepts `Authorization: Bearer` with the device credential. The session’s `master_url` is `/api/playback/sessions/{id}/{token}/master.m3u8`. The playlist route (`playback_session_media`) authenticates that path token with `session_for_token` and does not read `Authorization`. The player requested the URL with neither the device bearer nor a `curatorx_session` cookie. That is the header-free shape AirPlay and picture-in-picture need. With accounts on, `multi_user_api_auth_middleware` still required a bearer or a session cookie for every `/api/` path that was not a public handshake, and this playlist path was not one, so the gate returned 401 `Authentication required` before the route could check the token. A wrong path token would have been 404 from the route, not 401. The player retried the playlist, which is the second 401. The preroll is a separate library request that sends the device bearer, so the gate allowed it. The app had already accepted the playable engine session, so a later playlist failure did not start library playback. Chrome and Safari on the same run played, because the video element sends the session cookie and that cookie satisfies the same gate. Single-owner mode never applies the gate.

The fix on main, not in the 1.42.0 image: a client gets a playable engine session only when it sends `engine_opt_in: true`. The playlist and segment paths are now a handshake pattern, the route still rejects a bad token with 404, and a device credential can fetch the playlist and an fMP4 `.m4s` segment with no `Authorization` header and no session cookie. A test opens a session with a device credential and reads both with no header and no cookie. Progress, stop, and opening a session stay behind the member credential.

## Honest limits

- **Browsers decode less than Apple devices.** The web profile is this browser's codec checks, not a fixed Chrome or Safari list. A browser that does not report HEVC or E-AC-3 does not get those streams as a remux. DTS and TrueHD still wait for an audio transcode.
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
| ENG-004 | WebVTT caption renditions in the master playlist (household cache first). Text subtitle streams are extracted to WebVTT ahead of play (a new arrival, Continue Watching, For you, or the title page) so a large file does not miss a play-time limit. A library scan does not enqueue every title. The title being played is first. One low-priority ffmpeg runs at a time, and a restart continues the queue. A text track that is not ready yet records that the captions are not ready, and the next play uses the cache. Picture captions keep the Plex fallback. The playability report can count those two reasons apart | ENG-003 |
| ENG-005 | Image-caption OCR job (jobs engine, cached, labeled). Tier 4 in the playback stack. Unchanged by the 2026-11-21 findings: picture captions stay on the Plex path until this exists | ENG-004 |
| ENG-006 | Own video transcode, re-scoped 2026-11-21. (a) Software 1080p H.264 on CPU-rich servers, only after the owner opts in and a startup benchmark clears a threshold, with a low concurrency cap. 4K, HEVC/AV1 output, and HDR tone-mapping in software are never chosen. (b) Hardware VAAPI/QSV and NVENC when an encoder test-open succeeds. Both wait until ENG-011 shows enough titles need them. (a) can be tested on a 2× Xeon E5-2630 v3, 32 threads, no GPU. (b) waits for a GPU box | ENG-003, ENG-011 |
| ENG-007 | Web player adoption, behind *Play through Projectionist* (off by default). The web sends `engine_opt_in: true` with the session. The profile is built at play time from `canPlayType`, `MediaSource.isTypeSupported`, and `MediaCapabilities.decodingInfo` for HEVC (`hvc1`, including 10-bit), AV1, E-AC-3, and AC-3. The plan records which answer it used. *Mulholland Drive* plans `remux` where that check reports HEVC, and `full` where it does not | ENG-003 |
| ENG-011 | Library playability report. The owner starts it from Settings → Playback. It plans first from Plex stream metadata, shows those shares while ffprobe confirms in the background, and does not start on a timer. Settings shows the share that is direct, remux, audio-only, captions not ready yet, needs OCR, or needs a video transcode, plus progress, the top reasons, each title’s tier, and what a GPU would change. It does not transcode | ENG-001, ENG-002 |
| ENG-012 | Audio-only transcode tier. Copy the video, convert the audio to the device profile’s target, serve segments like a remux, and cap how many run at once. A DTS or TrueHD film plays in Safari and on an Apple TV profile with the video untouched. The Chrome E-AC-3 row in the QA baseline is the first web case | ENG-003, ENG-011 |
| ENG-013 | Source-transcode tier. Today’s Plex fallback becomes a planned tier with a reason, behind the media-source interface, so a later source can provide it. Members see the same playback | ENG-003 |
| ENG-014 | Pre-optimized versions. An owner-triggered or scheduled job makes compatible copies for chosen titles, or for everything the report says needs a video transcode, inside a disk budget. The planner prefers those copies and plays them as direct or remux | ENG-011, ENG-012 |
| ENG-008 | Scrub thumbnails (trickplay image sprites / I-frame playlist) | ENG-003 |
| ENG-009 | Live Channels on engine sessions (same stations, new stream). Build as the Live facade ARCH-007 asked for; PRD-007 freeze still holds (no new channel types) | ENG-003; ARCH-007 |
| ENG-010 | Jellyfin media source | ENG-001 |

## Open decisions

- **Client order (decided 2026-11-20, re-sequenced the same day):** Apple clients adopt ENG-003 first. The web follows immediately as ENG-007, behind a household setting that is off by default, not after the rest of the engine series. Until that setting is on, the web stays on the Plex path.
- **Path naming:** keep `/api/library/playback/*` and switch its backend, or introduce `/api/playback/sessions/*` and deprecate the old routes after ENG-007. *Proposed:* new namespace, old routes stay as the Plex fallback until parity. **Spike (2026-11-19):** path-token session URLs under a new namespace worked for Safari/WebKit and tvOS `AVPlayer` without `Authorization` headers — keeps the proposed ENG-003 shape.
- **Segment cache:** on-the-fly remux per session vs. a short-lived on-disk segment cache under `DATA_DIR` shared by concurrent viewers. *Proposed:* on-the-fly first; cache only if measurements demand it. **Spike:** serving a pre-built `-c copy` fMP4 package was ~0% CPU idle; no evidence yet that remux needs a shared disk cache for single-viewer Apple playback.
- **HDR on the web:** whether to tone-map or refuse HDR → SDR on browsers without HDR support.
- **Browser audio vs remux (ENG-002 / ENG-006):** *3 Ninjas* H.264+AC-3 remux played on Apple clients and was **rejected** by desktop Chromium/hls.js (`manifestIncompatibleCodecsError`). *Proposed:* treat AC-3/E-AC-3 remux as Apple-profile; browser profiles that lack those codecs get **audio transcode** (or an AAC rendition) before the web player adopts the engine.
- **Caption packaging (ENG-004):** a household `DATA_DIR/subtitles/{rating_key}/{lang}.srt` is one WebVTT file plus a one-segment VOD subtitle playlist in the master `SUBTITLES` group. Embedded text tracks are extracted to the same shape ahead of Play, and cached beside that file, when that language is not already in the household cache. Play does not extract. Segmenting the VTT waits until a client requires it. Picture captions stay on the Plex path until ENG-005. The spike showed that shape is selectable in WebKit and tvOS AVPlayer.
- **Spike evidence:** [2026-11-19-engine-spike-findings.md](superpowers/specs/2026-11-19-engine-spike-findings.md) (throwaway code on `spike/engine-remux`, not merged).
- **Opt-in (decided 2026-11-21):** an engine session is only for a client that sends `engine_opt_in`. The capability is “this server can.” The household switch does not force a client onto the engine. Playlist URLs stay header-free, and a device credential can fetch them.
- **Playback tiers (decided 2026-11-21), cheapest first:** direct, remux, audio-only transcode, captions as text (ENG-005), source transcode, own video transcode (ENG-006, opt-in), pre-optimized copies. The planner records the tier, the reason, and the profile answer that chose them. Software video transcode is 1080p H.264 only, above a startup benchmark, with a low cap. The browser runtime profile is done: the web asks the browser at play time. Text captions are extracted ahead of play. ENG-011, the library playability report, is in the tree. Next, not started: ENG-012 audio → ENG-013 source tier → ENG-005 → ENG-014 → ENG-006 when the report says it is worth it. ENG-012, ENG-013, and ENG-014 are accepted and not started. Startup detection (core count, a one-time 1080p encode benchmark, Quick Sync or VAAPI, NVENC, and which encoders ffmpeg actually opens) lands with ENG-006 as a `playback_hardware` capability. No hardware is required to run Projectionist. Live channel normalization (ENG-009) is not in this stack.

## See also

- [SHARED_SESSIONS.md](SHARED_SESSIONS.md) — sessions as shared objects: owner, guests, remote, handheld captions
- [TIMELINE.md](TIMELINE.md) — the time-coded layer that captions feed
- [NATIVE_CLIENTS.md](NATIVE_CLIENTS.md) — device credentials, capabilities, API contract
- [DESIGN.md](DESIGN.md) — player behavior on the web today (hold-to-2×, fullscreen)
