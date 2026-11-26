# Drop: where to watch — streaming availability for the household's services

**From:** Will (via design chat) · **Date:** 2026-11-25 · **Items:** new EXP item(s), next free numbers

## Why

When a title isn't in the collection, the curator should still help: "Not in your collection, but it's on your Apple TV+ subscription." Title pages show where a title streams, for the services the household actually has.

## Decisions (accepted)

1. **Data source: TMDB watch providers** (`/movie/{id}/watch/providers`, `/tv/{id}/watch/providers`, the provider lists), per region.
   - TMDB's terms require **JustWatch attribution** wherever this data is shown. Show "Streaming data from JustWatch" beside every availability block, plus the TMDB attribution in About.
   - TMDB gives a link to its own watch page for the title, **not** deep links into each service's app. Use that link ("See where to watch"), or the provider's own search page where that's a plain public URL. Don't scrape for deep links.
   - Cache per title and region with a TTL (about 24 h); refresh lazily. Lookups use TMDB ids already known; no new personal data leaves the server.
2. **Subscriptions are tags, not linked accounts:**
   - the owner sets the household's services (Settings → Household → Where you watch), and members can add their own;
   - pick from the region's provider list, with logos from TMDB;
   - stored locally only.
3. **Linking the streaming accounts themselves is not in scope:** sign-in, link-to-play, pulling history.
   - Most services have no public API for watch history or playback, and scraping or automating them is fragile and usually against their terms.
   - **If external history is ever wanted, use Trakt** (an optional, owner-enabled integration later). Trakt gathers watch history from many services through its own apps and has a real API. Record this as a future item, not now.
4. **Where it shows:**
   - **Title page:** "Where to watch" with the household's services first (logo + Stream / Rent / Buy), then others collapsed. For titles in the library, the library Play stays primary and streaming appears as a quiet secondary line.
   - **Curator (chat + agents):** a `where_to_watch` tool returning availability filtered to the household's (and the member's) services. The curator may say "not in your collection, but on [service] (you have it)". If Seerr is enabled, it also offers "or request it for the collection".
   - **Search results** for titles not in the library: a small "On [service]" chip when it's on one of the household's services.
   - Explore stays library-first, with no streaming rails by default.
5. **Region:** follows the household's country setting (the same one weather and news use); a member can override it.
6. **Youth:** availability respects the member's rating ceiling (no suggestions above it).

## Done when

- The owner picks services, and a title not in the library shows where it streams, with the JustWatch attribution.
- The curator answers "where can I watch [title]?" using only real provider data filtered to the household's services, and offers Seerr when enabled.
- Cached, with tests for attribution present, region handling, Youth filtering, and no deep-link fabrication.
---
## Processing note (agent, 2026-11-26)
- Created: EXP-023 (accepted; starts when the front-door lane finishes), EXP-024 (proposed; not now).
- The parked line about an external "on Netflix" lookup stays parked as scraping or a deep link. EXP-023 is the accepted replacement: TMDB watch providers, JustWatch attribution, and the server's link only.
- Outbox: `docs/roadmap/outbox/2026-11-26-EXP-023-where-to-watch.md`.
- Needs the person: nothing.
