# Drop: reasons people believe, and a weekly letter worth opening

**From:** Will (via design chat) · **Date:** 2026-11-26 · **Type:** quality bug + redesign · **Reference:** canvas board `EmailWeeklyLetter` + sticky

## The bug (fix first)

For you, the inbox and the newsletter all use `recommendation_reasons.watched_bridge` → `plot_kinship.member_facing_why`. When the only link is a **shared plot phrase**, it prints "They share {phrase}". Real output on production:
- "You watched Beetlejuice (1988); Saving Private Ryan (1998) — they share video games."
- "You finished an episode of Family Guy (1999); Madden (2026) — they share a super bowl."
- "…they share a small town" / "…commercial" / "…a live variety".

Those are incidental n-grams, not reasons. The sentence frame ("You watched X; Y — they share Z") is also awkward.

## Decisions (accepted)

1. **Link types, ranked; use the strongest available:**
   1. Same series or collection (sequel, prequel, franchise), or next episode/season.
   2. Shared director or writer (named).
   3. Shared lead cast (named, top-billed only).
   4. The member's own behavior (rewatched X twice, finished the whole run of Y, a holiday shelf they opened).
   5. Era + genre + tone together ("from the late-'80s comedy run you've been on") only when all three hold.
   6. **A theme link only from a curated theme vocabulary** (heist, road trip, coming of age, time loop, courtroom, small-town mystery, …) matched with confidence on *both* titles (TMDB keywords mapped to themes, or an LLM theme tag stored per title and validated). **Raw plot n-grams never produce a sentence.**
   7. **No good link → no reason sentence.** Show the pick without a why rather than a bad one.
2. **Sentences in the curator's voice, built from the link, never from free n-grams:**
   - "Same director as *Heat* — Michael Mann, fifteen years earlier."
   - "You've watched *X* twice; this is where the story goes next."
   - Optional LLM polish **only** from the structured link facts (the model may rephrase, not add facts). Validated: names and titles in the output must come from the facts given; fall back to the template on any mismatch. Cached per (seed, pick, persona).
3. **Tests:** a golden list of bad pairs from production (above) must produce **no** "share" sentence. Good pairs produce the right link type. A lint check rejects any reason containing a phrase not traceable to a link fact.
4. **Applies to** For you, the inbox, nudges, whispers and the newsletter. One builder, fixed once.

## The weekly letter (redesign)

- **HTML email** (with a text alternative), 600 px, the Lights Down look; renders well in Gmail, Apple Mail and Outlook (table-based layout where needed).
- **Posters embedded as inline attachments** (`multipart/related`, CID), small JPEGs about 30–60 KB each, total under ~1 MB. **Nothing loads from the server**, so it works behind Cloudflare Access and leaks nothing on open (no tracking pixels).
- **Sections** (each omitted when empty):
  1. Greeting + a curator opener (persona voice, grounded in the reader's actual week; LLM with the same fact validation, template fallback)
  2. Tonight's pick (poster, facts, reason, a "Play in Projectionist" link)
  3. More for you (3, with reasons)
  4. Pick up where you left off
  5. New in the collection (5 posters + a count)
  6. The season's shelf (holiday theme, when active)
  7. On Live this week
  8. **For the owner only:** household health (from the exposure card and Doctor), members without a second factor, an available update
- **Links** go to the front door (`/title/...`), which opens the app when installed (universal link later) or the web behind the household's gate. Not "open Projectionist on your home network".
- **Per-member:** their own history, their Youth ceiling, the persona, the language; no other member's viewing.
- **Preview:** Settings → Notifications → "Preview this week's letter" renders it in the browser and can send a test to yourself.

## Done when

- The golden bad pairs give no "share" sentences on For you, the inbox and the letter.
- The letter arrives with inline posters in Gmail and Apple Mail, owner and member versions are correct, the Youth version respects the ceiling, and the preview works.
- Tests cover CID embedding, size limits, empty sections and fact validation.
---
## Processing note (agent, 2026-11-26)
- Created: EXP-021 (accepted; a small priority change for the next playback release), EXP-022 (accepted; follows that release).
- Clients already show the server's reason sentence. No new client route.
- Outbox: none.
- Needs the person: nothing. This filing does not build the feature.
