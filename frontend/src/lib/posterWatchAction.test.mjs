import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, it } from "node:test";
import {
  applyContinueWatchingProgress,
  rememberContinueWatchingProgress,
  writeExploreHubCache,
  readExploreHubCache,
} from "./exploreHubCache.ts";
import {
  commitPosterWatched,
  posterWatchAction,
  watchedStatePatch,
} from "./posterWatchAction.ts";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");

describe("posterWatchAction", () => {
  it("offers the action for in-library titles with a rating_key", () => {
    const action = posterWatchAction(
      { in_library: true, rating_key: "rk-1" },
      { role: "owner", multiUserEnabled: false },
    );
    assert.ok(action);
    assert.equal(action.label, "Mark as watched");
    assert.equal(action.watched, false);
    assert.equal(action.nextWatched, true);
  });

  it("also offers it to a signed-in member when multi-user is on", () => {
    const action = posterWatchAction(
      { in_library: true, rating_key: "rk-1" },
      { role: "member", multiUserEnabled: true },
    );
    assert.ok(action);
  });

  it("hides the action for external / not-in-library cards", () => {
    assert.equal(
      posterWatchAction({ in_library: false, rating_key: "rk-1" }, { role: "owner" }),
      null,
    );
    assert.equal(
      posterWatchAction({ tmdb_id: 42, in_library: false }, { role: "owner" }),
      null,
    );
  });

  it("hides the action when there is no rating_key", () => {
    assert.equal(
      posterWatchAction({ in_library: true, tmdb_id: 42 }, { role: "owner" }),
      null,
    );
  });

  it("treats a legacy guest role like a member when multi-user is on", () => {
    assert.deepEqual(
      posterWatchAction(
        { in_library: true, rating_key: "rk-1" },
        { role: "guest", multiUserEnabled: true },
      ),
      posterWatchAction(
        { in_library: true, rating_key: "rk-1" },
        { role: "member", multiUserEnabled: true },
      ),
    );
  });

  it("toggles the label to unwatched for an already-watched title", () => {
    const byWatchState = posterWatchAction(
      { in_library: true, rating_key: "rk-1", watch_state: "watched" },
      { role: "owner" },
    );
    assert.equal(byWatchState.label, "Mark as unwatched");
    assert.equal(byWatchState.watched, true);
    assert.equal(byWatchState.nextWatched, false);

    const byViewCount = posterWatchAction(
      { in_library: true, rating_key: "rk-1", view_count: 2 },
      { role: "owner" },
    );
    assert.equal(byViewCount.label, "Mark as unwatched");
  });

  it("treats in-progress titles as still offering Mark as watched", () => {
    const action = posterWatchAction(
      { in_library: true, rating_key: "rk-1", watch_state: "partial" },
      { role: "owner" },
    );
    assert.equal(action.label, "Mark as watched");
    assert.equal(action.nextWatched, true);
  });
});

describe("watchedStatePatch", () => {
  it("produces an optimistic watched patch", () => {
    assert.deepEqual(watchedStatePatch(true), {
      watch_state: "watched",
      view_count: 1,
      view_offset_ms: 0,
      resume_label: "",
    });
  });

  it("produces an optimistic unwatched patch that clears progress", () => {
    assert.deepEqual(watchedStatePatch(false), {
      watch_state: "unwatched",
      view_count: 0,
      view_offset_ms: 0,
      resume_label: "",
    });
  });
});

describe("poster menu style contract", () => {
  it("gives every poster menu action one class and one type style", () => {
    const menu = readFileSync(join(root, "components/PosterActionMenu.tsx"), "utf8");
    const css = readFileSync(join(root, "styles/03-browse-controls.css"), "utf8");
    const popover = menu.slice(menu.indexOf('className="poster-action-popover"'), menu.indexOf("document.body"));
    assert.ok(popover.includes("poster-action-popover"));
    assert.doesNotMatch(menu, /poster-action-watched/);
    const tags = popover.match(/<(?:Link|a|button|TitleDetailLink)\b[^>]*>/g) || [];
    assert.ok(tags.length >= 8, `expected menu actions, got ${tags.length}`);
    for (const tag of tags) {
      assert.match(tag, /className="poster-action-item"/, tag);
    }
    assert.match(css, /\.poster-action-popover \.poster-action-item\s*\{[^}]*text-decoration:\s*none/);
    assert.match(css, /\.poster-action-popover \.poster-action-item\s*\{[^}]*font-weight:\s*500/);
    assert.match(css, /\.poster-action-popover \.poster-action-item\s*\{[^}]*font-size:\s*var\(--text-sm\)/);
    assert.match(css, /\.poster-action-popover \.poster-action-item\s*\{[^}]*min-height:\s*var\(--tap-min\)/);
    assert.match(css, /\.poster-action-popover \.poster-action-item\s*\{[^}]*color:\s*var\(--text\)/);
    assert.doesNotMatch(
      css.slice(css.indexOf(".poster-action-popover .poster-action-item")),
      /\.poster-action-popover a\s*,/,
    );
  });
});

function memoryStorage() {
  const map = new Map();
  return {
    getItem: (key) => (map.has(key) ? map.get(key) : null),
    setItem: (key, value) => map.set(key, String(value)),
    removeItem: (key) => map.delete(key),
  };
}

describe("commitPosterWatched", () => {
  const showCard = {
    title: "The Twilight Zone",
    media_type: "show",
    in_library: true,
    rating_key: "show-tz",
    play_rating_key: "ep-s1e2",
    watch_state: "partial",
    view_offset_ms: 180_000,
    duration_ms: 1_500_000,
    continue_season: 1,
    continue_episode: 2,
    continue_episode_title: "Where Is Everybody?",
    resume_label: "S1E2 · 18% watched",
    poster_url: "/poster/tz",
    year: 1959,
  };

  it("scrobbles the episode key and drops the continue-watching card", async () => {
    const action = posterWatchAction(showCard, { role: "owner" });
    assert.equal(action.ratingKey, "ep-s1e2");
    assert.equal(action.label, "Mark as watched");
    const calls = [];
    const storage = memoryStorage();
    writeExploreHubCache(
      {
        rails: {
          continue_watching: {
            items: [{ ...showCard }],
            note: null,
          },
        },
      },
      storage,
    );
    const { patch, ratingKey } = await commitPosterWatched(showCard, {
      watched: true,
      setWatched: async (key, watched) => {
        calls.push({ key, watched });
        return { view_count: 1, plex_synced: true, media_type: "episode" };
      },
      rememberProgress: (note) => rememberContinueWatchingProgress(note, storage),
    });
    assert.equal(ratingKey, "ep-s1e2");
    assert.deepEqual(calls, [{ key: "ep-s1e2", watched: true }]);
    assert.equal(patch.watch_state, "watched");
    assert.equal(patch.view_offset_ms, 0);
    const row = readExploreHubCache(storage).payload.rails.continue_watching;
    assert.equal(row.items.length, 0);
  });

  it("does not update continue watching when the watched API fails", async () => {
    const storage = memoryStorage();
    let remembered = 0;
    writeExploreHubCache(
      { rails: { continue_watching: { items: [{ ...showCard }], note: null } } },
      storage,
    );
    await assert.rejects(
      () => commitPosterWatched(showCard, {
        watched: true,
        setWatched: async () => {
          throw new Error("Library item not found");
        },
        rememberProgress: () => {
          remembered += 1;
        },
      }),
      /Library item not found/,
    );
    assert.equal(remembered, 0);
    assert.equal(readExploreHubCache(storage).payload.rails.continue_watching.items.length, 1);
  });

  it("uses the movie rating key when the card is not an episode", async () => {
    const movie = { title: "Heat", media_type: "movie", in_library: true, rating_key: "movie-1", view_offset_ms: 60_000 };
    const calls = [];
    await commitPosterWatched(movie, {
      watched: true,
      setWatched: async (key, watched) => {
        calls.push({ key, watched });
        return { view_count: 1 };
      },
    });
    assert.deepEqual(calls, [{ key: "movie-1", watched: true }]);
    const noteItems = applyContinueWatchingProgress(
      { rails: { continue_watching: { items: [{ ...movie, play_rating_key: "movie-1" }] } } },
      { ratingKey: "movie-1", viewOffsetMs: 0, finished: true, title: "Heat", mediaType: "movie" },
    );
    assert.equal(noteItems.rails.continue_watching.items.length, 0);
  });
});
