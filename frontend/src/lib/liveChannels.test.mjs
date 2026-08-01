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
  OSD_IDLE_MS,
  popoutHandoff,
  programCellStyle,
  shouldBumpOsdFromPointerMove,
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

  it("ignores zero-delta pointer moves so OSD can auto-hide", () => {
    assert.ok(OSD_IDLE_MS >= 2000);
    const first = shouldBumpOsdFromPointerMove(null, { clientX: 120, clientY: 80 });
    assert.equal(first.bump, true);
    assert.deepEqual(first.pos, { x: 120, y: 80 });

    // Same coords as when an overlay vanishes under a still cursor.
    const stuck = shouldBumpOsdFromPointerMove(first.pos, { clientX: 120, clientY: 80 });
    assert.equal(stuck.bump, false);
    assert.deepEqual(stuck.pos, { x: 120, y: 80 });

    const moved = shouldBumpOsdFromPointerMove(stuck.pos, { clientX: 121, clientY: 80 });
    assert.equal(moved.bump, true);
    assert.deepEqual(moved.pos, { x: 121, y: 80 });
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

  it("OSD keeps flex honest and surfaces next episode as Up next", () => {
    const osd = buildOsdModel(
      {
        id: "59bc2df4-eca9-4ab8-9012-c42ffec358be",
        number: 105,
        name: "Gilligan's Island",
        now: {
          title: "Gilligan's Island · Up next",
          episode_title: "The Big Gold Strike", // stolen label must not win
          content_rating: "TV-G",
          is_flex: true,
          started_at: 1000,
          ends_at: 2800,
        },
        next: {
          title: "Gilligan's Island",
          episode_title: "The Big Gold Strike",
          start: 2800,
        },
      },
      2000 * 1000,
    );
    assert.equal(osd.isFlex, true);
    assert.equal(osd.title, "Gilligan's Island · Up next");
    assert.equal(osd.episode, "Up next: The Big Gold Strike");
    assert.equal(osd.rating, "");
    assert.equal(osd.nextTitle, "Gilligan's Island");
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
