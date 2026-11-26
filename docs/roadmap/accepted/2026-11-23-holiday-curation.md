# Drop: holiday shelves — fix the curator, give it a theme and reasons, one admin page

**From:** Will (via design chat) · **Date:** 2026-11-23 · **Type:** bug + rework · **Reference:** design canvas board `WebHolidays` and its sticky

## 1. Bug: "Ask the professor to curate" never reaches the curator (fix first)

`projectionist/library/seasonal_curation.py` builds the system prompt with `_SYSTEM_PROMPT.format(limit=capped)`. The prompt contains example JSON (`{"picks":[…]}`), so `.format()` raises `KeyError('"picks"')`. `holidays_routes.py` maps any `KeyError` to a 404 whose detail is the key name, so the owner sees a one-word "picks". No LLM call happens, and the shelf stays a raw keyword dump with empty notes.

**Fix:**
- Build the prompt without `str.format` on text that contains braces (use `.replace("{limit}", …)` or escape the braces).
- Only map a *missing holiday* to 404. Any other error is a 502 with a plain message.
- Test: a propose call reaches the (mocked) LLM, and a non-holiday `KeyError` doesn't come back as 404.

## 2. Picks with a theme and real reasons (accepted)

**Why today's picks are weak:**
- The candidates are substring matches on broad terms ("winter", "family", "holiday"), cut to the first 48 in database order, so newest arrivals dominate.
- The curator sees only title and year.

**The new approach:**
- **Candidates, scored, not dumped:**
  - *strong signals*: TMDB keywords for the holiday (e.g. christmas, santa claus, christmas eve), the plot set at the holiday, the household watching it in previous seasons;
  - *weak signals*: genre, and broad terms like "winter" or "family", which only count alongside a strong one.
  - Default terms per built-in holiday ship with the server; the owner can add to them.
  - Keep the top ~60 by score, with era variety. Exclude the owner's "not a fit" titles.
- **Give the curator real material, per candidate:** a one-line synopsis, genres, the matching keywords, content rating, runtime, popularity or rating, household views (and in which past seasons), last watched, Youth-safe yes/no.
- **Ask for a theme and a balanced mix**, returned as structured JSON:
  - `theme`: one line, the idea tying this year's shelf together;
  - `picks`: each with `library_item_id`, `role`, `note` (1–2 sentences) and `matched_because`;
  - roles: **Classic**, **Family**, **New this year**, **Deep cut**, **After bedtime** (adult-rated; hidden for Youth automatically).
  - Default mix for 10 picks: about 3 Classic · 3 Family · 1 New this year · 2 Deep cut · 1 After bedtime. The owner can change it.
- **Notes must be grounded:** only facts from the metadata provided and the household's history. No invented trivia, cast facts or quotes. Write in the household's curator persona voice.
- **The owner approves.** The proposal shows as a preview (theme, cards, roles, notes) with Apply / Redo / Cancel. Nothing replaces the shelf until Apply.
- **Notes everywhere:** every pick on Explore shows its note. A pick with an empty note never ships; the curator fills it, or the owner writes one.
- Store the theme with the shelf and show it on the Explore rail header ("Christmas — [theme]").

## 3. One admin page: Holidays & seasons (accepted)

Holiday settings live today in Admin → Holidays (the observance editor) **and** Admin → Live (seasonal shelves with picks). Merge them into **Admin → Experience → Holidays & seasons**:
- **Left:** every observance with its state (On Explore now / Coming up / Off), plus "Add your own".
- **Right:** the selected holiday, with an on/off switch and a summary line (dates on Explore, shelf size, Live block), and four tabs:
  - **The shelf:** the theme banner with the mix, *Ask the curator to redo*, and the pick cards (drag to reorder, role chip, note, "why it matched", Edit note, Not a fit), plus *Add a title from the library*;
  - **Dates:** grounding day, kind (fixed / movable), days before and after;
  - **On Live:** holiday programming for Live channels;
  - **Matching:** keyword terms (advanced).
- **Admin → Live** keeps channel settings only and links here for holiday shelves.
- Remove the stray "Hidden from this rail." line at the top of today's Holidays page, or replace it with a clear state message.

## Done when

- *Ask the curator* on Christmas returns a theme and 10 picks with roles, notes and reasons, every id from the library and none of the weak-only matches. The owner previews, then applies.
- Explore shows the theme and the notes.
- Youth profiles don't see After bedtime picks.
- There's one admin page for holidays, the Live page links to it, and old URLs redirect.
- Tests: the prompt builds, the candidate scoring prefers keyword and plot matches over weak terms, the JSON schema is validated, and the role mix is respected.

## Processing note

- Section 1 (the prompt-format bug and the error mapping) already merged as pull request 317 and is in tag `v1.46.0` (`4c36a9ad`). Not redone here.
- Sections 2 and 3 are EXP-020, in this change. Capability `holiday_shelves`. Not in the 1.46.1 image. Held until tag `v1.46.1` exists.
- Outbox: `docs/roadmap/outbox/2026-11-24-EXP-020-holiday-shelves.md` (platform fields only).
---
## Processing note (agent, 2026-11-26)
- Updated: EXP-020 is done. Section 1 merged as pull request 317 and is in tag `v1.46.1`. Sections 2 and 3 merged as pull request 326, `a452fb37`. They are in the 1.46.2 image on Docker Hub. Production is 1.45.5.
- Outbox: `docs/roadmap/outbox/2026-11-24-EXP-020-holiday-shelves.md` (already filed).
- Needs the person: nothing.
