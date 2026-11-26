# Platform handoff: where to watch

**Date:** 2026-11-26 · **Server item:** EXP-023 · **Client item waiting:** APL-066

## What the platform will offer

*Proposed* capability `where_to_watch` is `1` when a title can return provider rows. The server uses TMDB watch providers for the household region, cached for about a day. It does not scrape a streaming service and it does not invent a deep link.

A title payload that includes availability names:

- the household's services first, then the others
- the offer: stream, rent, or buy
- the link the server already has (TMDB's watch page, or a provider search page that is a plain public URL)
- a JustWatch attribution string that the client must show beside the block

Youth responses omit providers above that member's ceiling. Library titles keep Play as the primary action. Explore does not grow a streaming rail from this item.

Service choices are local tags. They are not linked accounts. Optional Trakt history is EXP-024 and is not part of this handoff.

## When

This starts after the front-door lane finishes. The client waits until the capability is on a released server.

## Privacy

Lookups use TMDB ids the server already stores. A member's watch history is not sent to TMDB.
