import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  adjacentChannelId,
  buildOsdModel,
  formatClock,
  isLivePlayerChromeTarget,
  liveGuideHref,
  liveStreamUrl,
  liveWatchHref,
  normalizeGuide,
  popoutHandoff,
  programCellStyle,
  toggleLiveVideoPlayback,
  tryPlayLiveVideo,
} from "./liveChannels.js";

describe("liveChannels helpers", () => {
  it("builds auth’d stream + watch hrefs", () => {
    assert.equal(liveStreamUrl("ch-1"), "/api/live-channels/stream/ch-1/index.m3u8");
    assert.equal(liveWatchHref("ch-1"), "/live?channel=ch-1");
    assert.equal(liveWatchHref("ch-1", { popout: true }), "/live/watch?channel=ch-1");
    assert.equal(liveGuideHref("ch-1"), "/live?channel=ch-1&mode=guide");
    assert.deepEqual(popoutHandoff("ch-1"), {
      popoutHref: "/live/watch?channel=ch-1",
      guideHref: "/live?channel=ch-1&mode=guide",
    });
  });

  it("ignores OSD chrome clicks for stage play/pause", () => {
    const button = { closest: (sel) => (String(sel).includes("button") ? button : null) };
    const video = { closest: () => null };
    assert.equal(isLivePlayerChromeTarget(button), true);
    assert.equal(isLivePlayerChromeTarget(video), false);
    assert.equal(isLivePlayerChromeTarget(null), false);
  });

  it("toggles live playback and muted-first autoplay recovery", async () => {
    const playing = {
      paused: false,
      muted: false,
      pause() {
        this.paused = true;
      },
      async play() {
        this.paused = false;
      },
    };
    assert.equal(await toggleLiveVideoPlayback(playing), "paused");
    assert.equal(playing.paused, true);

    const blocked = {
      paused: true,
      muted: false,
      calls: 0,
      pause() {
        this.paused = true;
      },
      async play() {
        this.calls += 1;
        if (this.calls === 1 && !this.muted) throw new Error("autoplay");
        this.paused = false;
      },
    };
    assert.equal(await tryPlayLiveVideo(blocked), "playing");
    assert.equal(blocked.muted, false);
    assert.equal(blocked.paused, false);

    assert.equal(await toggleLiveVideoPlayback(null), "idle");
  });

  it("formats clocks and OSD progress", () => {
    assert.equal(formatClock(65), "1:05");
    assert.equal(formatClock(3725), "1:02:05");
    const osd = buildOsdModel(
      {
        id: "c1",
        number: 101,
        name: "Chaos",
        now: {
          title: "Heat",
          episode_title: "Director’s cut",
          content_rating: "R",
          started_at: 1000,
          ends_at: 4600,
        },
        next: { title: "Ronin", start: 4600 },
      },
      1600 * 1000,
    );
    assert.equal(osd.title, "Heat");
    assert.equal(osd.episode, "Director’s cut");
    assert.equal(osd.secondsElapsed, 600);
    assert.equal(osd.secondsRemaining, 3000);
    assert.ok(osd.percent > 0);
  });

  it("normalizes guide rows with programs", () => {
    const model = normalizeGuide({
      enabled: true,
      ready: true,
      generated_at: 1_700_000_000,
      window_seconds: 7200,
      channels: [
        {
          id: "c1",
          name: "Chaos",
          number: 100,
          programs: [
            { title: "Heat", start: 1_700_000_000, stop: 1_700_003_600, content_rating: "R" },
          ],
        },
      ],
    });
    assert.equal(model.channels.length, 1);
    assert.equal(model.channels[0].programs[0].title, "Heat");
    assert.equal(adjacentChannelId(model.channels, "c1", 1), "c1");
  });

  it("lays out EPG cells inside the window", () => {
    const style = programCellStyle(
      { start: 100, stop: 1900 },
      0,
      3600,
      220,
    );
    assert.match(String(style.left), /px$/);
    assert.match(String(style.width), /px$/);
  });
});
