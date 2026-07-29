# Storage Intelligence for TV + show rollup health

**Date:** 2026-07-28  
**Status:** Approved  
**Version target:** 1.28.0 (feature)

## Problem

1. Storage Intelligence purge grid never shows TV shows because `library_items.file_size` is 0 for every show (sizes live on `library_episodes`).
2. Full remove via Sonarr already works; the gap is candidate discovery + confident presentation.
3. Agent tools under-report TV progress (`total_episode_count` not sortable/filterable; progress payloads lack totals).
4. Purge UX shows a hard-capped 20 rows from a 25-item cache with no pagination or interactive refill.

## Decisions

- **Approach B:** Unified show rollups + purge + agent honesty.
- **Page size:** 20. **Buffer target:** 100 (5×). **Refill threshold:** buffer length &lt; 80.
- **Compute strategy:** 5× buffer + async top-up after purge/keep; keep 6h idle full recompute at limit 100. Not 10× upfront; not user-driven “load more” as primary.
- **Freshness:** On panel load and page change, enrich **visible page** rows from SQLite; when *arr configured, prefer Radarr/Sonarr `sizeOnDisk` for those visible rows only.
- **Keep action:** Existing dismiss (`purge_dismissals`).
- **Delete:** Default full remove (Radarr/Sonarr files + import exclusion + local `acquisition_exclusions` + Plex metadata + index).

## Data model

### Show rollups (`_update_show_episode_rollups_on_conn`)

Also set:

```sql
file_size = COALESCE(SUM(library_episodes.file_size), 0)
```

alongside existing `total_episode_count`, `unwatched_episode_count`, `last_episode_watched_at`, `last_episode_sync_at`.

### Backfill

Migration or boot-safe one-shot: for every show, recompute rollups from `library_episodes` (including `file_size`) so existing DBs gain sizes without a full Plex resync.

## Purge candidates

- Include movies and shows (already no media_type filter once sizes exist).
- `DEFAULT_LIMIT` / recompute limit → **100**.
- Cache shape gains optional `page_size: 20`, `buffer_target: 100`.
- After purge/dismiss: `drop_cached_purge_keys`; if `len(items) < 80`, trigger background top-up (append new scored titles excluding dismissed + keys already in buffer).
- Enrich API (or GET with `enrich=1` / dedicated enrich-visible): refresh size / last_watched / episode counts for provided rating_keys; *arr size override when available.

## UI (Dashboard Storage Intelligence)

- Same grid; add **Type** column (Movie / Show).
- Paginate over buffer (prev/next + “Page X of Y”).
- On mount and page change: enrich visible keys, then render.
- After purge/keep: reload cache; show refill-in-progress hint if top-up kicked.
- Labels: “Keep” may stay “Dismiss” in UI if already shipped — prefer renaming button to **Keep** for clarity (optional polish; dismiss semantics unchanged).

## Agent honesty

- Add `total_episode_count` to library query `SortField` and tool sort enum.
- Add `min_total_episodes` / `max_total_episodes` filters (mirror unwatched episode filters).
- `summarize_tv_progress` response includes `total_shows`, `matched`, `returned`, `limit`, `in_progress_only` so agents cannot claim empty library when filtered/capped.

## Out of scope

- Episode-level purge (season/episode delete).
- Changing Sonarr/Radarr delete API contracts.
- Live *arr scan of entire library on every dashboard load.

## Success criteria

- Shows with episode bytes appear in purge candidates when they meet score thresholds.
- Paginating 5 pages of 20 works against a 100-item buffer.
- Purge/keep shrinks buffer and tops up toward 100 asynchronously.
- Visible rows show non-stale size/last-watched after enrich.
- Full remove of a show deletes via Sonarr (files + exclusion) and records acquisition exclusion.
- Agent can sort/filter by `total_episode_count`; progress tool reports totals.

## Spec self-review

- No placeholders.
- Consistent with prior acquisition-exclusion fix (re-add blocked after full remove).
- Scope is one releaseable feature set (rollup + purge UX + agent honesty).
