# Drop: the web app installs like a desktop app

**From:** Will · **Date:** 2026-11-23 · **Roadmap:** EXP-019

## Why

Some households use the web app as their client. Installing it gives that household its own window, an icon, and media keys, without a second native app.

## Decisions (accepted)

1. A web app manifest: name, theme and background from the lights-down tokens, icons including a maskable one, `display: standalone` with window controls overlay where the browser supports it, start URL Explore, scope `/`.
2. A minimal service worker. It stores the shell and static assets. It never stores API responses, art, or media, including playlists. When the server cannot be reached, an offline page says so.
3. A quiet Install Projectionist entry in Settings and the account menu. No banner. The browser's own install UI still works.
4. The Media Session API on the library player: title, artwork, play, pause, and seek.
5. Web Push waits for NAT-006. This item does not ask for notification permission.
6. Shortcuts: Ctrl or Command K opens Search. Space pauses, the arrow keys seek, and F toggles fullscreen, matching the player keys already on the page.

## Done when

- The manifest is installable and the installed window opens on Explore.
- Media keys control playback.
- The service worker serves no API or media response from cache.
- The page-speed budget still passes.

---
## Processing note (agent, 2026-11-23)
- Created: EXP-019, in progress with this change. Push is not part of it.
- Outbox: none. Web only.
- Needs the person: nothing.
