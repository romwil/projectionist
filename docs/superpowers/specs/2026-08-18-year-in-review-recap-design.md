# Year in Review recap — Design Spec

**Status:** Accepted  
**Date:** 2026-08-18  
**Document ID:** SPEC-2026-YIR-002  
**Depends on:** [Year in Review v1](2026-08-02-year-in-review-design.md)

---

## 1. Purpose

v1 shipped a guided cinema reel whose copy is gentle and forgettable — no hero totals, no movie vs TV genres, nothing screenshot-worthy. This spec turns YIR into a **hybrid**: a short punchy reel, then a **linger recap** with Letterboxd/Spotify-style numbers, still strictly from *your* tracked finishes.

---

## 2. Locked decisions

| Decision | Choice |
|----------|--------|
| Shape | Hybrid: punchy reel, then a scrollable recap sheet |
| Data | Extend year rollup + first-class `recap` object on the snapshot (`schema_version` 3) |
| Copy | Templated, no LLM |
| Honesty | Per-user completions only; hours labeled as **catalog runtime**, not live progress; rewatch only when finishes land on ≥2 distinct days |
| Tease | First ~3 reel chapters only; recap sheet is **ready** status |
| Sharing | Copy recap / copy beat; still no public secret URLs |

---

## 3. Recap payload

Built from the year rollup. Omit a beat when the underlying data is missing.

| Beat | Fields |
|------|--------|
| Headline | Personality line from movie + TV genre crowns |
| Hero | Movies finished, unique episodes, unique shows, catalog hours (when runtime exists) |
| Movie genre / TV genre | Crown name + count + runner-up |
| Top 5 movies / shows | Existing ranked titles + posters |
| Peak month | Label, count, highlight titles |
| Rewatch | Only `distinct_days >= 2` |
| Fun extras | Busiest weekday, most-seen director/actor, median movie decade |
| Honesty | Footnote + hours coverage note |

Hours = sum of `library_items.runtime_minutes` (movies) and `library_episodes.runtime_minutes` (episodes) for attributed finishes. Never invent from household `view_count`.

---

## 4. Reel chapters

Core (skip empties): overture with a hero number → totals → movie genre → TV genre → movies → TV binge → busy month.

Optional when signals exist: ratings, shares, Live.

Honesty and “lights up” **leave the reel**; they live on the recap.

Hard cap remains 12 chapters.

---

## 5. Frontend

`/year-in-review/:year` keeps the reel player. After the last chapter (Next, or auto-advance), land on the recap sheet. Recap is scrollable, with hero grid, genre crowns, poster rows, a simple month chart, extras, honesty footnote, and **Copy recap**. Back returns to the reel.

`prefers-reduced-motion` still disables auto-advance.

---

## 6. Tests & docs

- Rollup: genres, hours, weekday, credits from library joins; empty scan still honest.
- Recap builder: omit missing beats; personality line; hours note.
- Chapters: punchy copy; no honesty/closing chapters when recap exists.
- Snapshot includes `recap` at schema 3.
- Frontend helpers for recap share text + recap navigation.
- HELP member copy mentions totals, genres, and the recap sheet.

---

## 7. Out of scope

- LLM copy, public share URLs, household aggregates, live-progress hours, Instagram image export (clipboard text is enough).
