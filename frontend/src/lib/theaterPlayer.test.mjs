import assert from "node:assert/strict";
import test from "node:test";

import {
  RESUME_THRESHOLD_MS,
  SCRUB_MAX,
  SEEK_RESTART_DEBOUNCE_MS,
  SKIP_SECONDS,
  canLocalSeekTo,
  canResumeAttachedStream,
  clampTime,
  createStageGesture,
  formatClockMs,
  libraryWatchPath,
  libraryWatchPopoutPath,
  libraryWatchTo,
  msFromScrubPct,
  notePlayingBeforeHide,
  scrubPctFromMs,
  shouldAutoResumePlayback,
  shouldPauseOnVisibilityHide,
  shouldResumeFromOffset,
  shouldSendProgress,
  skipDeltaForZone,
  skipZoneFromClientX,
  theaterHlsConfig,
  theaterKeyAction,
  toggleTheaterFullscreen,
  isDocumentFullscreen,
} from "./theaterPlayer.js";

test("libraryWatchPath encodes the rating key", () => {
  assert.equal(libraryWatchPath("plex-949"), "/watch/plex-949");
  assert.equal(libraryWatchPath("abc/1"), "/watch/abc%2F1");
  assert.equal(libraryWatchPath(""), "");
  assert.equal(libraryWatchPopoutPath("9"), "/watch/9/popout");
});

test("seek restart debounce is short but non-zero", () => {
  assert.ok(SEEK_RESTART_DEBOUNCE_MS >= 100);
  assert.ok(SEEK_RESTART_DEBOUNCE_MS <= 500);
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

test("scrub pct ↔ ms mapping is stable at ends and mid", () => {
  assert.equal(scrubPctFromMs(0, 120_000), 0);
  assert.equal(scrubPctFromMs(60_000, 120_000), SCRUB_MAX / 2);
  assert.equal(scrubPctFromMs(120_000, 120_000), SCRUB_MAX);
  assert.equal(scrubPctFromMs(999, 0), 0);
  assert.equal(msFromScrubPct(0, 120_000), 0);
  assert.equal(msFromScrubPct(SCRUB_MAX / 2, 120_000), 60_000);
  assert.equal(msFromScrubPct(SCRUB_MAX, 120_000), 120_000);
  assert.equal(msFromScrubPct(SCRUB_MAX + 50, 120_000), 120_000);
  assert.equal(msFromScrubPct(-10, 120_000), 0);
  assert.equal(msFromScrubPct(500, 0), 0);
  // Round-trip mid-point
  assert.equal(msFromScrubPct(scrubPctFromMs(45_000, 90_000), 90_000), 45_000);
});

test("canLocalSeekTo requires a buffered range covering the target", () => {
  assert.equal(canLocalSeekTo(null, 10), false);
  assert.equal(canLocalSeekTo({ buffered: { length: 0 } }, 10), false);
  const video = {
    buffered: {
      length: 1,
      start: () => 0,
      end: () => 30,
    },
  };
  assert.equal(canLocalSeekTo(video, 10), true);
  assert.equal(canLocalSeekTo(video, 30), true);
  assert.equal(canLocalSeekTo(video, 31), false);
  assert.equal(canLocalSeekTo(video, Number.NaN), false);
});

test("theaterKeyAction maps J/K/L and Minecraft A/S/D aliases", () => {
  assert.equal(theaterKeyAction(" "), "toggle");
  assert.equal(theaterKeyAction("k"), "toggle");
  assert.equal(theaterKeyAction("K"), "toggle");
  assert.equal(theaterKeyAction("s"), "toggle");
  assert.equal(theaterKeyAction("S"), "toggle");
  assert.equal(theaterKeyAction("j"), "skipBack");
  assert.equal(theaterKeyAction("a"), "skipBack");
  assert.equal(theaterKeyAction("A"), "skipBack");
  assert.equal(theaterKeyAction("ArrowLeft"), "skipBack");
  assert.equal(theaterKeyAction("l"), "skipForward");
  assert.equal(theaterKeyAction("d"), "skipForward");
  assert.equal(theaterKeyAction("D"), "skipForward");
  assert.equal(theaterKeyAction("ArrowRight"), "skipForward");
  assert.equal(theaterKeyAction("m"), "mute");
  assert.equal(theaterKeyAction("c"), "captions");
  assert.equal(theaterKeyAction("f"), "fullscreen");
  assert.equal(theaterKeyAction("Escape"), "escape");
  assert.equal(theaterKeyAction("x"), null);
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

test("pause-on-hide is opt-in only; default keeps playing", () => {
  assert.equal(
    shouldPauseOnVisibilityHide({ pauseWhenBackgrounded: false, visibilityState: "hidden" }),
    false,
  );
  assert.equal(
    shouldPauseOnVisibilityHide({ pauseWhenBackgrounded: true, visibilityState: "hidden" }),
    true,
  );
  assert.equal(
    shouldPauseOnVisibilityHide({ pauseWhenBackgrounded: true, visibilityState: "visible" }),
    false,
  );
});

test("visibility hide remembers wasPlaying; visible resumes only when remembered", () => {
  assert.equal(notePlayingBeforeHide({ playing: true, visibilityState: "hidden" }), true);
  assert.equal(notePlayingBeforeHide({ playing: false, visibilityState: "hidden" }), false);
  assert.equal(notePlayingBeforeHide({ playing: true, visibilityState: "visible" }), null);
  assert.equal(shouldAutoResumePlayback({ wasPlaying: true, visibilityState: "visible" }), true);
  assert.equal(shouldAutoResumePlayback({ wasPlaying: true, visibilityState: "hidden" }), false);
  assert.equal(shouldAutoResumePlayback({ wasPlaying: false, visibilityState: "visible" }), false);
});

test("canResumeAttachedStream requires stream URL and media src", () => {
  assert.equal(canResumeAttachedStream({ video: { currentSrc: "x" }, streamUrl: "" }), false);
  assert.equal(canResumeAttachedStream({ video: null, streamUrl: "/api/stream" }), false);
  assert.equal(
    canResumeAttachedStream({ video: { currentSrc: "", src: "" }, streamUrl: "/api/stream" }),
    false,
  );
  assert.equal(
    canResumeAttachedStream({ video: { currentSrc: "blob:1" }, streamUrl: "/api/stream" }),
    true,
  );
  assert.equal(
    canResumeAttachedStream({ video: { currentSrc: "", src: "blob:2" }, streamUrl: "/api/stream" }),
    true,
  );
});

test("toggleTheaterFullscreen uses immersive CSS when requestFullscreen is missing", () => {
  const root = {
    classList: {
      _set: new Set(),
      contains(name) {
        return this._set.has(name);
      },
      add(name) {
        this._set.add(name);
      },
      remove(name) {
        this._set.delete(name);
      },
    },
  };
  assert.equal(isDocumentFullscreen(), false);
  assert.equal(toggleTheaterFullscreen(root), "immersive");
  assert.equal(root.classList.contains("theater-player--immersive"), true);
  assert.equal(toggleTheaterFullscreen(root), "exit");
  assert.equal(root.classList.contains("theater-player--immersive"), false);
  assert.equal(toggleTheaterFullscreen(null), "noop");
});
