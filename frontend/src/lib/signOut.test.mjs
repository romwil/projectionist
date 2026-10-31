import assert from "node:assert/strict";
import test from "node:test";

import { EXPLORE_HUB_CACHE_KEY } from "./exploreHubCache.ts";
import { RAIL_SEED_STORAGE_KEY } from "./railChatSeed.ts";
import { clearPerUserClientState, signOut } from "./signOut.ts";

function memoryStorage(entries = {}) {
  const map = new Map(Object.entries(entries));
  return {
    map,
    getItem: (key) => (map.has(key) ? map.get(key) : null),
    setItem: (key, value) => map.set(key, String(value)),
    removeItem: (key) => map.delete(key),
  };
}

test("clearPerUserClientState removes the stored thread id and per-user caches", () => {
  const local = memoryStorage({
    curatorx_session: "thread-of-previous-user",
    curatorx_active_lens: "lens-1",
    projectionist_sync_chime_muted: "1",
  });
  const session = memoryStorage({
    [EXPLORE_HUB_CACHE_KEY]: "{}",
    [RAIL_SEED_STORAGE_KEY]: "{}",
  });
  clearPerUserClientState({ local, session });
  assert.equal(local.getItem("curatorx_session"), null);
  assert.equal(local.getItem("curatorx_active_lens"), null);
  assert.equal(local.getItem("projectionist_sync_chime_muted"), "1");
  assert.equal(session.getItem(EXPLORE_HUB_CACHE_KEY), null);
  assert.equal(session.getItem(RAIL_SEED_STORAGE_KEY), null);
});

test("signOut clears the auth snapshot and client state even when logout fails", async () => {
  const calls = [];
  await signOut({
    logoutFn: async () => {
      calls.push("logout");
      throw new Error("offline");
    },
    clearSnapshot: () => calls.push("snapshot"),
    clearClientState: () => calls.push("client"),
    navigateTo: (path) => calls.push(`go:${path}`),
  });
  assert.deepEqual(calls, ["logout", "snapshot", "client", "go:/login"]);
});
