# Handoff: a picture the device cannot play asks the media source

**Date:** 2026-11-21 · **Server item:** ENG-013 · **Capability:** `playback_engine` stays `1`.

## What changed

When the picture is outside the device profile, `GET /api/playback/plan` and `POST /api/playback/sessions` return:

- `plan`: `source-transcode`
- `playable`: false
- `master_url`: empty
- `reason`: a sentence, such as “HEVC video is not playable on web (hevc level is above profile hevc 5.1)”
- `source_reason`: `codec`, `level`, or `bit_depth`
- `provider`: `plex` today. A later source uses the same field with its own name

The server does not start ffmpeg for this plan. Every session response now includes `source_reason` and `provider`. They are empty unless the plan is `source-transcode`.

A file the server cannot read, a caption that is not ready, and a missing ffmpeg stay `plex-fallback` or the caption reason. Those are not this tier.

## What the client does

Keep the existing rule: play the engine playlist only when `playable` is true and `plan` is `direct`, `remux`, or `audio`. A `source-transcode` plan uses the same library playback the client already uses for any session that is not playable. There is no new screen and no new capability to gate on.

## Done when (client)

- A title whose picture the device cannot play still starts on the library path.
- The client does not request `master_url` for a `source-transcode` plan.
