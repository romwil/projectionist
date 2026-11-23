# Drop: the warm-up screen — entertain while a stream starts

**From:** Will (via design chat) · **Date:** 2026-11-22 · **Items:** new EXP item (next free number); pairs with the engine session-state work (preparing/ready/failed) from the 1.45.1 findings
**Reference:** design canvas board `TVWarmup` and its sticky.

## Why

Playback now takes real work before the first frame: waking disks, remuxing, encoding the sound, preparing captions, sometimes falling back to Plex. A spinning disc makes 15 seconds feel like a minute. A screen worth watching (the title's art, a projector-booth feel, and a dry joke about what's actually happening) makes the wait part of the show. It also gives the engine room to start properly without anyone giving up.

The static on Live was right for the retro antenna feel, and it stays: as a short channel flip, not as the whole wait.

## Decisions (accepted)

1. **When it shows:**
   - Any on-demand start that isn't playing within ~0.8 s.
   - On Live, a tune shows static first. If the tune takes longer than ~1.5 s, the static dissolves into the warm-up screen.
   - It ends at the first frame with a quick fade.
2. **What's on it:**
   - The title's own backdrop and poster (art route), cross-fading every ~8 s with a slow drift.
   - A soft projector beam that flickers.
   - "Now starting · *room*", then the title, year and runtime.
   - **One joke line at a time** (~4 s each).
   - Under it, a small **honest status line** with a counter (for example "Preparing the sound for your speakers · 6 s"), plus "Press Back to cancel" (web: Esc).
   - On Live the art is the program's or channel's art.
3. **Lines follow the real state.** The server's session state names the current step: `waking_disk`, `probing`, `remuxing`, `encoding_audio`, `preparing_captions`, `falling_back`, `waiting_on_plex`, `buffering`. The client picks from that step's pool first, then the general pool. No line repeats within a session, and the line never lies about something serious (an error is never a joke).
4. **Fallback is seamless.** When the first-frame fallback switches to the library path, the screen stays up and moves to the `falling_back` pool. The member never sees a failure for a successful fallback.
5. **After ~45 s with no first frame**, the jokes stop. A plain message offers **Keep waiting** / **Try again** / **Back**, with the honest reason.
6. **Owner setting:** Warm-up humor **On** (default) / **Dry** (status line only, art kept) / **Off** (minimal spinner on the art). Lines are written to be fine for every member, Youth included; no swearing and no adult references.
7. **Accessibility:** the status line is the live region; joke lines are decorative (`aria-hidden`), so a screen reader hears the truth, not the bit. Reduce Motion: no drift, no flicker, lines swap without movement. Meets contrast on the darkest and lightest art.
8. **Lines live in one server-owned file** (`warmup_lines.json`, with a pool per state) so every client shows the same bits, and new ones ship without a client release. Clients cache it. The file is versioned and served with the capability.

## Starter copy bank (original lines; extend freely, keep them PG)

**General**
- switching VHS tapes.
- finding the right burned DVD. it's the one labeled "FINAL (real)".
- blowing on the cartridge. it never works. we do it anyway.
- adjusting the tracking. a little more. no, back.
- rewinding. be kind.
- the projectionist is threading the reel with his teeth.
- checking the gate for hair.
- shushing the people in row F.
- popping the popcorn. one kernel at a time.
- flipping the laserdisc to side B. it was side A.
- untangling the tape from the VCR's mouth.
- convincing the DVD player it's region-free.
- dusting off the good copy.
- the film is fine. the projectionist needed a minute.
- turning the lights down. slowly. dramatically.

**`waking_disk`**
- waking the hard drives. they were napping.
- the disks are spinning up. they're doing their stretches.
- knocking politely on drive 4.

**`remuxing` / `probing`**
- moving the movie into a nicer box. same movie.
- reading the label on the reel.
- repackaging the frames. no frames were harmed.

**`encoding_audio`**
- teaching your surround sound to share.
- translating the speakers' secret handshake.
- folding seven speakers into fewer speakers.

**`preparing_captions`**
- typing up the subtitles by hand.
- the captioner is a fast typist. mostly.
- proofreading the subtitles. "your" vs "you're" again.

**`falling_back` / `waiting_on_plex`**
- plan b: borrowing the neighbor's VCR.
- calling in a favor from the other projector.
- the backup reel is warming up.

**`buffering`** (mid-film stall)
- the reel slipped. hold on.
- someone tripped over the projector cord.

## Done when

- Web and Apple TV show the warm-up for a cold engine start (a slowed fixture works) with the real step's lines, the honest status and the counter. The fallback transition shows no error.
- The 45 s screen offers its three choices.
- The owner setting works.
- Reduce Motion is respected, and screen readers hear only the status line.
- The fixture playback test asserts the warm-up appears and is gone after the first frame.

---
## Processing note (agent, 2026-11-22)
- Created: EXP-018
- Updated: board status and sequencing; EXPERIENCE.md (lines file, step names, web screen); NATIVE_CLIENTS.md (proposed capability name only)
- Outbox: 2026-11-22-EXP-018-apple.md
- Needs the person: nothing. The capability name `warmup_screen` is proposed and is not on the manifest. Live stays inside the PRD-007 freeze: the static on a tune stays a short flip, and this adds no channel type.
