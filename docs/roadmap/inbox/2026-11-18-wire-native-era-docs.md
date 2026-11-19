# Wire the new platform docs into the existing ones

Dropped 2026-11-18 alongside the new docs (PLAYBACK_ENGINE, SHARED_SESSIONS, TIMELINE, TRACKS, NATIVE_CLIENTS, roadmap board). They were added as new files only, because the local working tree was being brought up to date with 1.40.1 at the time, and editing existing docs would have collided.

Once `main` is current, link them in:

- `README.md` — mention the playback engine direction in Key capabilities (as *planned*, not shipped) and add the new docs to the docs list.
- `docs/PRODUCT.md` — add the era to *Sequenced priorities (post-1.40)*: engine → sessions → timeline → tracks, with the board as the source of truth. Add Booth Notes and Class / Study to the surface map as *planned*. Note that Live’s PRD-007 freeze still holds (ENG-009 changes the stream under existing stations only).
- `docs/ARCHITECTURE.md` — a short “Playback engine (planned)” section under Component architecture linking PLAYBACK_ENGINE.md, and the timeline layer under Library and RAG.
- `docs/MEDIA_INTELLIGENCE.md` — *Next horizon* gains the timeline layer (TML) as the inward extension of title knowledge.
- `docs/PRIVACY.md` — nothing changes yet; when TRK-005 or NAT-006 is accepted, add the public-sources opt-in and the content-free push relay to the data map.
- `.gitignore` — nothing needed.

Not new roadmap items; a docs chore. Process it as such.
