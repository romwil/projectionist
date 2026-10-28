import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import {
  CONTINUE_WATCHING_PROGRESS_KEY,
  EXPLORE_HUB_WARMING_STALL_MESSAGE,
  clearExploreHubCache,
  dropReflectedContinueWatchingNotes,
  exploreHubLoadError,
  exploreHubStillWarming,
  hubRailState,
  mergeContinueWatchingNotes,
  readExploreHubCache,
  rememberContinueWatchingProgress,
  spliceContinueWatchingRail,
  writeExploreHubCache,
} from "./exploreHubCache.js";

const here = dirname(fileURLToPath(import.meta.url));

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

  const armstrongShow = {
    title: "The Armstrong & Miller Show",
    rating_key: "show-am",
    play_rating_key: "am-s1e1",
    media_type: "show",
    year: 2007,
    view_offset_ms: 18_000,
    duration_ms: 1_800_000,
    continue_season: 1,
    continue_episode: 1,
    resume_label: "S1E1 · 1% watched",
  };

  it("keeps one Armstrong & Miller card when E1 finishes and E2 starts", () => {
    const storage = memoryStorage();
    writeExploreHubCache(
      { rails: { continue_watching: { items: [{ ...armstrongShow }], note: null } } },
      storage,
    );
    rememberContinueWatchingProgress(
      {
        ratingKey: "am-s1e1",
        showRatingKey: "show-am",
        viewOffsetMs: 0,
        durationMs: 1_800_000,
        finished: true,
        title: "The Armstrong & Miller Show",
        mediaType: "episode",
        season: 1,
        episode: 1,
      },
      storage,
    );
    rememberContinueWatchingProgress(
      {
        ratingKey: "am-s1e2",
        showRatingKey: "show-am",
        viewOffsetMs: 36_000,
        durationMs: 1_800_000,
        title: "The Armstrong & Miller Show",
        mediaType: "episode",
        season: 1,
        episode: 2,
        episodeTitle: "Episode 2",
      },
      storage,
    );
    const row = readExploreHubCache(storage).payload.rails.continue_watching;
    assert.equal(row.items.length, 1);
    assert.equal(row.items[0].title, "The Armstrong & Miller Show");
    assert.equal(row.items[0].rating_key, "show-am");
    assert.equal(row.items[0].play_rating_key, "am-s1e2");
    assert.equal(row.items[0].continue_episode, 2);
    assert.match(row.items[0].resume_label, /S1E2/);

    const staleHub = {
      rails: {
        continue_watching: {
          items: [
            { ...armstrongShow },
            {
              ...armstrongShow,
              play_rating_key: "am-s1e2",
              continue_episode: 2,
              view_offset_ms: 36_000,
              resume_label: "S1E2 · 2% watched",
            },
          ],
        },
      },
    };
    const merged = mergeContinueWatchingNotes(staleHub, storage);
    assert.equal(merged.rails.continue_watching.items.length, 1);
    assert.equal(merged.rails.continue_watching.items[0].play_rating_key, "am-s1e2");
  });

  it("splices live Continue Watching percent without clearing the rail", () => {
    const payload = {
      rails: {
        continue_watching: { items: [{ ...armstrongShow }], note: null, pending: false },
        recently_added: { items: [{ title: "Heat" }], note: null },
      },
    };
    const live = {
      feed: "continue-watching",
      source: "plex_on_deck",
      items: [
        {
          ...armstrongShow,
          play_rating_key: "am-s1e2",
          continue_episode: 2,
          view_offset_ms: 558_000,
          resume_label: "S1E2 · 31% watched",
        },
      ],
      total: 1,
      note: null,
    };
    const next = spliceContinueWatchingRail(payload, live);
    assert.equal(next.rails.continue_watching.items.length, 1);
    assert.equal(next.rails.continue_watching.items[0].view_offset_ms, 558_000);
    assert.match(next.rails.continue_watching.items[0].resume_label, /31%/);
    assert.equal(next.rails.continue_watching.pending, false);
    assert.equal(next.rails.recently_added.items[0].title, "Heat");
    assert.equal(payload.rails.continue_watching.items[0].view_offset_ms, 18_000);
  });

  it("shows Plex-only progress on load with no Play notes in this tab", () => {
    const storage = memoryStorage();
    const live = {
      feed: "continue-watching",
      source: "plex_on_deck",
      items: [
        {
          title: "House",
          rating_key: "show-house",
          play_rating_key: "house-s5e2",
          media_type: "show",
          continue_season: 5,
          continue_episode: 2,
          view_offset_ms: 216_000,
          duration_ms: 2_640_000,
          resume_label: "S5E2 · 6% watched",
        },
      ],
      total: 1,
      note: null,
    };
    const next = spliceContinueWatchingRail({ rails: {} }, live);
    const merged = mergeContinueWatchingNotes(next, storage);
    assert.equal(merged.rails.continue_watching.items.length, 1);
    assert.equal(merged.rails.continue_watching.items[0].title, "House");
    assert.match(merged.rails.continue_watching.items[0].resume_label, /6%/);
    assert.equal(storage.getItem(CONTINUE_WATCHING_PROGRESS_KEY), null);
  });

  it("drops session notes a live rail already reflects", () => {
    const storage = memoryStorage();
    rememberContinueWatchingProgress(
      {
        ratingKey: "am-s1e2",
        showRatingKey: "show-am",
        viewOffsetMs: 36_000,
        durationMs: 1_800_000,
        title: "The Armstrong & Miller Show",
        mediaType: "episode",
        season: 1,
        episode: 2,
      },
      storage,
    );
    const livePayload = {
      rails: {
        continue_watching: {
          items: [
            {
              ...armstrongShow,
              play_rating_key: "am-s1e2",
              continue_episode: 2,
              view_offset_ms: 36_000,
            },
          ],
        },
      },
    };
    dropReflectedContinueWatchingNotes(livePayload, storage);
    assert.equal(JSON.parse(storage.getItem(CONTINUE_WATCHING_PROGRESS_KEY) || "[]").length, 0);
    const stale = {
      rails: {
        continue_watching: { items: [{ ...armstrongShow }] },
      },
    };
    const merged = mergeContinueWatchingNotes(stale, storage);
    assert.equal(merged.rails.continue_watching.items[0].play_rating_key, "am-s1e1");
  });

  it("ExplorePage live-refreshes Continue Watching on mount and visibility", () => {
    const src = readFileSync(join(here, "../pages/ExplorePage.tsx"), "utf8");
    assert.match(src, /getExploreFeedContinueWatching/);
    assert.match(src, /visibilitychange/);
    assert.match(src, /pageshow/);
    assert.match(src, /spliceContinueWatchingRail/);
    assert.doesNotMatch(src, /setHub\(\{ loading: true/);
  });

  it("does not clear warming locally when the poll gives up", () => {
    const stalled = {
      warming: true,
      rails: {
        recently_added: { items: [{ title: "Heat" }], pending: false },
        seasonal_spotlight: { items: [], pending: true },
      },
    };
    assert.equal(exploreHubStillWarming(stalled), true);
    const waiting = hubRailState(stalled, "seasonal_spotlight");
    assert.equal(waiting.loading, true);
    assert.match(EXPLORE_HUB_WARMING_STALL_MESSAGE, /still warming/);
    const src = readFileSync(join(here, "../pages/ExplorePage.tsx"), "utf8");
    assert.match(src, /EXPLORE_HUB_WARMING_STALL_MESSAGE/);
    assert.match(src, /explore-hub-status/);
    assert.doesNotMatch(src, /warming:\s*false/);
  });

  it("keeps a fetch error visible even when cache already painted", () => {
    assert.equal(exploreHubLoadError(new Error("hub down")), "hub down");
    assert.match(
      exploreHubLoadError(new Error("hub down"), { hasCache: true }),
      /hub down.*last successful load/,
    );
    const src = readFileSync(join(here, "../pages/ExplorePage.tsx"), "utf8");
    assert.match(src, /exploreHubLoadError/);
    assert.doesNotMatch(src, /error: prev\.payload \? ""/);
  });
});
