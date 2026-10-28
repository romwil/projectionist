import assert from "node:assert/strict";
import test from "node:test";

import {
  ADD_FEEDBACK_DISMISS_MS,
  PERFECT_PICK_ACK,
  appendPerfectPickAck,
  arrServiceConnected,
  chatErrorMessage,
  isNightOwlHour,
  pickStoredThreadId,
} from "./chatSession.ts";

test("appendPerfectPickAck appends to the first text block only", () => {
  const message = {
    blocks: [
      { type: "text", content: "Try Heat" },
      { type: "title_cards", items: [{ title: "Heat" }] },
    ],
  };
  const next = appendPerfectPickAck(message);
  assert.equal(next.blocks[0].content, `Try Heat${PERFECT_PICK_ACK}`);
  assert.deepEqual(next.blocks[1], message.blocks[1]);
  assert.equal(appendPerfectPickAck(null), null);
});

test("appendPerfectPickAck leaves empty-block messages unchanged", () => {
  const empty = { blocks: [] };
  assert.equal(appendPerfectPickAck(empty), empty);
});

test("arrServiceConnected prefers setup checks then feature flags", () => {
  assert.equal(arrServiceConnected({ checks: { radarr: { ok: true } } }, null, "radarr"), true);
  assert.equal(
    arrServiceConnected({}, { arr: { sonarr_configured: true } }, "sonarr"),
    true,
  );
  assert.equal(arrServiceConnected({}, { arr: {} }, "radarr"), false);
});

test("chatErrorMessage scales with diplomat/snark", () => {
  assert.match(chatErrorMessage("timeout", 0.9), /Well, that didn't work/);
  assert.match(chatErrorMessage("timeout", 0.1), /Sorry, I couldn't respond/);
  assert.match(chatErrorMessage("timeout", 0.5), /Curator couldn't respond/);
});

test("isNightOwlHour is true at 23:00 and later", () => {
  assert.equal(isNightOwlHour(new Date("2026-10-27T23:15:00")), true);
  assert.equal(isNightOwlHour(new Date("2026-10-27T22:59:00")), false);
  assert.equal(typeof ADD_FEEDBACK_DISMISS_MS, "number");
});

test("pickStoredThreadId restores or creates the active thread", () => {
  const threads = [{ id: "a" }, { id: "b" }];
  assert.deepEqual(pickStoredThreadId(threads, "a", true), { nextId: "a", create: false });
  assert.deepEqual(pickStoredThreadId(threads, "missing", false), {
    nextId: "a",
    create: false,
  });
  assert.deepEqual(pickStoredThreadId([], "missing", false), { nextId: null, create: true });
});
