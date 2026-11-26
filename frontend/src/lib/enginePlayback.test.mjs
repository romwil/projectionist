import assert from "node:assert/strict";
import test from "node:test";

import {
  browserPlaybackProfile,
  browserPlaybackProfileFromRuntime,
  HEVC_PROBE_TYPES,
  chooseWebPlayback,
  engineSessionForPlayer,
  isSafariUserAgent,
  playThroughProjectionist,
  safariReportsHdr,
  enginePlaybackClock,
  settleEngineFirstFrame,
} from "./enginePlayback.ts";

test("the household switch defaults the web player to the Plex path", async () => {
  let engineCalls = 0;
  const played = await chooseWebPlayback({
    features: { features: { play_through_projectionist: false } },
    openEngine: async () => {
      engineCalls += 1;
      return { playable: true, master_url: "/engine", plan: "remux" };
    },
    startPlex: async () => ({ stream_url: "/plex", engine: false }),
  });
  assert.equal(engineCalls, 0);
  assert.equal(played.stream_url, "/plex");
  assert.equal(playThroughProjectionist(null), false);
});

test("just for me uses the engine while the household switch stays off", async () => {
  let engineCalls = 0;
  const played = await chooseWebPlayback({
    features: {
      features: { play_through_projectionist: false, play_through_just_for_me: true },
    },
    openEngine: async () => {
      engineCalls += 1;
      return { playable: true, master_url: "/engine", plan: "remux" };
    },
    startPlex: async () => ({ stream_url: "/plex", engine: false }),
  });
  assert.equal(engineCalls, 1);
  assert.equal(played.stream_url, "/engine");
});

test("a playable remux uses the engine master and keeps the Plex path for captions", async () => {
  const profile = browserPlaybackProfile(
    (type) => type.includes("avc1") || type.includes("mp4a.40.2"),
  );
  assert.deepEqual(
    profile.video.map((item) => item.codec),
    ["h264"],
  );
  assert.equal(profile.audio.includes("ac3"), false);

  const engine = await chooseWebPlayback({
    features: { features: { play_through_projectionist: true } },
    openEngine: async () => ({
      playable: true,
      master_url: "/api/playback/sessions/s/token/master.m3u8",
      plan: "remux",
      session_id: "s",
    }),
    startPlex: async () => {
      throw new Error("plex should not start");
    },
  });
  assert.equal(engine.engine, true);
  assert.equal(engine.stream_url, "/api/playback/sessions/s/token/master.m3u8");

  const fallback = await chooseWebPlayback({
    features: { features: { play_through_projectionist: true } },
    openEngine: async () => ({
      playable: false,
      master_url: "",
      plan: "plex-fallback",
      reason: "Captions stay on the Plex path until they are tracks in the playlist.",
    }),
    startPlex: async () => ({ stream_url: "/plex", engine: false }),
  });
  assert.equal(fallback.stream_url, "/plex");
  assert.equal(engineSessionForPlayer({ playable: false, plan: "audio", master_url: "" }), null);
});

test("a playable audio plan uses the engine and a source transcode stays on the library path", async () => {
  const audio = await chooseWebPlayback({
    features: { features: { play_through_projectionist: true } },
    openEngine: async () => ({
      playable: true,
      master_url: "/api/playback/sessions/s/token/master.m3u8",
      plan: "audio",
      session_id: "s",
      reason:
        "H.264 video is playable on web; E-AC-3 audio is not, so the audio is transcoded (eac3 not in profile)",
    }),
    startPlex: async () => {
      throw new Error("a playable audio plan must not start the library path");
    },
  });
  assert.equal(audio.engine, true);
  assert.equal(audio.stream_url, "/api/playback/sessions/s/token/master.m3u8");

  let plex = 0;
  const source = await chooseWebPlayback({
    features: { features: { play_through_projectionist: true } },
    openEngine: async () => ({
      playable: false,
      master_url: "",
      plan: "source-transcode",
      source_reason: "level",
      provider: "plex",
      session_id: "s",
      reason: "HEVC video is not playable on web (hevc level is above profile hevc 5.1)",
    }),
    startPlex: async () => {
      plex += 1;
      return { stream_url: "/plex", engine: false };
    },
  });
  assert.equal(plex, 1);
  assert.equal(source.stream_url, "/plex");
  assert.equal(source.engine, false);
  assert.equal(
    engineSessionForPlayer({ playable: false, plan: "source-transcode", master_url: "" }),
    null,
  );
});

test("the profile lists HEVC, AV1, AC-3, E-AC-3, and 10-bit only when the check says yes", () => {
  const safari = browserPlaybackProfile(
    (type) =>
      type.includes("hvc1.1.6.L153.B0") ||
      type.includes("hvc1.2.4.L153.B0") ||
      type.includes("av01.0.13M.08") ||
      type.includes("ac-3") ||
      type.includes("ec-3") ||
      type.includes("avc1.640034"),
  );
  const hevc = safari.video.find((item) => item.codec === "hevc");
  assert.equal(hevc.max_level, "5.1");
  assert.equal(hevc.bit_depth, 10);
  assert.equal(
    safari.video.some((item) => item.codec === "av1" && item.bit_depth === 8),
    true,
  );
  assert.equal(safari.audio.includes("ac3"), true);
  assert.equal(safari.audio.includes("eac3"), true);
  assert.equal(safari.id, "web");
  assert.deepEqual(safari.containers, ["mp4", "hls-fmp4"]);

  const low = browserPlaybackProfile(
    (type) => type.includes("hvc1.1.6.L93.B0") || type.includes("avc1"),
  );
  const lowHevc = low.video.find((item) => item.codec === "hevc");
  assert.equal(lowHevc.max_level, "3.1");
  assert.equal(lowHevc.bit_depth, 8);

  const chrome = browserPlaybackProfile((type) => type.includes("avc1"));
  assert.equal(
    chrome.video.some((item) => item.codec === "hevc"),
    false,
  );
  assert.equal(
    chrome.video.some((item) => item.codec === "av1"),
    false,
  );
  assert.equal(chrome.audio.includes("eac3"), false);
  assert.equal(chrome.audio.includes("ac3"), false);
  assert.equal(chrome.audio.includes("flac"), false);
  assert.equal(chrome.audio.includes("opus"), false);
  assert.equal(chrome.audio.includes("alac"), false);
});

test("a 10-bit yes does not hide an 8-bit yes at a higher level", () => {
  const profile = browserPlaybackProfile(
    (type) => type.includes("hvc1.2.4.L93.B0") || type.includes("hvc1.1.6.L153.B0"),
  );
  const hevc = profile.video.filter((item) => item.codec === "hevc");
  assert.deepEqual(
    hevc.map((item) => ({ max_level: item.max_level, bit_depth: item.bit_depth })),
    [
      { max_level: "3.1", bit_depth: 10 },
      { max_level: "5.1", bit_depth: 8 },
    ],
  );
});

test("maybe on an unspecified hvc1 family does not claim Main 5.1", async () => {
  const family = await browserPlaybackProfileFromRuntime({
    canPlayType: (type) =>
      type.includes('codecs="hvc1"') && !type.includes("hvc1.") ? "maybe" : "",
  });
  assert.equal(
    family.video.some((item) => item.codec === "hevc"),
    false,
  );

  const named = browserPlaybackProfile((type) => type.includes("hvc1.1.6.L153.B0"));
  const row = named.video.find((item) => item.codec === "hevc");
  assert.equal(row.max_level, "5.1");
  assert.equal(row.bit_depth, 8);

  const tenBit = browserPlaybackProfile((type) => type.includes("hvc1.2.4.L153.B0"));
  const deep = tenBit.video.find((item) => item.codec === "hevc");
  assert.equal(deep.max_level, "5.1");
  assert.equal(deep.bit_depth, 10);
});

test("canPlayType, MediaSource, and decodingInfo are the same profile", async () => {
  const safari = await browserPlaybackProfileFromRuntime({
    canPlayType: (type) =>
      type.includes("hvc1.2.4.L153.B0") || type.includes("ec-3") || type.includes("avc1.640034")
        ? "probably"
        : "",
    isTypeSupported: () => false,
    decodingInfo: async () => ({ supported: false }),
  });
  assert.equal(safari.video.find((item) => item.codec === "hevc").bit_depth, 10);
  assert.equal(safari.audio.includes("eac3"), true);

  const chrome = await browserPlaybackProfileFromRuntime({
    canPlayType: (type) => (type.includes("avc1") ? "probably" : ""),
    isTypeSupported: (type) => type.includes("av01.0.13M.08"),
    decodingInfo: async (type) => ({ supported: type.includes("ac-3") }),
  });
  assert.equal(
    chrome.video.some((item) => item.codec === "hevc"),
    false,
  );
  assert.equal(
    chrome.video.some((item) => item.codec === "av1"),
    true,
  );
  assert.equal(chrome.audio.includes("ac3"), true);
  assert.equal(chrome.audio.includes("eac3"), false);
  assert.equal(chrome.audio.includes("flac"), false);
});

test("an engine session retries the library path once when the first frame never arrives", async () => {
  const logs = [];
  let libraryStarts = 0;
  let engineStops = 0;
  const startLibrary = async () => {
    libraryStarts += 1;
    return { stream_url: "/plex", engine: false, session_id: "library" };
  };
  const stopEngine = async () => {
    engineStops += 1;
  };
  const log = (reason) => logs.push(reason);

  const stillFlowing = await settleEngineFirstFrame({
    elapsedMs: 15000,
    videoWidth: 0,
    readyState: 0,
    fatalError: "",
    segmentBytes: 250000,
    playheadSeconds: 0,
    quietMs: 400,
    retried: false,
    startLibrary,
    stopEngine,
    log,
  });
  assert.equal(libraryStarts, 0);
  assert.equal(stillFlowing.retried, false);
  assert.equal(stillFlowing.session, null);

  const timedOut = await settleEngineFirstFrame({
    elapsedMs: 10000,
    videoWidth: 0,
    readyState: 0,
    fatalError: "",
    segmentBytes: 0,
    playheadSeconds: 0,
    quietMs: 10000,
    retried: false,
    startLibrary,
    stopEngine,
    log,
  });
  assert.equal(libraryStarts, 1);
  assert.equal(engineStops, 1);
  assert.equal(timedOut.retried, true);
  assert.equal(timedOut.session.stream_url, "/plex");
  assert.match(logs[0], /no progress for 10 seconds/);

  const secondTimeout = await settleEngineFirstFrame({
    elapsedMs: 16000,
    videoWidth: 0,
    readyState: 0,
    fatalError: "",
    retried: timedOut.retried,
    startLibrary,
    stopEngine,
    log,
  });
  assert.equal(libraryStarts, 1);
  assert.equal(engineStops, 1);
  assert.equal(secondTimeout.session, null);
  assert.equal(logs.length, 1);

  const fatal = await settleEngineFirstFrame({
    elapsedMs: 200,
    videoWidth: 0,
    readyState: 0,
    fatalError: "manifestLoadError",
    retried: false,
    startLibrary,
    stopEngine,
    log,
  });
  assert.equal(libraryStarts, 2);
  assert.equal(engineStops, 2);
  assert.equal(fatal.retried, true);
  assert.equal(fatal.session.stream_url, "/plex");
  assert.match(logs[1], /failed before the first frame: manifestLoadError/);

  const secondFatal = await settleEngineFirstFrame({
    elapsedMs: 200,
    videoWidth: 0,
    readyState: 0,
    fatalError: "manifestLoadError",
    retried: fatal.retried,
    startLibrary,
    stopEngine,
    log,
  });
  assert.equal(libraryStarts, 2);
  assert.equal(engineStops, 2);
  assert.equal(secondFatal.session, null);

  const playing = await settleEngineFirstFrame({
    elapsedMs: 9000,
    videoWidth: 1918,
    readyState: 4,
    fatalError: "",
    retried: false,
    startLibrary,
    stopEngine,
    log,
  });
  assert.equal(libraryStarts, 2);
  assert.equal(playing.session, null);
  assert.equal(playing.retried, false);
});

test("segments that are still arriving keep the engine session, and ten seconds with no bytes and no playhead movement leaves", () => {
  const preparing = enginePlaybackClock({
    state: "preparing",
    sinceCreatedMs: 8000,
    sinceReadyMs: 0,
    videoWidth: 0,
    readyState: 1,
  });
  assert.equal(preparing.fallback, false);

  const failed = enginePlaybackClock({
    state: "failed",
    sinceCreatedMs: 200,
    sinceReadyMs: 0,
    videoWidth: 0,
    readyState: 0,
  });
  assert.equal(failed.fallback, true);
  assert.match(failed.reason, /failed/i);

  const readyEarly = enginePlaybackClock({
    state: "ready",
    sinceCreatedMs: 20000,
    sinceReadyMs: 8000,
    videoWidth: 0,
    readyState: 1,
    segmentBytes: 0,
    playheadSeconds: 0,
  });
  assert.equal(readyEarly.fallback, false);

  const flowing = enginePlaybackClock({
    state: "ready",
    sinceCreatedMs: 40000,
    sinceReadyMs: 16000,
    videoWidth: 0,
    readyState: 1,
    segmentBytes: 1_500_000,
    playheadSeconds: 0,
    quietMs: 500,
  });
  assert.equal(flowing.fallback, false);
  assert.equal(flowing.reason, "");

  const readyLate = enginePlaybackClock({
    state: "ready",
    sinceCreatedMs: 22000,
    sinceReadyMs: 10000,
    videoWidth: 0,
    readyState: 1,
    segmentBytes: 0,
    playheadSeconds: 0,
    quietMs: 10000,
  });
  assert.equal(readyLate.fallback, true);
  assert.match(readyLate.reason, /no progress for 10 seconds/);

  const capped = enginePlaybackClock({
    state: "preparing",
    sinceCreatedMs: 30000,
    sinceReadyMs: 0,
    videoWidth: 0,
    readyState: 0,
  });
  assert.equal(capped.fallback, true);
  assert.match(capped.reason, /30 seconds/);

  const playing = enginePlaybackClock({
    state: "ready",
    sinceCreatedMs: 40000,
    sinceReadyMs: 12000,
    videoWidth: 1280,
    readyState: 4,
  });
  assert.equal(playing.fallback, false);
});

test("FLAC, Opus, and ALAC are included only when the mp4 codec check says yes", async () => {
  const reported = browserPlaybackProfile(
    (type) =>
      type === 'audio/mp4; codecs="flac"' ||
      type === 'audio/mp4; codecs="opus"' ||
      type === 'audio/mp4; codecs="alac"' ||
      type.includes("avc1"),
  );
  assert.deepEqual(reported.audio, ["aac", "flac", "opus", "alac"]);

  const silent = browserPlaybackProfile((type) => type.includes("avc1"));
  assert.deepEqual(silent.audio, ["aac"]);

  // A bare container yes is not the fMP4 codec the remux writes.
  const family = await browserPlaybackProfileFromRuntime({
    canPlayType: (type) => {
      if (
        type === "audio/flac" ||
        type === "audio/opus" ||
        type === "audio/alac" ||
        type === 'audio/ogg; codecs="opus"' ||
        type === 'audio/ogg; codecs="flac"' ||
        type === "audio/mp4"
      ) {
        return "maybe";
      }
      return type.includes("avc1") ? "probably" : "";
    },
    isTypeSupported: (type) => type === "audio/flac" || type === 'audio/webm; codecs="opus"',
    decodingInfo: async (type) => ({ supported: type === "audio/flac" }),
  });
  assert.deepEqual(family.audio, ["aac"]);

  const fromDecoding = await browserPlaybackProfileFromRuntime({
    canPlayType: () => "",
    isTypeSupported: (type) => type === 'audio/mp4; codecs="opus"',
    decodingInfo: async (type) => ({ supported: type === 'audio/mp4; codecs="flac"' }),
  });
  assert.equal(fromDecoding.audio.includes("flac"), true);
  assert.equal(fromDecoding.audio.includes("opus"), true);
  assert.equal(fromDecoding.audio.includes("alac"), false);
  assert.equal(fromDecoding.audio.includes("ac3"), false);
});

test("AAC channel cap is 6 only when the browser proves surround", async () => {
  const stereo = await browserPlaybackProfileFromRuntime({
    canPlayType: (type) => (type.includes("avc1") ? "probably" : ""),
    decodingInfo: async (_type, options) => ({ supported: options?.channels !== "6" }),
  });
  assert.equal(stereo.max_channels, 2);

  const surround = await browserPlaybackProfileFromRuntime({
    canPlayType: () => "",
    decodingInfo: async (_type, options) => ({ supported: options?.channels === "6" }),
  });
  assert.equal(surround.max_channels, 6);
  assert.equal(browserPlaybackProfile(() => false).max_channels, 2);
});

test("a playable try uses the engine playlist", async () => {
  const engine = await chooseWebPlayback({
    features: { features: { play_through_projectionist: true } },
    openEngine: async () => ({
      playable: true,
      master_url: "/api/playback/sessions/s/token/master.m3u8",
      plan: "try",
      session_id: "s",
    }),
    startPlex: async () => {
      throw new Error("a try must play the engine playlist");
    },
  });
  assert.equal(engine.engine, true);
  assert.equal(engine.plan, "try");
  assert.equal(engine.stream_url, "/api/playback/sessions/s/token/master.m3u8");
});

test("safari reports hdr10 only with a high dynamic range display and an HEVC probe", () => {
  assert.equal(safariReportsHdr(true, true), true);
  assert.equal(safariReportsHdr(false, true), false);
  assert.equal(safariReportsHdr(true, false), false);
  assert.equal(
    isSafariUserAgent(
      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    ),
    true,
  );
  assert.equal(
    isSafariUserAgent(
      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/157.0.0.0 Safari/537.36",
    ),
    false,
  );

  const reporting = browserPlaybackProfile(
    (type) => type.includes("hvc1.2.4.L153.B0") || type.includes("avc1"),
    2,
    { hdr: true },
  );
  const hevc = reporting.video.find((row) => row.codec === "hevc");
  assert.deepEqual(hevc.hdr, ["hdr10"]);
  assert.equal(reporting.video.find((row) => row.codec === "h264").hdr, undefined);

  const silent = browserPlaybackProfile(
    (type) => type.includes("hvc1.2.4.L153.B0"),
    2,
    { hdr: false },
  );
  assert.equal(silent.video.find((row) => row.codec === "hevc").hdr, undefined);

  const noHevc = browserPlaybackProfile((type) => type.includes("avc1"), 2, { hdr: true });
  assert.ok(noHevc.video.every((row) => !row.hdr));
});

test("chrome 157 accepts these HEVC strings and rejects bare hvc1, hev1, and L999", () => {
  assert.deepEqual(HEVC_PROBE_TYPES, [
    'video/mp4; codecs="hvc1.2.4.L186.B0"',
    'video/mp4; codecs="hev1.2.4.L186.B0"',
    'video/mp4; codecs="hvc1.1.6.L186.B0"',
    'video/mp4; codecs="hev1.1.6.L186.B0"',
    'video/mp4; codecs="hvc1.2.4.L153.B0"',
    'video/mp4; codecs="hvc1.2.4.L150.B0"',
    'video/mp4; codecs="hvc1.2.4.L120.90"',
    'video/mp4; codecs="hvc1.2.4.L93.B0"',
    'video/mp4; codecs="hvc1.1.6.L153.B0"',
    'video/mp4; codecs="hev1.1.6.L153.B0"',
    'video/mp4; codecs="hvc1.1.6.L120.90"',
    'video/mp4; codecs="hvc1.1.6.L93.B0"',
    'video/mp4; codecs="hev1.1.6.L93.B0"',
  ]);
  const rejected = [
    'video/mp4; codecs="hvc1"',
    'video/mp4; codecs="hev1"',
    'video/mp4; codecs="hvc1.2.4.L999.B0"',
  ];
  for (const type of rejected) {
    assert.equal(HEVC_PROBE_TYPES.includes(type), false);
  }
  const profile = browserPlaybackProfile((type) => HEVC_PROBE_TYPES.includes(type));
  const ten = profile.video.find((row) => row.codec === "hevc" && row.bit_depth === 10);
  const eight = profile.video.find((row) => row.codec === "hevc" && row.bit_depth === 8);
  assert.equal(ten.max_level, "6.2");
  assert.equal(eight.max_level, "6.2");
  const bare = browserPlaybackProfile((type) => rejected.includes(type));
  assert.equal(
    bare.video.some((row) => row.codec === "hevc"),
    false,
  );
});
