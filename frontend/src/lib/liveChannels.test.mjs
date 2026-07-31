import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  adjacentChannelId,
  buildOsdModel,
  formatClock,
  liveStreamUrl,
  liveWatchHref,
  normalizeGuide,
  programCellStyle,
} from "./liveChannels.js";

describe("liveChannels helpers", () => {
  it("builds auth’d stream + watch hrefs", () => {
    assert.equal(liveStreamUrl("ch-1"), "/api/live-channels/stream/ch-1/index.m3u8");
    assert.equal(liveWatchHref("ch-1"), "/live?channel=ch-1");
    assert.equal(liveWatchHref("ch-1", { popout: true }), "/live/watch?channel=ch-1");
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
