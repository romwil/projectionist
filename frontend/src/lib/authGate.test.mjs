import assert from "node:assert/strict";
import test from "node:test";

import { createAuthSnapshotStore } from "./authGate.ts";

test("concurrent auth reads share one features call and one session call", async () => {
  let features = 0;
  let me = 0;
  const store = createAuthSnapshotStore({
    getFeatures: async () => {
      features += 1;
      await new Promise((resolve) => setTimeout(resolve, 15));
      return { features: { multi_user_enabled: true }, setup_state: "active" };
    },
    getAuthMe: async () => {
      me += 1;
      return { user: { id: "member-1", role: "member" } };
    },
  });

  const results = await Promise.all(Array.from({ length: 40 }, () => store.load()));
  assert.equal(features, 1);
  assert.equal(me, 1);
  assert.equal(results.every((snap) => snap.cacheable && snap.role === "member"), true);

  await store.load();
  assert.equal(features, 1);
  assert.equal(me, 1);
});

test("a logged-out auth read is not reused, so login can refetch", async () => {
  let features = 0;
  const store = createAuthSnapshotStore({
    getFeatures: async () => {
      features += 1;
      return { features: { multi_user_enabled: true }, setup_state: "active" };
    },
    getAuthMe: async () => null,
  });

  const first = await store.load();
  assert.equal(first.needsLogin, true);
  assert.equal(first.cacheable, false);
  await store.load();
  assert.equal(features, 2);
});

test("single-user session lookups share one /auth/me", async () => {
  let me = 0;
  const store = createAuthSnapshotStore({
    getFeatures: async () => ({ features: { multi_user_enabled: false }, setup_state: "active" }),
    getAuthMe: async () => {
      me += 1;
      await new Promise((resolve) => setTimeout(resolve, 10));
      return { user: { ui_theme: "lights-down" } };
    },
  });

  await Promise.all(Array.from({ length: 20 }, () => store.loadSessionUser()));
  assert.equal(me, 1);
});
