import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  adjacentChannelId,
  buildOsdModel,
  classifyLiveStreamHealth,
  formatClock,
  isHlsBufferStallDetail,
  isLivePlayerChromeTarget,
  LIVE_CC_EMPTY_AIRING,
  LIVE_CC_EMPTY_STREAM,
  LIVE_STALL_ESCALATE_MS,
  liveGuideHref,
  liveProgramKey,
  liveStreamUrl,
  liveWatchHref,
  mergeLiveCcTracks,
  normalizeGuide,
  OSD_IDLE_MS,
  pickNowAndNext,
  popoutHandoff,
  programAiringBounds,
  programCellStyle,
  recordLivePlaybackDiag,
  shouldBumpOsdFromPointerMove,
  summarizeLiveVideoBuffer,
  toggleLiveVideoPlayback,
  tryPlayLiveVideo,
} from "./liveChannels.js";

describe("liveChannels helpers", () => {
  it("merges stream + Plex CC tracks with honest empty copy", () => {
    const empty = mergeLiveCcTracks([], null);
    assert.equal(empty.hasAny, false);
    assert.equal(empty.emptyMessage, LIVE_CC_EMPTY_STREAM);

    const airing = mergeLiveCcTracks([], {
      plex_streams: [],
      plex_rating_key: null,
      empty_message: LIVE_CC_EMPTY_AIRING,
      can_download: false,
    });
    assert.equal(airing.emptyMessage, LIVE_CC_EMPTY_AIRING);

    const merged = mergeLiveCcTracks(
      [{ index: 0, label: "English", language: "en" }],
      {
        plex_streams: [
          {
            id: "9",
            label: "English (SDH)",
            language_code: "en",
            proxy_url: "/api/library/items/1/subtitles/9/file",
          },
        ],
        can_download: false,
        plex_rating_key: "1",
      },
    );
    assert.equal(merged.hasAny, true);
    assert.equal(merged.streamTracks.length, 1);
    assert.equal(merged.plexTracks.length, 1);
    assert.equal(merged.plexTracks[0].proxyUrl.includes("/subtitles/9/file"), true);
    assert.equal(merged.emptyMessage, "");
  });

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

  it("classifies mid-watch buffering vs stalled without masking tune/pause", () => {
    assert.equal(
      classifyLiveStreamHealth({ playbackStatus: "loading", waiting: true }),
      "ok",
    );
    assert.equal(
      classifyLiveStreamHealth({ playbackStatus: "paused", waiting: true }),
      "ok",
    );
    assert.equal(
      classifyLiveStreamHealth({ playbackStatus: "playing", waiting: true, waitingMs: 500 }),
      "buffering",
    );
    assert.equal(
      classifyLiveStreamHealth({
        playbackStatus: "playing",
        waiting: true,
        waitingMs: LIVE_STALL_ESCALATE_MS,
      }),
      "stalled",
    );
    assert.equal(
      classifyLiveStreamHealth({
        playbackStatus: "playing",
        hlsBufferStalled: true,
      }),
      "stalled",
    );
    assert.equal(
      classifyLiveStreamHealth({
        playbackStatus: "playing",
        playheadFrozen: true,
      }),
      "stalled",
    );
    assert.ok(isHlsBufferStallDetail("bufferStalledError"));
    assert.ok(isHlsBufferStallDetail("bufferNudgeOnStall"));
    assert.equal(isHlsBufferStallDetail("fragLoadError"), false);
  });

  it("summarizes buffered ranges and records a diag ring", () => {
    const video = {
      readyState: 2,
      networkState: 2,
      currentTime: 12.3456,
      paused: false,
      ended: false,
      muted: false,
      buffered: {
        length: 1,
        start: () => 10,
        end: () => 14.5,
      },
    };
    assert.deepEqual(summarizeLiveVideoBuffer(video), {
      readyState: 2,
      networkState: 2,
      currentTime: 12.346,
      paused: false,
      ended: false,
      muted: false,
      buffered: [{ start: 10, end: 14.5 }],
    });

    globalThis.__projectionistLiveDiag = [];
    const logs = [];
    const entry = recordLivePlaybackDiag(
      "video-waiting",
      { channelId: "c1", mediaUrl: "/api/live-channels/stream/c1/index.m3u8" },
      { sink: { info: (...args) => logs.push(args) }, ringMax: 2 },
    );
    assert.equal(entry.event, "video-waiting");
    assert.equal(entry.channelId, "c1");
    assert.match(logs[0][0], /live-playback/);
    recordLivePlaybackDiag("a", {}, { sink: null, ringMax: 2 });
    recordLivePlaybackDiag("b", {}, { sink: null, ringMax: 2 });
    recordLivePlaybackDiag("c", {}, { sink: null, ringMax: 2 });
    assert.equal(globalThis.__projectionistLiveDiag.length, 2);
    assert.equal(globalThis.__projectionistLiveDiag[1].event, "c");
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
    assert.equal(osd.episode, "Up next: Gilligan's Island — The Big Gold Strike");
    assert.equal(osd.rating, "");
    assert.equal(osd.nextTitle, "Gilligan's Island");
    assert.equal(osd.nextDisplay, "Gilligan's Island — The Big Gold Strike");
  });

  it("pickNowAndNext advances past EOF Dora to MythBusters", () => {
    const nowSec = 1_700_000_100;
    const dora = {
      title: "Dora the Explorer",
      episode: "Dora Saves the Prince",
      start: nowSec - 1800,
      stop: nowSec + 600,
      durationSeconds: 1800,
      rating: "TV-Y",
    };
    const myth = {
      title: "MythBusters",
      start: nowSec - 60,
      stop: nowSec + 3600,
      durationSeconds: 3600,
    };
    const bounds = programAiringBounds(dora);
    assert.equal(bounds.stop, nowSec);
    const slots = pickNowAndNext([dora, myth], nowSec);
    assert.equal(slots.now.title, "MythBusters");
    assert.equal(slots.next, null);

    const osd = buildOsdModel(
      {
        id: "chaos",
        number: 102,
        name: "CHAOS",
        // Stale snapshot still claims Dora is now.
        now: {
          title: "Dora the Explorer",
          episode_title: "Dora Saves the Prince",
          started_at: dora.start,
          ends_at: dora.stop,
          content_rating: "TV-Y",
        },
        next: { title: "MythBusters", start: myth.start },
        programs: [dora, myth],
      },
      nowSec * 1000,
    );
    assert.equal(osd.title, "MythBusters");
    assert.ok(osd.secondsRemaining > 0);
    assert.notEqual(osd.title, "Dora the Explorer");
  });

  it("guide click selects MythBusters for OSD when prior slot is dead", () => {
    const nowSec = 1_700_000_100;
    const dora = {
      title: "Dora the Explorer",
      episode: "Dora Saves the Prince",
      start: nowSec - 1800,
      stop: nowSec + 600,
      durationSeconds: 1800,
    };
    const myth = {
      title: "MythBusters",
      start: nowSec + 30,
      stop: nowSec + 3630,
    };
    const slots = pickNowAndNext([dora, myth], nowSec, { selectedProgram: myth });
    assert.equal(slots.now.title, "MythBusters");
    assert.equal(liveProgramKey("chaos", myth), `chaos:${myth.start}:MythBusters`);

    const osd = buildOsdModel(
      {
        id: "chaos",
        number: 102,
        name: "CHAOS",
        now: {
          title: "Dora the Explorer",
          episode_title: "Dora Saves the Prince",
          started_at: dora.start,
          ends_at: dora.stop,
        },
        next: { title: "MythBusters", start: myth.start },
        programs: [dora, myth],
      },
      nowSec * 1000,
      { selectedProgram: myth },
    );
    assert.equal(osd.title, "MythBusters");
    assert.equal(osd.secondsElapsed, 0);
    assert.equal(osd.nextTitle, "");
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
