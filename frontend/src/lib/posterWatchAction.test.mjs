import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { posterWatchAction, watchedStatePatch } from "./posterWatchAction.js";

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

  it("hides the action from guests while multi-user is on", () => {
    assert.equal(
      posterWatchAction(
        { in_library: true, rating_key: "rk-1" },
        { role: "guest", multiUserEnabled: true },
      ),
      null,
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
    assert.deepEqual(watchedStatePatch(true), { watch_state: "watched", view_count: 1 });
  });

  it("produces an optimistic unwatched patch that clears progress", () => {
    assert.deepEqual(watchedStatePatch(false), {
      watch_state: "unwatched",
      view_count: 0,
      view_offset_ms: 0,
    });
  });
});
