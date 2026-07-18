import assert from "node:assert/strict";
import test from "node:test";

import { watchProgressLabel, watchProgressState } from "./watchProgress.js";

test("movie watched when view_count > 0", () => {
  assert.equal(watchProgressState({ media_type: "movie", view_count: 1 }), "watched");
  assert.equal(watchProgressState({ media_type: "movie", view_count: 3, view_offset_ms: 1000 }), "watched");
});

test("movie partial when unfinished view_offset and no view_count", () => {
  assert.equal(
    watchProgressState({ media_type: "movie", view_count: 0, view_offset_ms: 12_000 }),
    "partial",
  );
});

test("movie unwatched with no signals", () => {
  assert.equal(watchProgressState({ media_type: "movie", view_count: 0 }), "unwatched");
  assert.equal(watchProgressState(null), "unwatched");
});

test("show watched when all episodes watched", () => {
  assert.equal(
    watchProgressState({
      media_type: "show",
      total_episode_count: 10,
      unwatched_episode_count: 0,
    }),
    "watched",
  );
});

test("show partial when some episodes remain", () => {
  assert.equal(
    watchProgressState({
      media_type: "show",
      total_episode_count: 10,
      unwatched_episode_count: 4,
    }),
    "partial",
  );
});

test("show unwatched when no episodes watched", () => {
  assert.equal(
    watchProgressState({
      media_type: "show",
      total_episode_count: 10,
      unwatched_episode_count: 10,
    }),
    "unwatched",
  );
});

test("show falls back to view_count without episode totals", () => {
  assert.equal(watchProgressState({ media_type: "show", view_count: 2 }), "watched");
  assert.equal(watchProgressState({ media_type: "show", view_count: 0 }), "unwatched");
});

test("watchProgressLabel covers badge copy", () => {
  assert.equal(watchProgressLabel("watched"), "Watched");
  assert.equal(watchProgressLabel("partial"), "In progress");
  assert.equal(watchProgressLabel("unwatched"), "");
});

test("honors privacy watch_state when raw counters are stripped", () => {
  assert.equal(watchProgressState({ media_type: "movie", watch_state: "watched" }), "watched");
  assert.equal(watchProgressState({ media_type: "movie", watch_state: "in_progress" }), "partial");
  assert.equal(watchProgressState({ media_type: "show", watch_state: "unwatched" }), "unwatched");
});
