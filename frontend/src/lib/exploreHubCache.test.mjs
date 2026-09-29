import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  clearExploreHubCache,
  hubRailState,
  readExploreHubCache,
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
});
