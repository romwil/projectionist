# Drop: era order — Jellyfin before launch, three lanes, launch last

**From:** Will (via design chat) · **Date:** 2026-11-21 · **Type:** sequencing decisions (no new items)

Record these on the board's Decisions table and in the *Sequencing* section:

1. **Jellyfin support (ENG-010) comes before any public community launch.** It follows the playback work (ENG-012, ENG-013, ENG-005, ENG-014). It also covers the Jellyfin side of the source-transcode tier (ENG-013).
2. **Three lanes run in parallel:**
   - **engine** (ENG playback tiers, then ENG-010);
   - **Apple clients** (client repo);
   - **server for sessions** (SES-001…009, then TML, then TRK).

   NAT items thread through as each capability ships, as before.
3. **The public community launch is the last milestone, with no date.** Launch work (install template, hardware passthrough docs, first-run onboarding, privacy statement, security review) is written up when we get there.

The plain-language milestone view lives in the private program workspace's roadmap page. Don't copy client plans into this repo; record platform order only.

---

## Processing note (agent, 2026-11-21)

- Created: none. This drop is sequencing only
- Updated: board Sequencing and Decisions. ENG-010 stays proposed. It follows ENG-012, ENG-013, ENG-005, and ENG-014, includes the Jellyfin side of ENG-013, and comes before a public community launch. Three lanes run together: the engine, native clients in their own repository, and the server for sessions. The public community launch is last and has no date
- Outbox: none
- Needs the person: nothing
