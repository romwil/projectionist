import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  clearExploreHubCache,
  exploreHubStillWarming,
  hubRailState,
  mergeContinueWatchingNotes,
  readExploreHubCache,
  rememberContinueWatchingProgress,
  writeExploreHubCache,
} from "./exploreHubCache.js";

function memoryStorage() {
  const map = new Map();
  return {
    getItem: (k) => (map.has(k) ? map.get(k) : null),
    setItem: (k, v) => map.set(k, String(v)),
    removeItem: (k) => map.delete(k),
  };
}

describe("exploreHubCache", () => {
  it("round-trips hub payloads and marks freshness", () => {
    const storage = memoryStorage();
    const payload = {
      rails: { recently_added: { items: [{ title: "Heat" }], note: null } },
    };
    writeExploreHubCache(payload, storage);
    const hit = readExploreHubCache(storage);
    assert.equal(hit.payload.rails.recently_added.items[0].title, "Heat");
    assert.equal(hit.stale, false);
    clearExploreHubCache(storage);
    assert.equal(readExploreHubCache(storage), null);
  });

  it("hubRailState maps rails for Explore sections", () => {
    const state = hubRailState(
      {
        rails: {
          recently_added_episodes: {
            items: [{ title: "Severance", episode_label: "S2E1" }],
            note: null,
            mode: "x",
          },
        },
      },
      "recently_added_episodes",
    );
    assert.equal(state.items[0].episode_label, "S2E1");
    assert.equal(state.loading, false);
    assert.equal(state.meta.mode, "x");
  });

  it("paints ready rails while a slower rail is still pending", () => {
    const payload = {
      warming: true,
      rails: {
        recently_added: { items: [{ title: "Heat" }], pending: false },
        seasonal_spotlight: { items: [], pending: true, note: "still matching" },
      },
    };
    assert.equal(exploreHubStillWarming(payload), true);
    const ready = hubRailState(payload, "recently_added", { loading: true });
    assert.equal(ready.loading, false);
    assert.equal(ready.items[0].title, "Heat");
    const waiting = hubRailState(payload, "seasonal_spotlight");
    assert.equal(waiting.loading, true);
    assert.equal(waiting.items.length, 0);
    assert.equal(waiting.note, null);
  });

  it("puts a play just recorded on Continue Watching without the old offset", () => {
    const storage = memoryStorage();
    const previous = {
      warming: false,
      rails: {
        recently_added: { items: [{ title: "Heat" }] },
        continue_watching: {
          items: [{ title: "Heat", rating_key: "movie-1", play_rating_key: "movie-1", view_offset_ms: 60_000 }],
          note: null,
        },
      },
    };
    writeExploreHubCache(previous, storage);
    rememberContinueWatchingProgress(
      {
        ratingKey: "movie-1",
        viewOffsetMs: 1_800_000,
        durationMs: 6_000_000,
        title: "Heat",
        mediaType: "movie",
      },
      storage,
    );
    const hit = readExploreHubCache(storage);
    const row = hit.payload.rails.continue_watching.items[0];
    assert.equal(row.title, "Heat");
    assert.equal(row.view_offset_ms, 1_800_000);
    assert.notEqual(row.view_offset_ms, previous.rails.continue_watching.items[0].view_offset_ms);
    assert.equal(hit.payload.rails.recently_added.items[0].title, "Heat");

    const staleServer = {
      warming: false,
      rails: {
        continue_watching: {
          source: "plex_on_deck",
          items: [{ title: "Heat", rating_key: "movie-1", play_rating_key: "movie-1", view_offset_ms: 60_000 }],
        },
      },
    };
    const merged = mergeContinueWatchingNotes(staleServer, storage);
    assert.equal(merged.rails.continue_watching.items[0].view_offset_ms, 1_800_000);
    assert.notEqual(
      merged.rails.continue_watching.items[0].view_offset_ms,
      staleServer.rails.continue_watching.items[0].view_offset_ms,
    );
  });
});
