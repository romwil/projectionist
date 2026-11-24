# The timeline layer

Projectionist knows what a film or episode *is* — credits, motifs, plot, kinship. The timeline layer teaches it **when** things happen inside one: who is speaking, which scene you are in, which moment the curator wants to point at. It is the foundation for curator notes at key moments, for “who was that in the car?”, and for every [track](TRACKS.md).

**Status:** Proposed (design). Item IDs (`TML-…`) are tracked in [docs/roadmap/](roadmap/README.md).
**Audience:** Developers / contributors.
**Related:** [MEDIA_INTELLIGENCE.md](MEDIA_INTELLIGENCE.md) · [CURATOR_KNOWLEDGE.md](CURATOR_KNOWLEDGE.md) · [TRACKS.md](TRACKS.md) · [SHARED_SESSIONS.md](SHARED_SESSIONS.md) · [PLAYBACK_ENGINE.md](PLAYBACK_ENGINE.md)

Jump to: [What it holds](#what-the-layer-holds) · [Sources](#where-the-facts-come-from) · [Model](#data-model) · [Asking about now](#asking-about-now) · [Series](#tv-is-first-class) · [Limits](#honest-limits) · [Items](#roadmap-items)

---

## What the layer holds

For each movie and each episode, a set of **time-coded events**:

| Event kind | Example | Primary source |
|------------|---------|----------------|
| `dialogue` | 0:21:38–0:21:41 one subtitle cue (the line as written) | Household subtitle file |
| `speaker_hint` | that line is likely the lead character | Dialogue + cast/character map + names spoken nearby |
| `scene` | 0:19:52–0:24:10, night, diner | Shot-change detection + dialogue gaps |
| `chapter` | “The Diner” | Chapter markers in the file |
| `marker` | intro, recap, credits | Existing intro/credit detection where present; heuristics otherwise |
| `moment` | the coffee-shop face-off begins | Derived: curator / track generation picks moments over the scene + dialogue layer |

Everything is keyed on the same identity the knowledge graph uses (TMDB / IMDB, plus season/episode), and versioned per **media file**, because a director’s cut and a theatrical cut have different clocks.

---

## Where the facts come from

The layer builds on what Projectionist already has, and stays local.

1. **Dialogue — already cached.** The idle *subtitle enrichment* task keeps one household-language file per title at `DATA_DIR/subtitles/{rating_key}/{language}.srt` (`library/subtitle_cache.py`). Every cue is a timestamped line of dialogue. That is most of the layer for free.
2. **Scenes — from the file.** `ffmpeg`’s scene-change filter (already in the container) over a low-resolution decode gives shot boundaries; dialogue gaps and shot density group shots into scenes. This runs as a background job, off the request loop, once per file.
3. **Who is on screen — conservatively.** Speaker hints come from the cast/character map, names spoken in nearby dialogue, and scene continuity. **Face recognition is out of scope by default** — it is heavy, error-prone, and not the privacy posture this project holds.
4. **Moments — from the curator, on request.** Picking *the* moment (“the face-off begins here”) is a judgment, produced when a track is generated, stored with its reasoning, and attributable.

Provenance is recorded per event (`source`, `confidence`), so the curator can say *“probably the lead — he is named two lines earlier”* rather than assert.

---

## Data model

The fingerprint is the SHA-256 of `size:mtime_ns:duration_ms`. The same numbers are the same file version. `POST /api/library/timeline/files` records it for a title already in the library. The response is the id, the fingerprint, and the duration. It does not include events. `timeline_files` is `1`. `timeline` stays `0` until the asking tool exists.

```sql
-- one row per readable media file version
CREATE TABLE timeline_files (
  id INTEGER PRIMARY KEY,
  rating_key TEXT NOT NULL,          -- source-specific key (Plex today)
  tmdb_id INTEGER, season INTEGER, episode INTEGER,
  file_fingerprint TEXT NOT NULL,    -- size + mtime + duration hash
  duration_ms INTEGER NOT NULL,
  built_at REAL, build_version INTEGER
);

-- time-coded events
CREATE TABLE timeline_events (
  id INTEGER PRIMARY KEY,
  file_id INTEGER NOT NULL REFERENCES timeline_files(id),
  kind TEXT NOT NULL,                -- dialogue | speaker_hint | scene | chapter | marker | moment
  start_ms INTEGER NOT NULL, end_ms INTEGER,
  payload TEXT NOT NULL,             -- JSON: text, character, tmdb_person_id, label…
  source TEXT NOT NULL,              -- subtitle_cache | scene_detect | chapters | curator | …
  confidence REAL
);
CREATE INDEX timeline_events_at ON timeline_events(file_id, start_ms);
```

SQLite with the existing write serializer is enough: a feature film is a few thousand dialogue rows and a few hundred scenes.

---

## Asking about now

The most visible use: a question asked during playback carries **where you are**.

> **You ask, at 1:12:04:** “who was that in the car with Linda?”
>
> **Your curator answers** from the last few minutes of dialogue, the current scene, and the cast map — naming the character and the actor, saying how sure it is, and offering *“jump back to that scene”* on your phone (never on the room’s screen without the session owner).

How it works:

- A chat turn sent from a [shared session](SHARED_SESSIONS.md) includes `session_id` and the playhead.
- A new agent tool, `timeline_context(at_ms, window_ms)`, returns the surrounding dialogue, scene, speaker hints, and chapter — a small, bounded slice. The LLM never receives the whole script, matching the project’s *surgeon, not bulk export* rule ([ARCHITECTURE.md](ARCHITECTURE.md#design-thesis--mcp-over-local-data)).
- **No spoilers by default:** the tool only returns events **at or before** the playhead unless the member asks to look ahead.

---

## TV is first-class

Everything here applies to episodes as well as films:

- Episodes get their own timelines; a **series index** links recurring characters, places, and motifs across episodes so a study of *The Sopranos* can say “this is the third time the ducks appear.”
- Recaps and intros are markers, so tracks and studies skip them unless asked.

---

## Honest limits

- **Subtitles are not perfect transcripts.** Timing drifts on some files; hearing-impaired tracks add sound cues; translations paraphrase. The layer prefers a dialogue track matched to the file (moviehash) and records which one it used.
- **Speaker attribution is a hint,** not a fact. The curator says how sure it is.
- **Scene detection is approximate** around fades, montages, and very dark footage.
- **Builds take time.** Scene detection decodes the whole file at low resolution; a feature film is minutes of CPU on a homelab box. Builds are queued, resumable, and on demand for titles someone is watching or has asked a track for.

---

## Roadmap items

| ID | Item | Depends on |
|----|------|------------|
| TML-001 | Timeline schema + per-file fingerprinting (done: `timeline_files` is 1) | — |
| TML-002 | Dialogue import from the household subtitle cache | TML-001 |
| TML-003 | Scene / shot detection job (jobs engine, resumable) | TML-001 |
| TML-004 | Speaker hints from cast map + spoken names | TML-002 |
| TML-005 | `timeline_context` agent tool + spoiler guard | TML-002 |
| TML-006 | Chat turns carry session context (`session_id`, playhead). Youth LLM routing / memory defaults (PRIV-007, PRIV-025) must exist before notes reach Youth sessions | TML-005, SES-003, PRIV-007, PRIV-025 |
| TML-007 | Series index (recurring characters / places / motifs across episodes) | TML-002 |
| TML-008 | Owner coverage view (Admin → Library knowledge gains a timeline column) | TML-002 |

## See also

- [TRACKS.md](TRACKS.md) — cues and lessons built on this layer
- [MEDIA_INTELLIGENCE.md](MEDIA_INTELLIGENCE.md) — the title-level knowledge this layer extends inward
