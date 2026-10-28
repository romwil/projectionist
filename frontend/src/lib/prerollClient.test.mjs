import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import {
  bumperPlaySettle,
  bumperReadyPlayGate,
  bumperWatchDecision,
  isLivePrerollAssetUrl,
  livePrerollCueId,
  normalizePrerollPayload,
  playBumperVideo,
  PREROLL_TAP_COPY,
  shouldPlayLivePreroll,
  shouldPlayMoviePreroll,
} from "./prerollClient.ts";

describe("prerollClient", () => {
  it("normalizes next-preroll payloads and rejects empties", () => {
    assert.equal(normalizePrerollPayload(null), null);
    assert.equal(normalizePrerollPayload(undefined), null);
    assert.equal(normalizePrerollPayload({}), null);
    assert.equal(normalizePrerollPayload({ id: "a" }), null);
    const ok = normalizePrerollPayload({
      id: "clip-1",
      url: "/api/preroll/asset/clip-1",
      title: "Bumper",
    });
    assert.equal(ok.id, "clip-1");
    assert.equal(ok.url, "/api/preroll/asset/clip-1");
    assert.equal(ok.title, "Bumper");
  });

  it("skips a bumper that never starts or freezes on the first frame", async () => {
    assert.equal(isLivePrerollAssetUrl("/api/preroll/asset/abc"), true);
    assert.equal(isLivePrerollAssetUrl("/api/library/playback/sess/index.m3u8"), false);
    assert.equal(bumperWatchDecision({ playResult: "playing", currentTime: 1.2, elapsedMs: 200 }), "keep");
    assert.equal(
      bumperWatchDecision({ playResult: "playing", currentTime: 0, elapsedMs: 5000, stallMs: 4000 }),
      "skip",
    );
    assert.equal(bumperWatchDecision({ playResult: "ready", elapsedMs: 200, playTimeoutMs: 6000 }), "gesture");
    assert.equal(bumperWatchDecision({ playResult: "ready", elapsedMs: 7000, playTimeoutMs: 6000 }), "skip");
    assert.equal(bumperWatchDecision({ playResult: "idle", elapsedMs: 7000, playTimeoutMs: 6000 }), "skip");
    assert.equal(bumperWatchDecision({ error: true, playResult: "playing", currentTime: 0 }), "skip");

    const hung = {
      muted: false,
      play() {
        return new Promise(() => {});
      },
    };
    assert.equal(await playBumperVideo(hung, { timeoutMs: 25 }), "idle");
  });

  it("starts one bumper play; skip-while-playing does not abort", () => {
    assert.equal(bumperReadyPlayGate({ playResult: "idle", playInFlight: false }), "start");
    assert.equal(bumperReadyPlayGate({ playResult: "idle", playInFlight: true }), "ignore");
    assert.equal(bumperReadyPlayGate({ playResult: "playing", playInFlight: false }), "ignore");
    assert.equal(bumperReadyPlayGate({ playResult: "ready", playInFlight: false }), "ignore");
    assert.equal(bumperReadyPlayGate({ cancelled: true, playResult: "idle" }), "ignore");

    assert.equal(bumperPlaySettle({ result: "playing", playResult: "idle" }), "playing");
    assert.equal(bumperPlaySettle({ result: "idle", playResult: "playing" }), "playing");
    assert.equal(
      bumperPlaySettle({ result: "idle", playResult: "idle", videoPlaying: true }),
      "playing",
    );
    assert.equal(bumperPlaySettle({ result: "ready", playResult: "playing" }), "playing");
    assert.equal(bumperPlaySettle({ result: "idle", playResult: "idle" }), "skip");
    assert.equal(bumperPlaySettle({ result: "ready", playResult: "idle" }), "gesture");
    assert.equal(bumperPlaySettle({ cancelled: true, result: "idle" }), "ignore");

    const root = dirname(fileURLToPath(import.meta.url));
    const stage = readFileSync(join(root, "../components/theater/PrerollStage.tsx"), "utf8");
    assert.match(stage, /bumperReadyPlayGate/);
    assert.match(stage, /bumperPlaySettle/);
    assert.match(stage, /playInFlight/);
    assert.match(stage, /loadeddata/);
    assert.match(stage, /canplay/);
  });

  it("bumper overlay tap calls video.play(); autoplay-blocked path is not a no-op", async () => {
    assert.match(PREROLL_TAP_COPY, /Tap the picture/);
    const video = {
      muted: false,
      paused: true,
      plays: 0,
      async play() {
        this.plays += 1;
        if (!this.muted) throw new Error("NotAllowedError");
        this.paused = false;
      },
    };
    assert.equal(await playBumperVideo(video), "playing");
    assert.ok(video.plays >= 2, "muted-first recovery must call play() after the block");
    assert.equal(video.muted, false);
    assert.equal(video.paused, false);

    video.paused = true;
    video.muted = false;
    const beforeTap = video.plays;
    assert.equal(await playBumperVideo(video), "playing");
    assert.ok(video.plays > beforeTap, "gesture retry must call video.play()");
    assert.equal(video.paused, false);
  });

  it("gates movie preroll vs episode", () => {
    assert.equal(shouldPlayMoviePreroll({ media_type: "movie" }), true);
    assert.equal(shouldPlayMoviePreroll({ media_type: "episode" }), false);
    assert.equal(shouldPlayMoviePreroll({ media_type: "episode" }, { force: true }), true);
  });

  it("plays a live bumper only when a movie is starting now", () => {
    const start = 1_700_000_000;
    const movie = { title: "Heat", media_type: "movie", start, started_at: start };
    const show = {
      title: "The Office",
      media_type: "show",
      episode_title: "Dinner Party",
      start,
      started_at: start,
    };
    const at = (sec) => sec * 1000;

    assert.equal(
      shouldPlayLivePreroll({ isFlex: false, nowProgram: movie, nextProgram: null }, at(start + 20)),
      true,
    );
    assert.equal(
      shouldPlayLivePreroll({ isFlex: false, nowProgram: movie, nextProgram: null }, at(start + 600)),
      false,
    );
    assert.equal(
      shouldPlayLivePreroll({ isFlex: false, nowProgram: show, nextProgram: null }, at(start + 5)),
      false,
    );
    assert.equal(
      shouldPlayLivePreroll(
        { isFlex: false, nowProgram: { title: "Pilot", media_type: "episode", start } },
        at(start + 5),
      ),
      false,
    );
    assert.equal(shouldPlayLivePreroll({ isFlex: false, nowProgram: { title: "Mystery" } }, at(start)), false);

    const nextStart = start + 3600;
    const nextMovie = { title: "Heat", media_type: "movie", start: nextStart, started_at: nextStart };
    assert.equal(
      shouldPlayLivePreroll(
        { isFlex: true, nowProgram: null, nextProgram: nextMovie, nextStart },
        at(nextStart - 60),
      ),
      false,
      "flex pad in the last 180s is still a pad, not a movie-start bumper",
    );
    assert.equal(
      shouldPlayLivePreroll(
        { isFlex: true, nowProgram: null, nextProgram: nextMovie, nextStart },
        at(nextStart - 120),
      ),
      false,
    );
    assert.equal(
      shouldPlayLivePreroll(
        { isFlex: false, nowProgram: nextMovie, nextProgram: null },
        at(nextStart + 20),
      ),
      true,
    );
    assert.equal(
      shouldPlayLivePreroll(
        { isFlex: true, nowProgram: null, nextProgram: nextMovie, nextStart },
        at(nextStart - 3600),
      ),
      false,
    );
    assert.equal(
      shouldPlayLivePreroll(
        {
          isFlex: true,
          nextProgram: { ...show, start: nextStart, started_at: nextStart },
          nextStart,
        },
        at(nextStart - 30),
      ),
      false,
    );

    const cue = livePrerollCueId(
      { isFlex: false, nowProgram: movie },
      at(start + 15),
    );
    assert.equal(cue, `${start}:Heat`);
    assert.equal(livePrerollCueId({ isFlex: false, nowProgram: show }, at(start + 15)), "");
  });
});
