import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  applyOptimisticPinToggle,
  optimisticPinFromItem,
  removePinById,
  upsertPin,
} from "./optimisticWatchlist.js";

describe("optimisticWatchlist", () => {
  it("builds an optimistic pin from a title card", () => {
    const pin = optimisticPinFromItem({
      tmdb_id: 10,
      media_type: "movie",
      title: "Heat",
    });
    assert.equal(pin.tmdb_id, 10);
    assert.equal(pin.title, "Heat");
    assert.equal(pin._optimistic, true);
    assert.ok(String(pin.id).startsWith("optimistic-"));
  });

  it("removes by id and upserts by media key", () => {
    const a = { id: "a", media_type: "movie", tmdb_id: 1, title: "A" };
    const b = { id: "b", media_type: "movie", tmdb_id: 2, title: "B" };
    assert.deepEqual(removePinById([a, b], "a").map((p) => p.id), ["b"]);
    const next = upsertPin([a], { id: "a2", media_type: "movie", tmdb_id: 1, title: "A+" });
    assert.equal(next.length, 1);
    assert.equal(next[0].title, "A+");
  });

  it("toggles add/remove with rollback snapshots", () => {
    const pins = [{ id: "p1", media_type: "movie", tmdb_id: 5, title: "X" }];
    const removed = applyOptimisticPinToggle(pins, {
      item: pins[0],
      pinRecord: pins[0],
      adding: false,
    });
    assert.equal(removed.next.length, 0);
    assert.equal(removed.rollback.length, 1);

    const added = applyOptimisticPinToggle([], {
      item: { tmdb_id: 9, media_type: "movie", title: "Y" },
      adding: true,
    });
    assert.equal(added.next.length, 1);
    assert.equal(added.next[0].title, "Y");
  });
});
