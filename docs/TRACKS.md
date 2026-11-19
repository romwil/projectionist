# Tracks: Moments, Booth Notes, and Class

A **track** is what plays *with* a film or episode — like a commentary track on a disc, but built by your curator from your own library’s knowledge. Tracks turn playback into the experience the person who pressed Play asked for: a quiet movie night, a rewatch full of trivia and snark, or a full film class that pauses to show you a clip from another film and comes back.

**Status:** Proposed (design). Item IDs (`TRK-…`) are tracked in [docs/roadmap/](roadmap/README.md).
**Audience:** Developers / contributors; members and owners for behavior and limits.
**Related:** [TIMELINE.md](TIMELINE.md) · [SHARED_SESSIONS.md](SHARED_SESSIONS.md) · [PLAYBACK_ENGINE.md](PLAYBACK_ENGINE.md) · [CURATOR_KNOWLEDGE.md](CURATOR_KNOWLEDGE.md) · [PRIVACY.md](PRIVACY.md)

Jump to: [Levels](#levels) · [Booth Notes](#booth-notes) · [Class and Study](#class-and-study) · [Detours](#detours) · [Cues](#cues) · [Sources](#where-facts-may-come-from) · [Building](#built-on-request) · [On screen](#on-screen-rules) · [Limits](#honest-limits) · [Items](#roadmap-items)

---

## Levels

The session owner picks a level when they start, and can switch mid-film (see [SHARED_SESSIONS.md](SHARED_SESSIONS.md#who-is-in-a-session)).

| Level | What it is | On the big screen | On a joined phone |
|-------|-----------|-------------------|-------------------|
| **Off** | A promise: nothing on the glass | Nothing | Remote + captions only |
| **Moments** | Your curator, sparing — a handful of notes at key beats | One-line corner notes | The full note, sources, **Ask about this** |
| **Booth Notes** | Playful pop-ups: trivia, on-screen people and places, production lore, riffs | Frequent bubbles from the booth | Expanded bubbles + sources for facts |
| **Class / Study** | A lesson built around the title (or a season), with detours | Notes + detour bridges + clips | Lesson outline, readings, discussion |

Everything here works the same for **TV episodes and seasons** as for films. A study of *The Sopranos* is a Class track that spans episodes.

---

## Booth Notes

The rewatch mode. The inspiration is the late-80s/90s music-video pop-up format; the voice is Projectionist’s own: **the projectionist leaning out of the booth.** We never see them — a small, warm port window glows high in a corner, and the bubble comes out of it.

Each Booth Notes **edition** has two settings:

| Setting | Options | Meaning |
|---------|---------|---------|
| **Mix** | Facts · Riffs · Both | Facts are trivia, on-screen people, locations, production lore. Riffs are puns, snark, horror-host-style commentary — entertainment, not information |
| **Heat** | Mild · Spicy · Roast | How irreverent the voice is allowed to be |

> **You ask your curator:** “Make me a Booth Notes edition of *Heat* — both, spicy.”
>
> **Your curator replies** that it has queued the edition and will let you know. Later, your Inbox shows **“Your Booth Notes edition of *Heat* is ready!”** with a **Play with Booth Notes** button.

Rules that keep it fun *and* trustworthy:

- **Riffs never claim facts.** A riff is a joke and needs no citation. If a joke depends on a fact, that fact is sourced like any other.
- **Facts are true.** Every fact bubble carries its source; the phone shows it on tap.
- **Fact and riff bubbles look different** (tail and type voice), so nobody mistakes a pun for trivia.
- **Roast the film, not the people.** Riffs target the movie — plot holes, wigs, suspicious amounts of fog — never real people’s bodies, identities, or private lives.
- **Youth caps the Heat.** A Youth-started session tops out at Mild, and every bubble respects the rating ceiling.
- **The persona shapes the voice.** The member’s curator persona sliders (Admin → Persona / Settings) give each curator its own comic register.

---

## Class and Study

The serious end. Built from the course machinery that already exists in chat (`projectionist/syllabus/` — lineage, canon, compare, seminar walks), but placed **on the timeline**:

- A **lesson** is an ordered set of cues: notes at moments, prompts to notice something, and [detours](#detours).
- A **study** is a lesson that spans a season or series, with an outline the phone shows between episodes.
- A member asks for one in their own words — *“teach me Michael Mann’s nocturnal city through Heat”*, *“a study of Tony’s therapy sessions across season one”* — and the curator builds it, as it builds courses today.
- Lessons cite their sources and stay within the household’s library for any clip they show.

---

## Detours

The film-class move: the curator pauses the film, shows a short clip from another title to make a point or draw a contrast, and returns exactly where you were.

```
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│                   F R O M   T H E   S T A C K S              │
│                                                              │
│                        Thief  (1981)                         │
│               the same cold blue, fourteen years earlier     │
│                                                              │
│                  18 seconds · back to Heat at 1:12:04        │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

- **Only titles in the library.** A detour clip is a range (`start_ms`–`end_ms`) on another library title, played by the [engine](PLAYBACK_ENGINE.md) as a short session. No outside video.
- **The bridge is editorial.** The interstitial is a title card in Projectionist’s cinema language — not Live’s deliberately retro “between programs / tuning” slate. *Name provisional:* “From the stacks.”
- **The owner decides.** At Class level, detours play automatically; at Moments level they are offered on the owner’s phone first (“Show the *Thief* contrast?”).
- **Return is exact.** The film resumes at the paused offset; Continue Watching ignores the detour.

---

## Cues

A track is a list of **cues** on the [timeline](TIMELINE.md):

```jsonc
{
  "track_id": "trk_heat_booth_both_spicy_v3",
  "title": {"tmdb_id": 949, "file_fingerprint": "…"},
  "level": "booth_notes",
  "edition": {"mix": "both", "heat": "spicy"},
  "cues": [
    {"id": "c41", "at_ms": 4324000, "dwell_ms": 7000, "kind": "fact",
     "screen": "<one-line fact, under ~12 words>",
     "phone":  "<the longer version, with context>",
     "sources": [{"kind": "tmdb", "ref": "movie/949"}, {"kind": "public", "url": "https://…"}]},
    {"id": "c42", "at_ms": 4401000, "dwell_ms": 6000, "kind": "riff",
     "screen": "Two men, one table, zero blinking."},
    {"id": "c43", "at_ms": 4410000, "kind": "detour",
     "clip": {"tmdb_id": 11524, "start_ms": 3120000, "end_ms": 3138000},
     "bridge": "the same cold blue, fourteen years earlier"}
  ]
}
```

- `screen` is the big-screen line (short); `phone` is the expanded version.
- Cues are matched to the **file version**; a different cut gets its cue times re-aligned from dialogue, or the track says it was built for another cut.
- Clients render cues; they never generate them.

---

## Where facts may come from

| Track | Allowed sources |
|-------|----------------|
| **Moments, Class / Study** | Projectionist’s own index and found relationships (credits, motifs, kinship, relations), TMDB, the timeline layer, and the household’s own chat history where the member allows memory |
| **Booth Notes (facts)** | All of the above **plus trusted public sources** the server fetches and cites |
| **Booth Notes (riffs)** | No facts claimed; voice only |

**Trusted public sources are an owner setting.** Looking things up publicly tells those sites which titles the household is exploring. *Proposed:* Admin → Experience → Booth Notes → **Public sources**, off by default, with an allowlist the owner can edit; the fetch is made by the server, never by a client, and only for titles someone requested an edition of.

---

## Built on request

Tracks are **never** built for the whole library at once.

1. A member asks (chat, title detail, or the phone’s **Make an edition** button).
2. The jobs engine builds it in the background: ensures the [timeline](TIMELINE.md) exists, gathers facts, drafts cues with the curator, validates (sources present for facts, ceiling respected, cues inside the file’s duration), and stores the result.
3. The Inbox (and push, when a native client is registered) says **“Your Booth Notes edition of *Heat* is ready!”**
4. Editions are cached by **title × file version × level × mix × heat**, so “*Heat*, Both, Spicy” serves anyone in the household who asks for that edition. Persona voice is applied per member at render time where it changes only phrasing, not facts.

---

## On-screen rules

For every client that draws track content over the picture:

- **Calm by default.** One cue at a time; fade in, reading dwell, fade out.
- **Captions own the bottom band.** Cues sit in a corner clear of it; Booth Notes bubbles come from the booth port (top corner).
- **Off means off.**
- **Shared screen, owner’s intent.** Only the session owner changes the level on the big screen. Guests get expanded cues on their own devices.
- **Accessible.** Cue text meets contrast in Lights Down and Lights Up; motion respects reduced-motion settings; every cue is also available on a phone for people who read slower than the dwell.

---

## Honest limits

- **Language models invent things.** That is why facts need a source to ship and riffs are not allowed to claim facts. A cue without a source is dropped at validation, not shown.
- **Generation costs tokens.** A full Booth Notes edition is many LLM calls with a cloud provider, or a long run on a local model. Editions are on request, cached, and reused across the household.
- **Clips need the other title in the library.** A lesson that wants a film you don’t own says so and suggests it, rather than showing it.
- **Timing depends on the cut.** Tracks built for one file version are re-aligned to another from dialogue; if alignment fails, the track says so.

---

## Roadmap items

| ID | Item | Depends on |
|----|------|------------|
| TRK-001 | Track + cue schema, storage, validation (sources, ceiling, duration) | TML-001 |
| TRK-002 | Moments track generation (curator, on request) | TRK-001, TML-002, PERF-011 |
| TRK-003 | Track delivery on sessions (cue events on the realtime channel) | TRK-001, SES-004 |
| TRK-004 | Booth Notes editions (Mix × Heat), persona voice, riff/fact separation | TRK-002, PERF-011, PRIV-007, PRIV-025 |
| TRK-005 | Trusted public sources (owner setting, allowlist, server-side fetch, citation). Ship PRIV-026 “what leaves this server” panel the same day | TRK-004, SEC-013 |
| TRK-006 | Class / Study lessons from syllabus walks, placed on the timeline | TRK-002 |
| TRK-007 | Detours (library clip sessions, bridge card, exact return) | TRK-006, ENG-003 |
| TRK-008 | “Your edition is ready” Inbox + push notifications (one badge count: UX-007 / PRD-009) | TRK-002, EXP-009 |
| TRK-009 | Series studies spanning episodes | TRK-006, TML-007 |
| TRK-010 | Web overlay renderer (element fullscreen) | TRK-003, ENG-007 |

## See also

- [TIMELINE.md](TIMELINE.md) — the time-coded layer cues sit on
- [SHARED_SESSIONS.md](SHARED_SESSIONS.md) — who sets the level, and how cues reach devices
- [PRIVACY.md](PRIVACY.md) — what leaves the box (public sources stay an owner opt-in)
