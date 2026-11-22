# Handoff: home and away addresses

**Date:** 2026-11-21 · **Capability:** `household_addresses` 1

## What changed

The owner sets the public base URL (the away address) with `PUT /api/network/public-base-url`:

```json
{ "public_base_url": "https://films.example.com" }
```

The value is an `http` or `https` origin. A path, query, fragment, or username is HTTP 400. An empty string clears it. Only the household owner can set it.

Signed-in `GET /api/features` includes:

```json
"addresses": { "home": "http://10.0.0.8:8788", "away": "https://films.example.com" }
```

`home` is the last origin observed from the home network, or `""` after a restart until a home request arrives. `away` is the owner’s address, or `""`. A signed-out features response has `capabilities.household_addresses` and does not include `addresses`.

Engine playlist and segment URLs stay relative. `master_url` looks like `/api/playback/sessions/{id}/{token}/master.m3u8`. Rendition and segment names inside the playlist have no scheme and no host.

## What the client does

- Read `addresses` only after sign-in, and only when `household_addresses` is at least 1.
- Join a relative playlist or segment URL to the address the device is using: home while on the home network, away otherwise.
- Do not expect the server to embed either address in a playlist.

## Done when (client)

- A signed-in client can show which address it will use, and can play a relative `master_url` against that address.
- A signed-out client does not need the addresses to draw the sign-in screen.
