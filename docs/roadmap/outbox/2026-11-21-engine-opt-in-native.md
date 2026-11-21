# Handoff: engine sessions are opt-in

**Date:** 2026-11-21 · **Server items:** ENG-003, ENG-007 · **Capability:** `playback_engine` stays `1` (this server can). It does not mean the client must open an engine session.

## What changed

`POST /api/playback/sessions` starts a playable engine session only when the body sets `engine_opt_in` to true and includes the device profile. Without that flag the response is:

- `plan`: `library`
- `playable`: false
- `master_url`: empty
- `reason`: the client did not opt in, so playback stays on the library path

No probe and no remux run in that case. The client calls `POST /api/library/playback/start` as it does for any session the engine marks not playable.

A playable session's playlist and segments stay header-free: `/api/playback/sessions/{id}/{token}/…`. Opening the session still needs the member credential (device bearer or session cookie). Fetching the playlist does not. A device credential can GET that URL with no `Authorization` header and no session cookie. A wrong token is 404. Progress and stop still need the member credential.

## What the client does

- Send `engine_opt_in: true` only when that client can play the header-free playlist.
- Until then, do not treat `playback_engine: 1` as an instruction to open an engine session. Use the library session.
- If a non-library playlist fails before the first frame (4xx or 5xx), retry once on the library session.

## Done when (client)

- With the household switch on and off, a title plays through the library session on a client that does not opt in.
- A client that does opt in sends the flag and its device profile, and plays the returned `master_url` with no bearer on the playlist request.
