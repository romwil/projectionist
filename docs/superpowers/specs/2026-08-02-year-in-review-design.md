# Year in Review — Design Spec

**Status:** Accepted  
**Date:** 2026-08-02  
**Document ID:** SPEC-2026-YIR-001  
**Audience:** Developers / Cursor agents  
**Depends on:** [Watch Tracker plan](../plans/2026-08-03-watch-tracker.md) (per-user sessions/completions; never household `view_count`)

---

## 1. Purpose

Year in Review (YIR) is a **flexible consumer of the watch tracker**: a private, opt-in, cinema-reel experience that tells each mapped member a warm story about *their* year of watching — not a household stats dashboard and not an LLM essay.

Projectionist precomputes a **versioned JSON reel snapshot** per `(user_id, year)` from tracker rollups, delivers an inbox/email deep link, and plays an adaptive guided reel at `/year-in-review/:year`.

---

## 2. Locked product decisions

| Decision | Choice |
|----------|--------|
| Architecture | Snapshot program — versioned JSON reel from tracker rollups; auth-gated `/year-in-review/:year` |
| Copy | Templated poetic voice (Fraunces + amber); **no LLM required for v1** |
| UX | Guided cinema reel (auto-advance + pause, ambient CSS motion, `prefers-reduced-motion`); playful/warm, not stuffy |
| Audience | Opt-in (`year_in_review_opt_in`); mapped Plex identity; enough tracker data; **guests skipped** |
| Chapters | Adaptive registry — watch-life core always when data exists; social/curator beats only when signals exist; ~10–12 cap; skip empty placeholders |
| Schedule | Late Dec soft tease + early Jan full drop for prior calendar year; owner admin generate/send (self) for testing |
| Sharing | Private reel + optional share cards (download/copy beat image); **no public secret URLs in v1** |
| Delivery | Inbox kind `year-in-review` + email if configured; reuse `deliver_notification` / newsletter patterns |
| Honesty | Confidence vocabulary from watch tracker — never claim unverified rewatches or invent history from household aggregates |

---

## 3. Watch-tracker dependency

YIR **must not** invent per-user history from Plex library `view_count` / household sync aggregates.

Minimum tracker surface for YIR v1:

1. Append-only `watch_events` with exact Plex-account → `user_id` mapping (unmapped stay isolated).
2. Derived `watch_sessions` / `watch_completions` with confidence (`certain` / `likely` / `plex_event_only`).
3. Year-scoped rollup API: completions, sittings, top titles, media mix, monthly rhythm — **scoped to `user_id`**.

Ingest sources for v1 foundation: Plex history poll (durable backfill) + webhook observations (live). Correlation materializes sessions/completions. Tautulli and full agent/UI adoption remain out of YIR’s critical path.

---

## 4. Data model

### `year_in_review_snapshots`

```sql
CREATE TABLE year_in_review_snapshots (
    user_id TEXT NOT NULL,
    year INTEGER NOT NULL,
    schema_version INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('ready', 'tease', 'empty', 'error')),
    reel_json TEXT NOT NULL,
    generated_at REAL NOT NULL,
    notified_at REAL,
    PRIMARY KEY (user_id, year),
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
```

`reel_json` is the full chapter list + meta (counts, honesty footnotes, share-card payloads). Regenerating overwrites the row for that `(user_id, year)` at the current `schema_version`.

### User preference

`users.year_in_review_opt_in INTEGER NOT NULL DEFAULT 0` — same pattern as `newsletter_opt_in` / `nudge_opt_in`.

### Notification kind

`year-in-review` added to `NOTIFICATION_KINDS` and the `user_notifications.kind` CHECK (migration).

---

## 5. Reel / chapter contract

```json
{
  "schema_version": 1,
  "year": 2025,
  "user_id": "…",
  "display_name": "Will",
  "status": "ready",
  "honesty": {
    "footnote": "These chapters use Projectionist's tracked completions for you — not household Plex totals.",
    "confidence_note": "Some finishes are reconstructed from Plex history when progress wasn't observed live."
  },
  "chapters": [
    {
      "id": "overture",
      "kind": "overture",
      "title": "Your year on the screen",
      "body": "…",
      "stat_lines": [],
      "posters": [],
      "shareable": true,
      "duration_ms": 5500
    }
  ]
}
```

### Chapter registry (plugin style)

Builders live under `projectionist/year_in_review/chapters/` and register into an ordered list. Each builder:

- receives `YearRollup` + optional social signals;
- returns `None` / empty to skip;
- never invents placeholders.

**Core (when rollup has data):** overture, volume, top movies, TV depth, monthly rhythm, confidence/honesty coda, closing.

**Optional (when signals exist):** ratings highlights, shares given/received, Live channel beats, curator/persona shout-out.

Hard cap **12** chapters after filtering empties.

---

## 6. APIs

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| `GET` | `/api/year-in-review/{year}` | Signed-in non-guest; own reel only | Return snapshot reel (404 if missing/empty/not opted when required for drop) |
| `POST` | `/api/admin/year-in-review/generate` | Owner | Generate (and optionally notify) scoped like weekly newsletter — **v1: `self` only** |
| `GET` | `/api/admin/watch-tracker/status` | Owner | Tracker health (no title leakage) |

Member access: must be authenticated, role ≠ guest, and the snapshot must be for `current_user.id`. Opt-in gates **delivery**; owners may still generate a self reel for testing when opted in.

---

## 7. Schedule & delivery

| Task | When | Behavior |
|------|------|----------|
| `year_in_review_tease` | Late Dec (calendar window) | Soft inbox nudge for opted-in mapped members with enough prior-year tracker signal; status may be `tease` |
| `year_in_review_drop` | Early Jan | Generate `ready` snapshots + deliver inbox/email deep link `/year-in-review/{year}` |

Delivery reuses `deliver_notification(..., kind="year-in-review", …)` with payload `{ "year", "path" }`. Email body includes the deep link when mail is configured.

Guests never generate or receive YIR.

---

## 8. Frontend

- Route: `/year-in-review/:year` behind `useAuthGate`.
- Cinema reel player: CSS keyframes only (**no framer-motion**); auto-advance with pause; progress dots; skip empty.
- Tokens: Fraunces + amber from `01-tokens.css`; ambient motion respects `prefers-reduced-motion`.
- Share card: canvas/DOM capture of current beat → download PNG / copy image when supported — no public URL.
- Settings → Notifications: Year in Review opt-in toggle.
- Admin → Newsletters (or Settings → Notifications): Generate my Year in Review (mirror weekly newsletter self scope).
- Inbox: deep-link CTA for `year-in-review` kind.

---

## 9. Honesty & privacy

- Copy distinguishes tracked completions vs Plex-played-only events.
- Never merge household users.
- No public share links in v1.
- Export/delete: snapshots included with user deletion (`ON DELETE CASCADE`).
- Raw watch events remain in the tracker privacy boundary (see watch-tracker plan / PRIVACY).

---

## 10. Out of scope (v1)

- LLM-authored chapters
- Public secret URLs
- Multi-member admin blast beyond self (can extend later like newsletter scopes)
- Tautulli-required correctness
- Reinterpreting historical household `view_count` as personal YIR evidence

---

## 11. Success criteria

- Opted-in owner can generate a self reel from tracker fixtures and play it at `/year-in-review/{year}`.
- Empty / guest / other-user access fail closed.
- Chapters adapt: social beats absent when no signals.
- Pytest covers rollup → snapshot → delivery; frontend unit tests cover reel player helpers.
- HELP + CHANGELOG Highlights document the member benefit without claiming unverified rewatches.
