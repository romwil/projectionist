import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";

import {
  PLEX_PIN_POLL_INTERVAL_MS,
  plexPinPollDelayMs,
  plexPinPollSucceeded,
  startPlexPinPoll,
} from "./plexPinPoll.js";

const here = dirname(fileURLToPath(import.meta.url));

describe("plex PIN poll", () => {
  it("checks immediately, then about once a second", () => {
    assert.equal(PLEX_PIN_POLL_INTERVAL_MS, 1000);
    assert.ok(PLEX_PIN_POLL_INTERVAL_MS <= 1000);
    assert.equal(plexPinPollDelayMs(0), 0);
    assert.equal(plexPinPollDelayMs(1), 1000);
    assert.equal(plexPinPollDelayMs(4), 1000);
    assert.equal(plexPinPollDelayMs(Number.NaN), 0);
    assert.equal(plexPinPollDelayMs("nope"), 0);
  });

  it("treats only a linked payload as done", () => {
    const user = { id: "plex-1", display_name: "Will" };
    assert.equal(plexPinPollSucceeded({ authenticated: true, pending: false, user }), true);
    assert.equal(plexPinPollSucceeded({ authenticated: true, pending: false }), false);
    assert.equal(plexPinPollSucceeded({ authenticated: false, pending: true }), false);
    assert.equal(plexPinPollSucceeded(null), false);
    assert.equal(plexPinPollSucceeded("<script>alert(1)</script>"), false);
    assert.equal(plexPinPollSucceeded({ authorized: true }, { peek: true }), true);
    assert.equal(plexPinPollSucceeded({ authorized: false, pending: true }, { peek: true }), false);
    assert.equal(plexPinPollSucceeded({ authenticated: true, user }, { peek: true }), false);
  });

  it("stops on the first linked response and does not poll again", async () => {
    const delays = [];
    const queued = [];
    let now = 5_000;
    const payloads = [
      { authenticated: false, pending: true },
      { authenticated: true, pending: false },
      { authenticated: true, pending: false, user: { id: "plex-1" } },
      { authenticated: true, pending: false, user: { id: "late" } },
    ];
    const successes = [];
    startPlexPinPoll({
      poll: async () => payloads.shift(),
      onSuccess: (result) => successes.push(result),
      onTimeout: () => successes.push("timeout"),
      onError: (error) => successes.push(String(error)),
      deadline: now + 60_000,
      now: () => now,
      schedule: (fn, ms) => {
        delays.push(ms);
        queued.push(fn);
        return queued.length;
      },
      clear: () => {},
    });

    assert.deepEqual(delays, [0]);
    await queued[0]();
    assert.equal(successes.length, 0);
    await queued[1]();
    assert.equal(successes.length, 0);
    assert.deepEqual(delays, [0, 1000, 1000]);
    await queued[2]();
    assert.equal(successes.length, 1);
    assert.equal(successes[0].user.id, "plex-1");
    assert.equal(queued.length, 3);
    assert.equal(payloads.length, 1);
  });

  it("leaves the peek wait on the first authorized response", async () => {
    const queued = [];
    const successes = [];
    startPlexPinPoll({
      peek: true,
      deadline: 10_000,
      now: () => 1_000,
      poll: async () => ({ authorized: true, pending: false, authenticated: true, bound: false }),
      onSuccess: (result) => successes.push(result),
      schedule: (fn, ms) => {
        assert.equal(ms, 0);
        queued.push(fn);
        return 1;
      },
      clear: () => {},
    });
    await queued[0]();
    assert.equal(successes.length, 1);
    assert.equal(successes[0].authorized, true);
    assert.equal(queued.length, 1);
  });

  it("is what login, join, and profile use", () => {
    for (const rel of [
      "../pages/LoginPage.jsx",
      "../pages/JoinPage.jsx",
      "../pages/settings/ProfilePage.jsx",
    ]) {
      const source = readFileSync(join(here, rel), "utf8");
      assert.match(source, /startPlexPinPoll/);
      assert.doesNotMatch(source, /PIN_POLL_MS\s*=\s*(?:[5-9]\d{3}|\d{5,})/);
      assert.doesNotMatch(source, /setTimeout\([\s\S]{0,400}pollPlexPinLogin/);
    }
  });
});
