import assert from "node:assert/strict";
import test from "node:test";

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import {
  OSD_IDLE_MS,
  RESUME_THRESHOLD_MS,
  SCRUB_MAX,
  SEEK_PICTURE_TIMEOUT_MS,
  SEEK_RESTART_DEBOUNCE_MS,
  SKIP_LONG_SECONDS,
  SKIP_SECONDS,
  canLocalSeekTo,
  capturePlaybackHoldFrame,
  createScrubCommit,
  dispatchPictureTap,
  bottomThirdTapResult,
  centerPlayHoldAfterOsdHide,
  playerClosePlacement,
  longSkipFits,
  pictureTapIntent,
  canResumeAttachedStream,
  clampTime,
  createStageGesture,
  formatClockMs,
  EXPLORE_PATH,
  NEXT_EPISODE_MISSING_MESSAGE,
  NEXT_EPISODE_UNAVAILABLE_MESSAGE,
  libraryWatchPath,
  libraryWatchPopoutPath,
  nextEpisodeEndCardAction,
  runEndCardBackToExplore,
  runNextEpisodeEndCard,
  libraryWatchTo,
  msFromScrubPct,
  playbackSrcForSeek,
  playheadMsFromMedia,
  notePlayingBeforeHide,
  scrubPctFromMs,
  seekTimelineOriginMs,
  shouldRevealPlaybackPicture,
  shouldAutoResumePlayback,
  shouldPauseOnVisibilityHide,
  shouldResumeFromOffset,
  shouldSendProgress,
  skipDeltaForZone,
  skipZoneFromClientX,
  theaterHlsConfig,
  dispatchLibraryPlayKey,
  isPlayShortcutBlockedTarget,
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

test("library play arrows seek ±15 and space toggles unless typing", () => {
  const calls = [];
  const skipBy = (delta) => calls.push(["skip", delta]);
  const togglePlayback = () => calls.push(["toggle"]);
  function fire(key, target, extra = {}) {
    const event = {
      key,
      target,
      repeat: false,
      ...extra,
      preventDefault() {
        calls.push(["prevent", key]);
      },
    };
    return dispatchLibraryPlayKey(event, { skipBy, togglePlayback });
  }

  assert.equal(fire("ArrowLeft", { tagName: "DIV" }), true);
  assert.equal(fire("ArrowRight", { tagName: "BODY" }), true);
  assert.equal(fire(" ", { tagName: "DIV" }), true);
  assert.deepEqual(calls, [
    ["prevent", "ArrowLeft"],
    ["skip", -SKIP_SECONDS],
    ["prevent", "ArrowRight"],
    ["skip", SKIP_SECONDS],
    ["prevent", " "],
    ["toggle"],
  ]);

  const blocked = [];
  const typingTargets = [
    { tagName: "INPUT", type: "range" },
    { tagName: "INPUT", type: "text" },
    { tagName: "TEXTAREA" },
    { tagName: "SELECT" },
    { tagName: "DIV", isContentEditable: true },
  ];
  for (const target of typingTargets) {
    assert.equal(isPlayShortcutBlockedTarget(target), true);
    const key = target.tagName === "TEXTAREA" || target.isContentEditable ? " " : "ArrowRight";
    const event = {
      key,
      target,
      preventDefault() {
        blocked.push("prevent");
      },
    };
    assert.equal(
      dispatchLibraryPlayKey(event, {
        skipBy: () => blocked.push("skip"),
        togglePlayback: () => blocked.push("toggle"),
      }),
      false,
    );
  }
  assert.deepEqual(blocked, []);

  const alias = [];
  for (const key of ["a", "A", "d", "D", "s", "S"]) {
    dispatchLibraryPlayKey(
      { key, target: { tagName: "DIV" }, preventDefault() {} },
      {
        skipBy: (delta) => alias.push(["skip", delta]),
        togglePlayback: () => alias.push(["toggle"]),
      },
    );
  }
  assert.deepEqual(alias, [
    ["skip", -SKIP_SECONDS],
    ["skip", -SKIP_SECONDS],
    ["skip", SKIP_SECONDS],
    ["skip", SKIP_SECONDS],
    ["toggle"],
    ["toggle"],
  ]);
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

test("Next Episode control opens the in-app watch route", () => {
  const calls = [];
  const messages = [];
  const decision = runNextEpisodeEndCard(
    { rating_key: "ep-2", play_rating_key: "ep-2-play" },
    "ep-1",
    {
      navigate: (path) => calls.push(path),
      onMessage: (message) => messages.push(message),
    },
  );
  assert.equal(decision.action, "play");
  assert.equal(decision.path, "/watch/ep-2-play");
  assert.deepEqual(calls, ["/watch/ep-2-play"]);
  assert.deepEqual(messages, []);
});

test("missing next episode surfaces a message instead of navigating", () => {
  const calls = [];
  const messages = [];
  for (const next of [null, undefined, {}, { rating_key: "  " }, { rating_key: "" }]) {
    const decision = runNextEpisodeEndCard(next, "ep-1", {
      navigate: (path) => calls.push(path),
      onMessage: (message) => messages.push(message),
    });
    assert.equal(decision.action, "message");
    assert.equal(decision.message, NEXT_EPISODE_MISSING_MESSAGE);
  }
  assert.deepEqual(calls, []);
  assert.ok(messages.length >= 1);
  assert.ok(messages.every((message) => message === NEXT_EPISODE_MISSING_MESSAGE));
});

test("Next Episode on the current watch route surfaces a message instead of a no-op", () => {
  const calls = [];
  const messages = [];
  const decision = nextEpisodeEndCardAction({ rating_key: "ep-9" }, "ep-9");
  assert.equal(decision.action, "message");
  assert.equal(decision.message, NEXT_EPISODE_UNAVAILABLE_MESSAGE);
  const ran = runNextEpisodeEndCard({ rating_key: "abc/1" }, "abc/1", {
    navigate: (path) => calls.push(path),
    onMessage: (message) => messages.push(message),
  });
  assert.equal(ran.action, "message");
  assert.deepEqual(calls, []);
  assert.deepEqual(messages, [NEXT_EPISODE_UNAVAILABLE_MESSAGE]);
});

test("Back to Explore opens /explore even when Next Episode cannot start", () => {
  const calls = [];
  const messages = [];
  const next = runNextEpisodeEndCard(null, "ep-1", {
    navigate: (path) => calls.push(path),
    onMessage: (message) => messages.push(message),
  });
  assert.equal(next.action, "message");
  assert.equal(messages[0], NEXT_EPISODE_MISSING_MESSAGE);
  const back = runEndCardBackToExplore({
    navigate: (path) => calls.push(path),
  });
  assert.equal(back.action, "explore");
  assert.equal(back.path, EXPLORE_PATH);
  assert.deepEqual(calls, ["/explore"]);
  const sameRoute = runNextEpisodeEndCard({ rating_key: "ep-9" }, "ep-9", {
    navigate: (path) => calls.push(`next:${path}`),
    onMessage: () => {},
  });
  assert.equal(sameRoute.action, "message");
  runEndCardBackToExplore({ navigate: (path) => calls.push(path) });
  assert.deepEqual(calls, ["/explore", "/explore"]);
});

test("a scrubber burst commits one seek, not one per input", async () => {
  const seeks = [];
  const scrub = createScrubCommit({
    onCommit: (pct) => seeks.push(pct),
    quietMs: 40,
    lostEndMs: 200,
  });
  scrub.begin();
  for (let i = 1; i <= 40; i += 1) scrub.input(i * 10);
  assert.equal(seeks.length, 0, "drag must not seek until release");
  scrub.end();
  assert.deepEqual(seeks, [400]);

  const burst = [];
  const loose = createScrubCommit({
    onCommit: (pct) => burst.push(pct),
    quietMs: 30,
    lostEndMs: 200,
  });
  for (let i = 0; i < 25; i += 1) loose.input(500 + i);
  assert.equal(burst.length, 0);
  await new Promise((resolve) => setTimeout(resolve, 50));
  assert.deepEqual(burst, [524]);
  loose.cancel();
});

test("slider drag previews the time and commits one seek on release", () => {
  const durationMs = 27 * 60 * 1000 + 52 * 1000;
  const commits = [];
  const previews = [];
  const scrub = createScrubCommit({
    onCommit: (pct) => commits.push(msFromScrubPct(pct, durationMs)),
    quietMs: 50,
    lostEndMs: 500,
  });
  scrub.begin();
  for (const pct of [120, 280, 360]) {
    scrub.input(pct);
    previews.push(msFromScrubPct(pct, durationMs));
  }
  assert.equal(commits.length, 0);
  assert.ok(previews[2] > previews[0]);
  assert.equal(previews[2], msFromScrubPct(360, durationMs));
  scrub.end();
  assert.deepEqual(commits, [previews[2]]);
  assert.ok(SEEK_RESTART_DEBOUNCE_MS >= 0);
  assert.ok(SEEK_PICTURE_TIMEOUT_MS >= 1000);
});

test("seek reload changes the playlist src once per committed epoch", () => {
  const base = "/api/library/playback/sess/index.m3u8";
  assert.equal(playbackSrcForSeek(base, 0), base);
  assert.equal(playbackSrcForSeek(base, 1), `${base}?seek=1`);
  assert.equal(playbackSrcForSeek(`${base}?x=1`, 2), `${base}?x=1&seek=2`);
  assert.equal(playbackSrcForSeek("", 3), "");
});

test("held seek does not present the video until a frame can paint", () => {
  assert.equal(shouldRevealPlaybackPicture({ holdingSeek: false, readyState: 0, videoWidth: 0 }), true);
  assert.equal(shouldRevealPlaybackPicture({ holdingSeek: true, readyState: 0, videoWidth: 0 }), false);
  assert.equal(shouldRevealPlaybackPicture({ holdingSeek: true, readyState: 1, videoWidth: 1280 }), false);
  assert.equal(shouldRevealPlaybackPicture({ holdingSeek: true, readyState: 2, videoWidth: 0 }), false);
  assert.equal(shouldRevealPlaybackPicture({ holdingSeek: true, readyState: 2, videoWidth: 16 }), true);
  assert.equal(shouldRevealPlaybackPicture({ holdingSeek: true, readyState: 4, videoWidth: 1920 }), true);
  assert.equal(capturePlaybackHoldFrame(null), "");
  assert.equal(capturePlaybackHoldFrame({ videoWidth: 0, videoHeight: 0 }), "");
});

test("seek playhead follows a 0-based transcoder timeline and copyts", () => {
  const committed = 10 * 60 * 1000 + 11 * 1000;
  assert.equal(seekTimelineOriginMs({ currentTimeSec: 0.4, committedOffsetMs: committed }), committed);
  assert.equal(seekTimelineOriginMs({ currentTimeSec: 611, committedOffsetMs: committed }), 0);
  const origin = seekTimelineOriginMs({ currentTimeSec: 0.2, committedOffsetMs: committed });
  assert.equal(playheadMsFromMedia({ currentTimeSec: 4, originMs: origin }), committed + 4000);
  assert.equal(playheadMsFromMedia({ currentTimeSec: 611.5, originMs: 0 }), 611500);
});

test("Play seek holds the picture instead of the static tuning overlay", () => {
  const root = dirname(fileURLToPath(import.meta.url));
  const player = readFileSync(join(root, "../components/theater/LibraryPlayer.jsx"), "utf8");
  const stage = readFileSync(join(root, "../components/theater/TheaterPlayer.jsx"), "utf8");
  const css = readFileSync(join(root, "../styles/13-watch.css"), "utf8");
  assert.match(player, /playbackSrcForSeek\(session\.stream_url, seekEpoch\)/);
  assert.match(player, /pictureHold=\{pictureHold\}/);
  assert.match(player, /onPictureReady=\{handlePictureReady\}/);
  assert.doesNotMatch(player, /tuning=\{seeking\}/);
  assert.doesNotMatch(player, /\.setPointerCapture/);
  assert.match(stage, /shouldRevealPlaybackPicture/);
  assert.match(stage, /data-picture-hold=\{pictureHold \? "true" : "false"\}/);
  assert.match(css, /\.theater-player-video\[data-picture-hold="true"\]\s*\{\s*visibility:\s*hidden;/);
});

test("bottom third open keeps the normal idle and a second tap hides", () => {
  assert.equal(pictureTapIntent(600, 900), "osd");
  const shown = bottomThirdTapResult({ visibleAtPointerDown: false });
  assert.equal(shown.effect, "show");
  assert.equal(shown.hideAfterMs, OSD_IDLE_MS);
  assert.ok(shown.hideAfterMs > 1000);

  let visible = false;
  let hideAt = null;
  function tap(at, visibleAtPointerDown) {
    const result = bottomThirdTapResult({ visibleAtPointerDown });
    if (result.effect === "show") {
      visible = true;
      hideAt = at + result.hideAfterMs;
      return;
    }
    visible = false;
    hideAt = null;
  }
  function at(t) {
    if (visible && hideAt != null && t >= hideAt) visible = false;
    return visible;
  }

  tap(0, false);
  assert.equal(at(OSD_IDLE_MS - 1), true);
  assert.equal(at(OSD_IDLE_MS), false);

  tap(OSD_IDLE_MS + 10, false);
  tap(OSD_IDLE_MS + 10, true);
  assert.equal(at(OSD_IDLE_MS + 10), false);
});

test("paused center Play outlives the bar by one idle timeout", () => {
  const hold = centerPlayHoldAfterOsdHide({ paused: true });
  assert.equal(hold.visible, true);
  assert.equal(hold.hideAfterMs, OSD_IDLE_MS);
  assert.equal(centerPlayHoldAfterOsdHide({ paused: false }).visible, false);

  let osd = true;
  let center = true;
  let centerHideAt = null;
  function tick(t) {
    if (osd && t >= OSD_IDLE_MS) {
      osd = false;
      const next = centerPlayHoldAfterOsdHide({ paused: true });
      center = next.visible;
      centerHideAt = t + next.hideAfterMs;
    }
    if (!osd && centerHideAt != null && t >= centerHideAt) center = false;
    return { osd, center };
  }

  assert.deepEqual(tick(OSD_IDLE_MS - 1), { osd: true, center: true });
  assert.deepEqual(tick(OSD_IDLE_MS), { osd: false, center: true });
  assert.deepEqual(tick(OSD_IDLE_MS + hold.hideAfterMs - 1), { osd: false, center: true });
  assert.deepEqual(tick(OSD_IDLE_MS + hold.hideAfterMs), { osd: false, center: false });
});

test("Close sits on the player bar and not in More", () => {
  const place = playerClosePlacement();
  assert.equal(place.onBar, true);
  assert.equal(place.inMoreMenu, false);
  assert.equal(place.label, "Close");
});

test("bottom third toggles the overlay and does not pause", () => {
  assert.equal(pictureTapIntent(0, 900), "toggle");
  assert.equal(pictureTapIntent(599, 900), "toggle");
  assert.equal(pictureTapIntent(600, 900), "osd");
  assert.equal(pictureTapIntent(899, 900), "osd");

  const calls = [];
  const bottom = dispatchPictureTap({
    offsetY: 800,
    height: 900,
    togglePlayback: () => calls.push("pause"),
    toggleOsd: () => calls.push("osd"),
  });
  assert.equal(bottom, "osd");
  assert.deepEqual(calls, ["osd"]);

  calls.length = 0;
  const upper = dispatchPictureTap({
    offsetY: 200,
    height: 900,
    togglePlayback: () => calls.push("pause"),
    toggleOsd: () => calls.push("osd"),
  });
  assert.equal(upper, "playback");
  assert.deepEqual(calls, ["pause"]);
});

test("long skip is ±30 only in wide landscape", () => {
  assert.equal(SKIP_LONG_SECONDS, 30);
  assert.equal(SKIP_SECONDS, 15);
  assert.equal(longSkipFits({ width: 1024, height: 768 }), true);
  assert.equal(longSkipFits({ width: 1180, height: 820 }), true);
  assert.equal(longSkipFits({ width: 768, height: 1024 }), false);
  assert.equal(longSkipFits({ width: 844, height: 390 }), false);
  assert.equal(longSkipFits({ width: 390, height: 844 }), false);
  assert.equal(longSkipFits({ width: 0, height: 0 }), false);
});
