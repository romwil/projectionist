# Watch Tracker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a per-Plex-user watch ledger that turns durable Plex history and live progress observations into conservative logical viewings and completion counts, without claiming that Plex can prove uninterrupted viewing.

**Architecture:** Keep Plex aggregates as compatibility metadata, but add an append-only observation layer, deterministic correlation, and derived `watch_sessions` / `watch_completions`. History, webhook, live-session, manual-scrobble, and optional Tautulli adapters all normalize into the same event contract; agents and UI consume only user-scoped derived summaries with explicit confidence.

**Tech Stack:** Python 3.12, FastAPI, SQLite/WAL, existing `PlexClient`, existing Plex webhook route, optional `TautulliClient`, idle scheduler, React, pytest, frontend unit tests.

## Global Constraints

- Never describe Plex `viewCount`, a history row, or a scrobble by itself as a verified full rewatch.
- “Certain” means the tracker directly observed a completion threshold crossing; it does **not** mean uninterrupted viewing was proven.
- Every observation and derived viewing is scoped to a Plex identity. Never merge two users, and never expose one user’s watch activity to another.
- Existing library aggregates remain available during migration; no destructive backfill or reinterpretation of old `view_count` values.
- Movies and episodes are correlation units. A TV show is a rollup of episode completions, never a single playable session.
- Ingestion must be idempotent, resumable, bounded, and safe under overlapping webhook/scheduler writes.
- Tautulli remains optional. Core correctness cannot depend on it.
- Raw payload retention is minimized: store normalized fields and a payload hash, not tokens, IP addresses, or full webhook/history payloads.
- All confidence and dedupe decisions must be reproducible from persisted evidence and an algorithm version.

---

## 1. Owner outcome and honest product contract

Projectionist should answer:

- “How many logical times did I finish this movie, according to the evidence Projectionist observed?”
- “Did I finish this episode, and when?”
- “Was that one viewing over several sittings?”
- “Why does Projectionist think this was a completion?”
- “Is this count based on observed progress, a plausible history event, or only Plex’s played event?”

Projectionist must still answer “I cannot prove it” when asked whether a viewing was uninterrupted, attentive, or watched by the person whose Plex profile was active. Plex reports server/client events, not human attention.

### Confidence vocabulary

| Level | Product meaning | Minimum evidence |
|---|---|---|
| `certain` | Projectionist directly observed one logical viewing cross its completion boundary. Not proof of uninterrupted or attentive viewing. | Same user/title logical session has progress below threshold and later at/above threshold, or a trusted credits/completion transition, with no dedupe conflict. |
| `likely` | Evidence strongly supports one completion, but the threshold crossing was reconstructed rather than directly observed. | A history completion linked to a plausible session, or monotonic progress ending near completion with a terminal stop/history event. |
| `plex_event_only` | Plex emitted a played/scrobble/history event, but Projectionist lacks enough progress evidence to call it a reconstructed viewing. | A unique Plex played event with mapped user/title, after duplicate suppression. |

The UI may say “2 tracked completions” and show confidence. It must not flatten these into “watched twice” without qualification.

---

## 2. Repository survey — current behavior and reusable seams

| Area | Current behavior | Tracker implication |
|---|---|---|
| Plex metadata sync | `projectionist/connectors/plex.py` parses movie/show/episode `viewCount`, `viewOffset`, and `lastViewedAt`. `projectionist/library/sync.py` writes those aggregates during library and episode sync. | Useful compatibility snapshot, not event history. The household server token also cannot represent every member’s personal state. |
| SQLite library model | `library_items` stores title-level `view_count` / `last_viewed_at`; later migrations add `view_offset_ms` / `duration_ms`. `library_episodes` stores episode `view_count`, `last_viewed_at`, `view_offset_ms`, and `duration_ms`. | Do not overload either table with event rows. Add a separate watch domain linked by `rating_key` and optional local item IDs. |
| Play counts | `projectionist/library/play_counts.py` uses movie `view_count`; for shows it sums episode `view_count`. It already labels movie counts as completed-or-marked-played and leaves `play_sessions` unknown. | Keep this as the Phase 0 fallback. Later prefer tracker summaries only when user-scoped coverage exists. |
| Progress state | `projectionist/library/watch_progress.py` and `frontend/src/lib/watchProgress.js` derive watched/partial/unwatched from aggregate count, playhead, and TV episode totals. | Preserve for cards during rollout. Add a tracker-backed user summary rather than silently changing these global fields. |
| Mark watched | `projectionist/library/watch_state.py` updates local aggregate state and calls `PlexClient.scrobble` / `unscrobble`, preferring the signed-in user’s Plex token and otherwise falling back to the server token. | Emit a normalized manual action observation. A manual mark is `plex_event_only`, never `certain`; unscrobble is a correction event, not deletion of audit history. |
| Plex webhooks | `projectionist/web/webhooks.py` accepts `media.pause`, `media.stop`, and `media.scrobble`, maps `Account.id` through `users.plex_user_id`, computes completion percentage, and currently uses the event only to queue a rating prompt. Unmapped accounts fail closed for prompts. | This is already a Phase 2 event source. Refactor it to persist normalized observations before prompt derivation; continue failing closed for personal UX. |
| Rating prompts | `projectionist/reviews/store.py` scans aggregate progress or optional Tautulli metadata and stores one prompt per `(user_id, rating_key)`. Multi-user library sync does not invent personal ownership. | Trigger prompts from a new completion transition eventually, while keeping current scan fallback until tracker coverage is adequate. |
| Tautulli | The stack already exposes optional Tautulli configuration. `projectionist/connectors/tautulli.py` currently supports libraries, media info, metadata, and never-watched checks; purge scoring and rating prompts use it. It does not ingest Tautulli history. | Tautulli is common enough here to support as an enhanced adapter, but only after the core Plex path. |
| User identity | `users.plex_user_id` maps Plex `Account.id` to Projectionist users; personal Plex tokens may be stored encrypted. Local/OIDC users may have no Plex identity. | `user_id` remains nullable at ingest, but `source_user_key` is mandatory. Unmapped observations remain isolated and are never shown as someone’s personal history. |
| Agent language | Agent tool payloads expose `completed_watches`, `rewatch_count`, `partial`, progress percentage, explicit count semantics, and `play_sessions=None`. The system prompt warns against treating counts as playback sessions. | This is the Phase 0 baseline. Phase 4 introduces new fields rather than changing meanings in place. |
| Scheduler | `projectionist/scheduler/engine.py` runs registered `TaskDefinition` jobs with persisted status and intervals; task modules register from `projectionist/scheduler/tasks/__init__.py`. | Use a small I/O task for history polling. Active-session polling needs a shorter dedicated loop or carefully justified scheduler interval; do not force high-frequency work into long idle cycles without measuring it. |

### Phase 0 status: honesty baseline

Phase 0 is substantially present in `library/play_counts.py`, agent instructions, `docs/HELP.md`, and title/card semantics:

- movie counts are labeled Plex completed-or-marked-played events;
- TV counts are episode `viewCount` sums;
- unfinished playheads remain partial;
- `play_sessions` is explicitly unknown;
- manual marks and duplicate scrobbles are disclosed.

Keep these tests and copy as regression gates throughout later phases. Do not remove the fallback until per-user tracker coverage and migration behavior are proven.

---

## 3. Target data model

Add the watch domain in a focused migration, not to the bootstrap `SCHEMA` alone. Use integer epoch milliseconds for source event times and progress, and `REAL` epoch seconds for local `created_at` / `updated_at` to match current conventions.

### `watch_ingest_cursors`

One cursor per source and Plex server.

```sql
CREATE TABLE watch_ingest_cursors (
    source TEXT NOT NULL,
    server_machine_id TEXT NOT NULL,
    cursor_value TEXT,
    high_watermark_ms INTEGER,
    last_success_at REAL,
    last_error_at REAL,
    last_error TEXT,
    updated_at REAL NOT NULL,
    PRIMARY KEY (source, server_machine_id)
);
```

`cursor_value` stores opaque paging/cursor state if a provider offers one. `high_watermark_ms` supports overlap-window replay when it does not.

### `watch_source_identities`

Explicitly maps provider identities without guessing by display name.

```sql
CREATE TABLE watch_source_identities (
    source TEXT NOT NULL,
    server_machine_id TEXT NOT NULL,
    source_user_key TEXT NOT NULL,
    user_id TEXT,
    display_name TEXT,
    mapping_method TEXT NOT NULL DEFAULT 'unmapped',
    first_seen_at REAL NOT NULL,
    last_seen_at REAL NOT NULL,
    PRIMARY KEY (source, server_machine_id, source_user_key),
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
);
```

For Plex, auto-map only exact `Account.id == users.plex_user_id`. For Tautulli, map through its stable Plex user/account identifier when available; never auto-map username text alone.

### `watch_events`

Append-only normalized evidence. This table is the durable boundary between connectors and correlation.

```sql
CREATE TABLE watch_events (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    source_event_id TEXT,
    source_event_kind TEXT NOT NULL,
    server_machine_id TEXT NOT NULL,
    source_user_key TEXT NOT NULL,
    user_id TEXT,
    rating_key TEXT NOT NULL,
    parent_rating_key TEXT,
    media_type TEXT NOT NULL CHECK (media_type IN ('movie', 'episode')),
    occurred_at_ms INTEGER NOT NULL,
    client_key TEXT,
    session_key TEXT,
    progress_ms INTEGER,
    duration_ms INTEGER,
    completion_pct REAL,
    terminal INTEGER NOT NULL DEFAULT 0,
    manual INTEGER NOT NULL DEFAULT 0,
    payload_hash TEXT NOT NULL,
    duplicate_of_event_id TEXT,
    ingested_at REAL NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL,
    FOREIGN KEY(duplicate_of_event_id) REFERENCES watch_events(id) ON DELETE SET NULL
);
CREATE UNIQUE INDEX idx_watch_events_source_id
    ON watch_events(source, server_machine_id, source_event_id)
    WHERE source_event_id IS NOT NULL;
CREATE UNIQUE INDEX idx_watch_events_fingerprint
    ON watch_events(source, server_machine_id, payload_hash);
CREATE INDEX idx_watch_events_correlation
    ON watch_events(source_user_key, rating_key, occurred_at_ms);
CREATE INDEX idx_watch_events_user_time
    ON watch_events(user_id, occurred_at_ms DESC);
```

Allowed `source_event_kind` values begin with:

- `history_played`
- `session_progress`
- `session_pause`
- `session_stop`
- `plex_scrobble`
- `manual_scrobble`
- `manual_unscrobble`
- `tautulli_history`

`payload_hash` is a deterministic SHA-256 over normalized identity/title/time/progress fields, not the raw payload. Preserve duplicates as rows only when they provide new evidence; otherwise use the unique fingerprint and count the no-op in task metrics.

### `watch_sessions`

A derived logical viewing attempt. It may contain several pause/resume sittings and several clients, but only under conservative merge rules.

```sql
CREATE TABLE watch_sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT,
    source_user_key TEXT NOT NULL,
    rating_key TEXT NOT NULL,
    parent_rating_key TEXT,
    media_type TEXT NOT NULL CHECK (media_type IN ('movie', 'episode')),
    started_at_ms INTEGER NOT NULL,
    ended_at_ms INTEGER,
    start_progress_ms INTEGER,
    max_progress_ms INTEGER,
    duration_ms INTEGER,
    first_event_id TEXT NOT NULL,
    last_event_id TEXT NOT NULL,
    primary_client_key TEXT,
    client_count INTEGER NOT NULL DEFAULT 1,
    event_count INTEGER NOT NULL DEFAULT 1,
    terminal_reason TEXT,
    algorithm_version INTEGER NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL,
    FOREIGN KEY(first_event_id) REFERENCES watch_events(id),
    FOREIGN KEY(last_event_id) REFERENCES watch_events(id)
);
CREATE INDEX idx_watch_sessions_user_title
    ON watch_sessions(user_id, rating_key, started_at_ms DESC);
```

### `watch_session_events`

Keep derivation auditable and rebuildable.

```sql
CREATE TABLE watch_session_events (
    session_id TEXT NOT NULL,
    event_id TEXT NOT NULL UNIQUE,
    ordinal INTEGER NOT NULL,
    PRIMARY KEY(session_id, event_id),
    FOREIGN KEY(session_id) REFERENCES watch_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY(event_id) REFERENCES watch_events(id) ON DELETE CASCADE
);
```

### `watch_completions`

Exactly one accepted completion per logical session. Suppressed played events remain visible through evidence, not inflated into this table.

```sql
CREATE TABLE watch_completions (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL UNIQUE,
    user_id TEXT,
    rating_key TEXT NOT NULL,
    parent_rating_key TEXT,
    media_type TEXT NOT NULL CHECK (media_type IN ('movie', 'episode')),
    completed_at_ms INTEGER NOT NULL,
    confidence TEXT NOT NULL CHECK (
        confidence IN ('certain', 'likely', 'plex_event_only')
    ),
    basis TEXT NOT NULL,
    threshold_pct REAL,
    evidence_event_id TEXT NOT NULL,
    superseded_by_completion_id TEXT,
    algorithm_version INTEGER NOT NULL,
    created_at REAL NOT NULL,
    FOREIGN KEY(session_id) REFERENCES watch_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL,
    FOREIGN KEY(evidence_event_id) REFERENCES watch_events(id),
    FOREIGN KEY(superseded_by_completion_id) REFERENCES watch_completions(id)
);
CREATE INDEX idx_watch_completions_user_title
    ON watch_completions(user_id, rating_key, completed_at_ms DESC);
```

Use `superseded_by_completion_id` for later corrections/rebuilds. Do not hard-delete a completion that an owner may have seen.

---

## 4. Normalized connector contract

Create `projectionist/watch_tracker/models.py`:

```python
@dataclass(frozen=True)
class WatchEventInput:
    source: str
    source_event_id: str | None
    source_event_kind: str
    server_machine_id: str
    source_user_key: str
    rating_key: str
    parent_rating_key: str | None
    media_type: Literal["movie", "episode"]
    occurred_at_ms: int
    client_key: str | None = None
    session_key: str | None = None
    progress_ms: int | None = None
    duration_ms: int | None = None
    terminal: bool = False
    manual: bool = False
```

Create `projectionist/watch_tracker/store.py`:

```python
def ingest_watch_events(
    db: Database,
    events: Sequence[WatchEventInput],
) -> IngestResult:
    """Normalize, map exact identities, fingerprint, and idempotently insert."""

def list_user_watch_summary(
    db: Database,
    *,
    user_id: str,
    rating_key: str,
) -> WatchSummary:
    """Return only this user's accepted tracker-derived state."""
```

Every adapter produces this contract. Correlation code never parses Plex XML, webhooks, or Tautulli JSON directly.

---

## 5. Correlation and duplicate rules

Put constants and pure logic in `projectionist/watch_tracker/correlate.py`. Store `algorithm_version = 1` on every derived row so a future rebuild can coexist with old results.

### 5.1 Session merge rules

Process non-duplicate events ordered by `(source_user_key, rating_key, occurred_at_ms, id)`.

An event joins the current logical session only when all are true:

1. same `server_machine_id`, `source_user_key`, `rating_key`, and playable `media_type`;
2. event is at most **4 hours** after the prior event;
3. progress is monotonic within a tolerance of the larger of **60 seconds** or **2% of duration**, unless the event is only terminal history/scrobble evidence;
4. the current logical session has no accepted completion followed by a clear restart;
5. when both events have `client_key`, they match; a client change merges only when the gap is at most **30 minutes** and progress remains monotonic.

Start a new logical session when any is true:

- gap exceeds 4 hours;
- progress falls by more than the rewind tolerance;
- an earlier completion is followed by progress at or below **15%**;
- the title/episode/user changes;
- evidence is ambiguous across clients and cannot be safely ordered.

This intentionally under-merges rather than inventing one continuous viewing.

### 5.2 Completion rules

The tracker completion threshold is **90%**, separate from the existing **85% near-complete rating prompt** threshold.

Create one `watch_completions` row per session:

- `certain`: observed prior progress below 90% and later progress at/above 90%, or a direct trusted credits transition, with mapped identity and no duplicate conflict.
- `likely`: session has monotonic progress and a terminal history/stop event consistent with completion, but the actual crossing was missed.
- `plex_event_only`: unique scrobble/history played event without enough progress evidence.

An episode completion is attached to the episode `rating_key`; `parent_rating_key` supports show rollups. Never attach a show-level completion to an episode session.

### 5.3 Duplicate suppression

Apply in this order:

1. Provider ID uniqueness: same `(source, server, source_event_id)` is one event.
2. Exact normalized fingerprint: same user/title/kind/time/progress/session fingerprint is one event.
3. Reconnect/scrobble window: played/scrobble events for the same user, title, and client within **120 seconds** are one completion candidate; later rows link to the first as duplicate evidence.
4. Implausible recompletion: after an accepted completion, another played event cannot create a new completion unless there is evidence of a new start at/below 15%, forward progress in a new session, or at least `max(6 hours, 75% of runtime)` elapsed.
5. Cross-source overlap: matching Plex and Tautulli terminal events within **5 minutes** attach to one session/completion. Prefer direct progress evidence over source priority.

Manual `scrobble` may create only `plex_event_only`. `unscrobble` does not erase organic history; it records a correction and supersedes a manual-only completion when the evidence chain identifies it.

### 5.4 Rebuild behavior

`rebuild_watch_derivations(db, user_id=None, since_ms=None, algorithm_version=1)` runs in one bounded transaction per user/time chunk:

- raw `watch_events` are immutable;
- sessions/completions for the selected window are regenerated deterministically;
- previously surfaced rows are superseded when identity changes, not silently deleted;
- fixture replay produces byte-for-byte stable logical results aside from generated IDs/timestamps.

---

## 6. Phased architecture

### Phase 0 — Preserve honesty

Keep current aggregate semantics and add regression tests around agent wording. No tracker fields are implied before evidence exists.

Exit criteria:

- agent cannot call `view_count` a session count;
- TV count remains episode-play sum;
- partial playhead can coexist with earlier Plex completions;
- owner help text states manual/sync/duplicate limitations.

### Phase 1 — Durable Plex history ingest

Add `PlexClient.history(...)` against `/status/sessions/history/all` (or the server-version equivalent discovered by a capability probe), with pagination and fixtures from a supported Plex server. Normalize only fields actually returned by the endpoint; do not assume client/session/progress fields are present.

Ingest a bounded backfill, then poll with an overlap window:

- initial default: latest 90 days or 10,000 rows, whichever comes first;
- incremental: replay from `high_watermark - 10 minutes`;
- page size: 250;
- cursor advances only after the page transaction commits;
- unsupported endpoint or missing user identity reports a task outcome, not a startup failure.

Phase 1 does **not** claim correlated viewings. It delivers a per-user event ledger and source-quality diagnostics.

### Phase 2 — Live progress observations

Refactor the existing Plex webhook handler so supported events are ingested even below the rating-prompt threshold. Derive rating prompts after ingest.

Add active session polling only if needed to fill gaps:

- preferred interval: 60 seconds while sessions exist, 5 minutes while idle;
- poll the Plex active sessions endpoint and emit `session_progress`;
- key by Plex account + session/client + playable rating key;
- do not store IP address, bandwidth, device name beyond a stable local client hash;
- stop polling cleanly when Plex is unavailable.

Plex webhooks should remain the low-cost terminal signal. Polling supplies progress samples; it is not a second completion counter.

### Phase 3 — Correlation and confidence

Materialize `watch_sessions`, `watch_session_events`, and `watch_completions` with the rules above. Run correlation after each ingest batch and support deterministic rebuild.

Provide an owner-only diagnostics endpoint for evidence review and a user-scoped summary API. Do not expose raw source identity keys to members.

### Phase 4 — Agent and UI adoption

Add tracker fields beside legacy fields:

```json
{
  "tracked_completions": 2,
  "completion_confidence": {"certain": 1, "likely": 1, "plex_event_only": 0},
  "logical_viewings": 2,
  "sittings_observed": 4,
  "last_tracked_completion_at": 1785732000000,
  "tracker_coverage": "partial"
}
```

Agent policy:

- prefer `tracked_completions` for the current user when `tracker_coverage != "none"`;
- say “tracked completion” or “Plex played event” according to confidence;
- never infer favorite status from frequency alone;
- never combine household users;
- keep legacy aggregate count visible as `plex_played_event_count` during migration;
- deprecate `rewatch_count` as an authoritative label. A rewatch is `max(tracked_completions - 1, 0)` only within the same user and only with confidence breakdown attached.

UI:

- title detail: “Your watch history” timeline with confidence and “Why this count?”;
- movie card: concise tracked-completion count only when user-scoped data exists;
- episode detail: episode completion timeline;
- show detail: episodes completed, repeat episode completions, and recent activity—never “show watched N times”;
- privacy/export/delete actions include watch events and derivations.

### Optional Phase 3B — Tautulli enhanced source

Extend `TautulliClient` with paged history only after Plex Phase 1 fixtures establish the normalization contract. Tautulli may improve stable session/user/client metadata and historical depth, but it is another observer of Plex, not independent proof.

Requirements:

- explicit config/capability status: `disabled`, `available`, `degraded`;
- same identity mapping and normalized event contract;
- cross-source five-minute dedupe;
- source disagreement retained for diagnostics;
- no behavior regression when Tautulli is absent.

---

## 7. Movie and TV semantics

### Movies

- Correlation key: user + movie `rating_key`.
- A logical session may merge multiple sittings under the four-hour/monotonic rules.
- Completion count is the number of accepted `watch_completions`.
- A later unfinished replay is a new in-progress session and does not increment completions.

### TV

- Correlation key: user + **episode** `rating_key`.
- `library_episodes.view_count` remains the Phase 0 Plex aggregate fallback.
- Show totals derive from episode completion rows:
  - unique episodes completed;
  - total episode completions including repeats;
  - episodes in progress;
  - most recently completed episode.
- Consecutive episodes are separate sessions even under autoplay.
- Specials remain episodes. If Plex omits parent metadata, retain the episode event and defer the show rollup until metadata resolves.
- Never compare the new episode completion total directly to the old show-level `view_count`; the existing effective count is already an episode counter sum, not completed series watches.

---

## 8. Privacy, multi-user, and retention

- `source_user_key` is mandatory because an unmapped event still belongs to a distinct Plex identity.
- Only exact stable identifier mapping assigns `user_id`.
- Member APIs always require current `user_id`; owner diagnostics may inspect unmapped counts but not tokens or raw payloads.
- Single-owner mode may map the server-token account to `BOOTSTRAP_OWNER_ID` only after server/account identity is verified. Do not repeat the current aggregate-sync assumption for shared accounts.
- Local and OIDC users without `plex_user_id` have no personal Plex tracker until linked.
- Encrypt no new watch fields because they must be queryable locally; protect them through existing database/file permissions and role authorization.
- Add watch tables to privacy export and user deletion. On user deletion, set derived/event `user_id` null or purge according to the existing privacy policy while preserving no cross-user linkage.
- Default normalized-event retention: 24 months; retain completion summaries until user deletion. Make raw-event compaction a later data-retention task, not part of the first PR.
- Never persist Plex/Tautulli API keys, full webhook payloads, IPs, or transcode details in watch tables.

---

## 9. Concrete first PR — Plex history ledger

This is the smallest slice that creates durable value without pretending correlation is solved.

### Files

- Create: `projectionist/watch_tracker/__init__.py`
- Create: `projectionist/watch_tracker/models.py`
- Create: `projectionist/watch_tracker/store.py`
- Create: `projectionist/watch_tracker/plex_history.py`
- Create: `projectionist/scheduler/tasks/watch_history_ingest.py`
- Create: `tests/fixtures/plex/history_page_1.xml`
- Create: `tests/fixtures/plex/history_page_2.xml`
- Create: `tests/test_watch_history.py`
- Create: `tests/test_watch_tracker_api.py`
- Modify: `projectionist/connectors/plex.py`
- Modify: `projectionist/library/db/_schema.py`
- Modify: `projectionist/library/db/migrations.py`
- Modify: `projectionist/scheduler/tasks/__init__.py`
- Modify: `projectionist/web/app.py`
- Modify: `docs/DATA_MODEL.md`
- Modify: `docs/PRIVACY.md`

### Interfaces

- `PlexClient.history_page(*, start: int, size: int, since_ms: int | None) -> PlexHistoryPage`
- `normalize_plex_history(row, *, server_machine_id: str) -> WatchEventInput | None`
- `ingest_watch_events(db, events) -> IngestResult`
- `run_history_ingest(db, settings, should_cancel) -> dict`
- `watch_tracker_status(db) -> WatchTrackerStatus`

### Explicitly out of first PR

- no `watch_sessions` or `watch_completions`;
- no agent/UI count changes;
- no active-session polling;
- no Tautulli history;
- no historical reinterpretation of `library_items.view_count`;
- no claim that one history row equals one full watch;
- no member history endpoint—only owner-visible source health and ledger counts.

### Task 1: Add history fixtures and parser

- [ ] Write failing connector tests covering movie and episode rows, account identity, paging, missing optional fields, malformed rows, and endpoint-unavailable behavior.
- [ ] Add `PlexHistoryItem` / `PlexHistoryPage` dataclasses and `history_page`.
- [ ] Use existing XML request and container helpers; URL-encode all paging parameters.
- [ ] Run:

```bash
.venv/bin/python -m pytest tests/test_watch_history.py -k history_page -v
```

Expected: parser tests pass without network access.

### Task 2: Add append-only event storage

- [ ] Write a migration test asserting the new cursor, identity, and event tables plus indexes.
- [ ] Add migration 44, `watch_event_ledger`, in `projectionist/library/db/migrations.py`.
- [ ] Implement exact Plex-account mapping through `get_user_by_plex_id`.
- [ ] Implement normalized hashing and idempotent batch insert with `Database.run_write`.
- [ ] Write tests proving replay inserts zero duplicates, unknown users stay unmapped, and two Plex users watching the same title remain separate.
- [ ] Run:

```bash
.venv/bin/python -m pytest tests/test_watch_history.py tests/test_library_db.py -v
```

Expected: all selected tests pass.

### Task 3: Add resumable scheduled ingestion

- [ ] Write tests for initial bounded backfill, incremental overlap replay, page failure, cancellation, and cursor advancement only after successful commit.
- [ ] Implement `watch_history_ingest.run` returning task metrics:

```json
{
  "status": "ok",
  "source": "plex_history",
  "fetched": 250,
  "inserted": 12,
  "deduped": 238,
  "mapped": 10,
  "unmapped": 2,
  "high_watermark_ms": 1785732000000
}
```

- [ ] Register it at a 15-minute default interval. Treat missing Plex config or unsupported history endpoint as a clear skipped/degraded result.
- [ ] Run:

```bash
.venv/bin/python -m pytest tests/test_watch_history.py tests/test_scheduler*.py -v
```

Expected: ingestion and scheduler tests pass.

### Task 4: Document the ledger and privacy boundary

- [ ] Add owner-only `GET /api/admin/watch-tracker/status` returning source capability, cursor age, total/mapped/unmapped event counts, and last error; return no event rows, titles, or source identity keys.
- [ ] Add API authorization tests proving owners can inspect health and members cannot.
- [ ] Document normalized fields, identity behavior, retention intent, and the fact that no logical completion count ships in this PR.
- [ ] Add an owner-facing scheduler/status explanation; do not add a new member-facing promise.
- [ ] Run:

```bash
.venv/bin/python -m pytest tests/test_watch_tracker_api.py -v
rg -n "watch_events|Plex history|uninterrupted" docs/DATA_MODEL.md docs/PRIVACY.md
```

Expected: API authorization passes; data model and privacy limits are both present.

### First-PR acceptance criteria

- Replaying the same two history pages produces identical row counts.
- A page failure leaves the prior cursor intact.
- Events from two Plex accounts never share `user_id`.
- Unmapped accounts are retained as isolated source identities and never returned by a member query.
- No raw payload, token, IP, or API key is stored.
- The scheduler reports source quality and does not break application startup.
- The owner status endpoint reports freshness and mapping coverage without leaking watch titles or identities.
- Existing aggregate watch, scrobble, webhook prompt, and TV episode tests remain green.

---

## 10. Follow-up implementation tasks

### Task 5: Persist webhook and manual-action observations

**Files:**
- Modify: `projectionist/web/webhooks.py`
- Modify: `projectionist/library/watch_state.py`
- Test: `tests/test_webhooks.py`
- Test: `tests/test_watch_state.py`

- [x] Make event persistence independent of the 85% rating-prompt gate.
- [x] Include pause/stop/scrobble progress observations and exact Plex account mapping.
- [x] Record manual scrobble/unscrobble with the acting user and token source.
- [x] Keep prompts behavior-compatible until completion derivation ships.

### Task 6: Add live-session polling

**Files:**
- Create: `projectionist/watch_tracker/live_sessions.py`
- Modify: `projectionist/connectors/plex.py`
- Test: `tests/test_watch_live_sessions.py`

- [x] Probe active sessions and normalize progress without storing sensitive network fields.
- [x] Poll at adaptive 60-second/5-minute intervals.
- [x] Verify stop/restart, pause/resume, reconnect, client switch, and Plex outage fixtures.

### Task 7: Materialize sessions and completions

**Files:**
- Create: `projectionist/watch_tracker/correlate.py`
- Modify: `projectionist/watch_tracker/store.py`
- Modify: `projectionist/library/db/_schema.py`
- Modify: `projectionist/library/db/migrations.py`
- Test: `tests/test_watch_correlation.py`

- [ ] Add migrations for sessions, session-event links, and completions.
- [ ] Implement the exact merge, threshold, and suppression rules from §5.
- [ ] Use table-driven tests for:
  - one uninterrupted movie;
  - pause/resume across three sittings;
  - reconnect duplicate scrobbles;
  - genuine next-day rewatch;
  - credits completion;
  - manual mark/unmark;
  - client handoff;
  - two household users;
  - episode autoplay;
  - Plex + Tautulli duplicate terminal events.

### Task 8: Move prompts to completion transitions

**Files:**
- Modify: `projectionist/reviews/store.py`
- Modify: `projectionist/web/webhooks.py`
- Test: `tests/test_reviews.py`

- [ ] Queue one prompt from a new user-scoped completion.
- [ ] Preserve the 85% near-complete prompt path as a distinct “nearly finished” signal if product copy still wants it.
- [ ] Prevent duplicate prompts without conflating prompt dedupe with completion dedupe.

### Task 9: Add user summary APIs and agent fields

**Files:**
- Create: `projectionist/watch_tracker/api.py`
- Modify: `projectionist/web/app.py`
- Modify: `projectionist/agent/tools/__init__.py`
- Modify: `projectionist/agent/tools/_definitions.py`
- Test: `tests/test_watch_tracker_api.py`
- Test: `tests/test_agent_tools.py`

- [ ] Add current-user summary and owner-only diagnostics endpoints.
- [ ] Add tracker fields beside legacy aggregate semantics.
- [ ] Update system instructions to prefer tracked evidence and state confidence.
- [ ] Test cross-user authorization and no-coverage fallback.

### Task 10: Add watch-history UI

**Files:**
- Create: `frontend/src/components/WatchHistoryTimeline.jsx`
- Create: `frontend/src/lib/watchTracker.js`
- Modify: `frontend/src/components/TitleDetailContent.jsx`
- Modify: `frontend/src/components/ShowSeasonsPanel.jsx`
- Modify: `frontend/src/api/client.js`
- Test: `frontend/src/lib/watchTracker.test.mjs`
- Test: `e2e/watch-tracker.spec.ts`

- [ ] Render tracked completions, sittings, confidence, and evidence explanation.
- [ ] Use episode rollups for shows.
- [ ] Show legacy Plex aggregate only as a labeled fallback.
- [ ] Verify owner/member isolation, empty states, theme safety, keyboard access, and narrow screens.

### Task 11: Add optional Tautulli history

**Files:**
- Modify: `projectionist/connectors/tautulli.py`
- Create: `projectionist/watch_tracker/tautulli_history.py`
- Test: `tests/test_tautulli_watch_history.py`

- [ ] Add paged history adapter and stable identity capability checks.
- [ ] Normalize into `WatchEventInput`.
- [ ] Test cross-source dedupe and degraded/no-Tautulli behavior.

### Task 12: Privacy lifecycle and release documentation

**Files:**
- Modify: `projectionist/web/library_privacy.py`
- Modify: `projectionist/privacy/schema.py`
- Modify: `projectionist/library/db/_users.py`
- Modify: `projectionist/web/app.py`
- Modify: `projectionist/scheduler/tasks/data_retention.py`
- Modify: `docs/HELP.md`
- Modify: `docs/CONFIGURATION.md`
- Modify: `docs/PRIVACY.md`
- Modify: `docs/DATA_MODEL.md`
- Modify: `CHANGELOG.md`

- [ ] Add export/delete coverage and raw-event retention.
- [ ] Explain confidence with worked examples.
- [ ] Replace naive rewatch wording only where tracker-backed data is actually available.
- [ ] Add benefit-led release highlights and regenerate release notes.

---

## 11. Validation matrix

Backend:

```bash
.venv/bin/python -m pytest tests/test_watch_history.py tests/test_watch_correlation.py tests/test_webhooks.py tests/test_watch_state.py tests/test_reviews.py tests/test_agent_tools.py -v
.venv/bin/python -m pytest tests/
```

Frontend when Phase 4 lands:

```bash
cd frontend && npm run test:unit
cd frontend && npm run lint
cd frontend && npm run build
npm run test:e2e
```

Operational fixture replay:

1. Import a history page twice; second import inserts zero rows.
2. Deliver pause → stop → scrobble with reconnect duplicates; one session and one completion result.
3. Deliver a second viewing after a clear restart; two completions result.
4. Repeat with two Plex account IDs; no merged session or summary.
5. Disable Tautulli and webhooks; Plex history ingestion remains functional.
6. Disable history capability; app boots and scheduler reports degraded source.
7. Delete/export a user; only that user’s watch records are affected.

---

## 12. Decisions locked by this plan

- The source of truth is normalized evidence plus deterministic derivation, not Plex aggregates.
- The core is Plex-native; Tautulli is an optional enhanced source.
- Completion threshold is 90%; rating-prompt near-completion remains a separate 85% concept.
- Four hours is the default same-viewing merge window; client handoff requires a 30-minute monotonic window.
- Exact played/scrobble duplicates within 120 seconds are suppressed.
- A new completion after one already accepted requires restart/progress evidence or a conservative elapsed-time floor.
- Confidence is part of the persisted product model, not prose added at render time.
- Per-user identity is mandatory for personal claims.
- TV is episode-first.
- The first PR ships only a durable, idempotent Plex history ledger and scheduler integration.

## 13. Open implementation probes — not product ambiguity

Resolve these with captured fixtures before merging Phase 1:

- Which history endpoint and paging attributes are present on the minimum supported Plex server version?
- Which stable account, client, session, event, and timestamp attributes are actually returned by that endpoint?
- Does a server-owner token expose managed-user history consistently, and are account IDs present on every row?
- Which webhook fields remain stable across Plex Web, mobile, TV, and synced/offline playback?
- Whether the existing idle scheduler can responsibly run a 15-minute I/O task under current idle semantics; if not, use the established background service lifecycle.

Missing fields reduce confidence; they do not justify inferred identity or fabricated progress.
