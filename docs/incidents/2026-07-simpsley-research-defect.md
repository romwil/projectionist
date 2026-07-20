# Simpsley research defect — 2026-07

## Verified record

`Simpsley` (2026) is a 24-minute animated Simpsons special, not a bad local
match or fan-content guess. Plex rating key `227463` and TMDB ID `1725116`
agree on the title, date, cast, production companies, and placement in *The
Simpsons (TV Specials) Collection*. The local media path is intentionally not
recorded here: chat and privacy-safe tool responses never expose owner storage
paths.

TMDB’s exact-ID response includes the full Italy con-artist synopsis, the
tagline “A Simpsons noir? We’re in.”, cast including Dan Castellaneta and Julie
Kavner, director Debbie Bruce Mahan, writer Cesar Mazariegos, and IMDb ID
`tt43140642`. Its `Simpsley` title search has one result; `Simpsons` is broad
and returns many unrelated specials and films.

## Failure and remediation

The chat preflight sent the full conversational sentence
`how about simpsley? 2026?` to library search. Exact `Simpsley` succeeds, but
that sentence did not. The agent then treated a compact local card as if it
were all available metadata, inferred a stub, and incorrectly claimed it
could not research online.

Release 1.8.28 extracts conservative title candidates from conversational
queries and adds `research_title`. The tool uses configured official JSON APIs
(TMDB and Wikipedia; optional OMDb/TVDB), returns source provenance and gaps,
and is explicitly not arbitrary web browsing.
