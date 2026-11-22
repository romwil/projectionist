# Shared playback sessions

A playback session is a **room**, not a private stream: one screen plays, the person who started it owns the intent, and other devices can join — as a remote, as a handheld caption display, or as a companion that knows exactly where the film is.

**Status:** Proposed (design). Builds on the Apple TV pairing and throw work (`projectionist/devices/`, `web/device_routes.py`) and on the [playback engine](PLAYBACK_ENGINE.md). Item IDs (`SES-…`) are tracked in [docs/roadmap/](roadmap/README.md).
**Audience:** Developers / contributors; members and owners for the behavior.
**Related:** [PLAYBACK_ENGINE.md](PLAYBACK_ENGINE.md) · [TRACKS.md](TRACKS.md) · [TIMELINE.md](TIMELINE.md) · [NATIVE_CLIENTS.md](NATIVE_CLIENTS.md) · [PRIVACY.md](PRIVACY.md)

Jump to: [The idea](#the-idea) · [Home and away](#home-and-away) · [Roles](#who-is-in-a-session) · [What a guest can do](#what-a-joined-device-can-do) · [Realtime](#the-realtime-channel) · [Handheld captions](#handheld-captions) · [Privacy](#privacy-and-youth) · [Items](#roadmap-items)

---

## The idea

> **Friday night.** You start *Heat* on the living-room Apple TV from your phone. The phone becomes a rich remote. Your partner opens Projectionist on theirs and taps **Join Living Room** — they get captions in their hand without turning them on for the room. Twenty minutes in, you swipe up and ask your curator, “who was that in the car just now?” — and it already knows you are at 0:21:40.

A device at home and a device away from home do not share one origin. [Home and away](#home-and-away) is how a client learns both, while the playlist itself stays relative.

Three ideas carry that evening:

1. **The session is the unit.** Position, state, chosen tracks, and the interaction level belong to the session, not to a device. Any joined device reads the same truth.
2. **The initiator owns the intent.** Whoever started playback chose movie night or film class. They set the [track level](TRACKS.md#levels) and can change it mid-film. Guests never change what the shared screen shows.
3. **Every device can be a second screen.** Phones, tablets, and laptops join through the same API. The Apple apps are the first rich client, not the only one.

---

## Who is in a session

| Role | Who | Can |
|------|-----|-----|
| **Owner** (of the session) | The member who started playback — on the TV, by throw, or from a phone | Everything: transport, track level, captions on the big screen, end session, invite |
| **Guest** | A signed-in household member who joined | Remote transport (if the owner allows), handheld captions, their own private curator chat with the session’s time context |
| **Screen** | The device rendering the picture (Apple TV, a browser tab) | Plays the stream, renders big-screen overlays, reports position |

A session has exactly one screen. Moving playback to another screen is a **handoff**: the session keeps its id, position, and track; the old screen stops.

*Proposed:* the household’s Apple TVs are visible as **rooms** (“Living Room”) to every signed-in member; *what is playing* in a room is visible only to the session owner and joined guests. Joining needs either the owner’s approval in the moment, or the code on the TV’s pause screen.

---

## What a joined device can do

| Capability | Owner | Guest | Notes |
|------------|-------|-------|-------|
| Play / pause / seek / skip ±15 / 2× | ✓ | ✓ when the owner allows remote for guests | 2× on library titles only; Live keeps the guide clock |
| Change big-screen captions / audio | ✓ | — | Guests use handheld captions instead |
| Handheld captions | ✓ | ✓ | Per device; never changes the room |
| Track level (Off / Moments / Pop-ups / Class) | ✓ | — | See [TRACKS.md](TRACKS.md#levels) |
| Curator chat with “now” context | ✓ | ✓ (their own curator, private) | The question carries `session_id` + position; see [TIMELINE.md](TIMELINE.md#asking-about-now) |
| Detours (pause → clip → return) | ✓ starts / approves | sees on the big screen | Part of Class / Study tracks |
| End session / hand off | ✓ | — | |

---

## The realtime channel

Joined devices need sub-second state. Polling `GET /api/devices/me/intent` is right for a throw; it is wrong for a remote.

- **Transport:** a WebSocket per joined device at `/api/sessions/{id}/live` (SSE fallback for the web, matching the existing `/api/chat/stream` pattern). *Open decision:* WebSocket vs SSE + POST commands; proposed WebSocket because commands and events are symmetric.
- **Events (server → devices):** `state` (playing / paused / buffering / ended), `position` heartbeat (~1 s while playing, plus on every seek), `track` (current level, next cue id), `cue` (a [track cue](TRACKS.md#cues) is due), `detour` (start / end), `members` (who joined), `ended`.
- **Commands (device → server → screen):** `play`, `pause`, `seek {ms}`, `skip {s}`, `rate {1|2}`, `captions {id|off}`, `level {…}`, `detour.accept`, `end`. The server authorizes every command against the session role table above, then relays to the screen.
- **Clock:** events carry server time; devices estimate the playhead from the last `position` + elapsed time, so handheld captions and cue timing stay within a few hundred milliseconds of the picture.

---

## Handheld captions

A guest (or the owner) can read captions on their own device while the room watches clean.

- The device fetches the session’s caption rendition list from the [engine](PLAYBACK_ENGINE.md#captions) and renders cues locally against the realtime playhead.
- Language is per device: one person reads English, another the original French.
- **How this works:** the cues are the same WebVTT the screen would use; nothing is generated per person. **Honest limit:** if the screen buffers, handheld cues pause on the next heartbeat — they can lag by up to a second during a seek.

---

## Privacy and youth

- **Taste stays personal.** A guest’s curator chat in a session is the guest’s own conversation and memory, with the same rules as Chat today. The session owner never sees a guest’s questions.
- **Youth.** A session started by a Youth member carries the rating ceiling: track content, detour clips, and curator answers are Youth-safe. An adult guest joining a Youth session sees the session as it is; they do not loosen it.
- **A Youth member joining an adult’s session asks first** (decided 2026-11-18). The join sends the session owner a notification: **“<Name> wants to join. Approving limits this room to <ceiling>.”** with **Approve** / **Not now**.
  - **Approve** tightens the whole session to the Youth member’s rating ceiling for as long as they are joined: track level content (Booth Notes Heat capped at Mild), detour clips, curator notes on the big screen, and what the room may play next.
  - **Not now** declines the join; the Youth member sees a plain sentence and nothing about what is playing.
  - *Proposed:* if the title already playing is above the ceiling, the prompt says so — “*Heat* is rated R. Approving stops it.” — and approval stops playback and opens a For you row the whole room can watch.
  - *Proposed:* when the Youth member leaves, the ceiling relaxes at the next title, never mid-title.
- **No new exports.** Session state is ephemeral; position reporting continues to feed Continue Watching and the watch tracker exactly as library Play does today.

---

## Home and away

A device on the home network and a device somewhere else need different origins. The owner sets the away address — the public base URL — in **Settings → Playback**. A signed-in `GET /api/features` publishes both:

```json
"addresses": { "home": "http://10.0.0.8:8788", "away": "https://films.example.com" }
```

Home is the origin of a request that arrived from the home network (a private address, loopback, a link-local address, or a `.local` / `.lan` / `.home.arpa` / `.internal` name). Projectionist remembers the latest one until the process restarts. Away is the owner’s address, or `""` until they set one. A signed-out client receives the capability and not the addresses.

```bash
curl -s -X PUT http://your-host:8788/api/network/public-base-url \
  -H "Authorization: Bearer YOUR_OWNER_CREDENTIAL" \
  -H "Content-Type: application/json" \
  -d '{"public_base_url":"https://films.example.com"}'
```

Engine playlist and segment URLs stay relative (`/api/playback/sessions/…`, `av/stream.m3u8`, `seg_0001.m4s`). The client joins them to the address it is using. The away address is never written into a playlist.

**How this works.** The capability `household_addresses` is `1` on every features response. The two strings are only on the signed-in payload. **Honest limit.** After a restart, home is empty until someone opens Projectionist on the home network. The away address is an origin: a path, a query, or a username in the URL is refused.

## Rooms

A room is a named screen in the household. Every signed-in member can read the list. A handheld is not a room. A removed screen is not a room.

```bash
curl -s -H "Authorization: Bearer YOUR_CREDENTIAL" \
  http://your-host:8788/api/rooms
```

```json
{ "rooms": [{ "id": "…", "name": "Living Room", "kind": "tv" }] }
```

The household owner, or the member signed in on that screen, can rename it with `PATCH /api/rooms/{id}` and `{"name": "Den"}`.

**How this works.** The capability `rooms` is `1`. The list is only the name. **Honest limit.** What is playing is not on this list. Joining a room is a later item. A browser tab is not a room yet.

## Roadmap items

| ID | Item | Depends on |
|----|------|------------|
| SES-001 | Device credentials for phones and tablets (done with NAT-002). Every web sign-in path can end in a device credential | pairing (shipped) |
| SES-002 | Rooms registry (named screens per household) + visibility rules (done: `GET /api/rooms`, `rooms` is 1) | SES-001 |
| SES-003 | Session object (owner, screen, position, level) on top of engine sessions | ENG-003 |
| SES-004 | Realtime channel (`/api/sessions/{id}/live`), command authorization, clock model | SES-003 |
| SES-005 | Join flow (owner approval or on-screen code) + guest permissions | SES-004 |
| SES-006 | Handheld captions | SES-004, ENG-004 |
| SES-007 | Handoff between screens (same session, new screen) | SES-004 |
| SES-008 | Web client as a second screen (join from a browser) | SES-005 |
| SES-009 | Youth join approval: owner notification, Approve tightens the session ceiling, Not now declines (absorbs review PRD-025) | SES-005, TRK-003 |

## See also

- [TRACKS.md](TRACKS.md) — what plays *with* the film: Moments, Pop-ups (Booth Notes), Class / Study
- [TIMELINE.md](TIMELINE.md) — how “who is in the car?” is answered at a position
- [NATIVE_CLIENTS.md](NATIVE_CLIENTS.md) — device credentials and capability negotiation
