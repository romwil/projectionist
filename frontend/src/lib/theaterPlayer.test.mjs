import assert from "node:assert/strict";
import test from "node:test";

import {
  RESUME_THRESHOLD_MS,
  SKIP_SECONDS,
  clampTime,
  createStageGesture,
  formatClockMs,
  libraryWatchPath,
  libraryWatchPopoutPath,
  libraryWatchTo,
  shouldResumeFromOffset,
  shouldSendProgress,
  skipDeltaForZone,
  skipZoneFromClientX,
  theaterHlsConfig,
} from "./theaterPlayer.js";

test("libraryWatchPath encodes the rating key", () => {
  assert.equal(libraryWatchPath("plex-949"), "/watch/plex-949");
  assert.equal(libraryWatchPath("abc/1"), "/watch/abc%2F1");
  assert.equal(libraryWatchPath(""), "");
  assert.equal(libraryWatchPopoutPath("9"), "/watch/9/popout");
});

test("libraryWatchTo carries return state", () => {
  assert.deepEqual(libraryWatchTo("99", { pathname: "/chat", search: "" }), {
    pathname: "/watch/99",
    state: { from: "/chat" },
  });
  assert.deepEqual(
    libraryWatchTo("99", { pathname: "/title/movie/1", search: "", state: { from: "/explore" } }),
    { pathname: "/watch/99", state: { from: "/explore" } },
  );
});

test("skip-zone math splits left / center / right thirds", () => {
  assert.equal(skipZoneFromClientX(10, 300), "left");
  assert.equal(skipZoneFromClientX(150, 300), "center");
  assert.equal(skipZoneFromClientX(290, 300), "right");
  assert.equal(skipZoneFromClientX(99, 300), "left");
  assert.equal(skipZoneFromClientX(101, 300), "center");
  assert.equal(skipZoneFromClientX(199, 300), "center");
  assert.equal(skipZoneFromClientX(201, 300), "right");
  assert.equal(skipZoneFromClientX("x", 0), "center");
  assert.equal(skipDeltaForZone("left"), -SKIP_SECONDS);
  assert.equal(skipDeltaForZone("right"), SKIP_SECONDS);
  assert.equal(skipDeltaForZone("center"), 0);
});

test("resume gate is 2 minutes", () => {
  assert.equal(shouldResumeFromOffset(0), false);
  assert.equal(shouldResumeFromOffset(119_999), false);
  assert.equal(shouldResumeFromOffset(RESUME_THRESHOLD_MS), true);
  assert.equal(shouldResumeFromOffset(10 * 60 * 1000), true);
  assert.equal(shouldResumeFromOffset("nope"), false);
});

test("progress throttle is 10 seconds", () => {
  assert.equal(shouldSendProgress(null, 1000), true);
  assert.equal(shouldSendProgress(1000, 10_999), false);
  assert.equal(shouldSendProgress(1000, 11_000), true);
});

test("formatClockMs is living-room readable", () => {
  assert.equal(formatClockMs(0), "0:00");
  assert.equal(formatClockMs(65_000), "1:05");
  assert.equal(formatClockMs(3_661_000), "1:01:01");
});

test("theaterHlsConfig uses credentialed XHR (session cookies on proxy)", () => {
  const cfg = theaterHlsConfig();
  assert.equal(cfg.enableWorker, false);
  assert.equal(typeof cfg.xhrSetup, "function");
  const xhr = { withCredentials: false };
  cfg.xhrSetup(xhr);
  assert.equal(xhr.withCredentials, true);
});

test("clampTime stays inside duration", () => {
  assert.equal(clampTime(-4, 100), 0);
  assert.equal(clampTime(40, 100), 40);
  assert.equal(clampTime(140, 100), 100);
});

test("stage gesture ignores the click that completes a double-tap", async () => {
  const singles = [];
  const doubles = [];
  const handle = createStageGesture({
    onSingle: () => singles.push(1),
    onDouble: () => doubles.push(1),
    delay: 40,
  });
  handle({});
  handle({});
  await new Promise((resolve) => setTimeout(resolve, 60));
  assert.equal(singles.length, 0);
  assert.equal(doubles.length, 1);

  handle({});
  await new Promise((resolve) => setTimeout(resolve, 60));
  assert.equal(singles.length, 1);
});
