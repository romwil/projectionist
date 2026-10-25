import assert from "node:assert/strict";
import test from "node:test";

import {
  activeCueText,
  clampSubtitleDelay,
  cleanCueText,
  formatSubtitleDelay,
  liveProgramClockSec,
  needsTextSubtitleFetch,
  normalizeSubtitleTracks,
  parseCueTimestamp,
  parseVtt,
  plexBurnInChipLabel,
  plexBurnInFallbackTracks,
  preferredPickableSubtitle,
  resolvePlaySubtitleTracks,
  resolveSubtitlePresentation,
  silenceNativeTextTracks,
  stepSubtitleDelay,
  subtitleLookupTimeSec,
} from "./subtitleCues.js";

const VTT = `WEBVTT

00:00:01.000 --> 00:00:03.000
Hello <i>there</i>

00:00:02.500 --> 00:00:04.000 align:middle
General Kenobi
second line

01:00:00.000 --> 01:00:02.000
42
`;

test("parseCueTimestamp handles hours, minutes-only and comma decimals", () => {
  assert.equal(parseCueTimestamp("01:02:03.500"), 3723.5);
  assert.equal(parseCueTimestamp("02:03.500"), 123.5);
  assert.equal(parseCueTimestamp("00:00:01,250"), 1.25);
  assert.ok(Number.isNaN(parseCueTimestamp("nope")));
});

test("parseVtt strips markup, ignores cue settings, keeps numeric-only text", () => {
  const cues = parseVtt(VTT);
  assert.equal(cues.length, 3);
  assert.equal(cues[0].text, "Hello there");
  assert.equal(cues[1].text, "General Kenobi\nsecond line");
  assert.equal(cues[2].text, "42");
  assert.equal(cues[2].start, 3600);
});

test("activeCueText finds cues and prefers the latest-started overlap", () => {
  const cues = parseVtt(VTT);
  assert.equal(activeCueText(cues, 0.5), "");
  assert.equal(activeCueText(cues, 1.5), "Hello there");
  assert.equal(activeCueText(cues, 2.75), "General Kenobi\nsecond line");
  assert.equal(activeCueText(cues, 3.5), "General Kenobi\nsecond line");
  assert.equal(activeCueText(cues, 4.0), "");
  assert.equal(activeCueText([], 1), "");
  assert.equal(activeCueText(cues, Number.NaN), "");
});

test("subtitleLookupTimeSec applies seek origin and sync delay", () => {
  assert.equal(subtitleLookupTimeSec({ currentTimeSec: 10, delaySec: 0 }), 10);
  assert.equal(subtitleLookupTimeSec({ currentTimeSec: 10, delaySec: 1.5 }), 8.5);
  assert.equal(subtitleLookupTimeSec({ currentTimeSec: 10, delaySec: -0.5 }), 10.5);
  // 0-based Plex restart: media clock is near 0 but title offset is 10 minutes.
  assert.equal(
    subtitleLookupTimeSec({ currentTimeSec: 0.4, originMs: 600_000, delaySec: 0 }),
    600.4,
  );
  assert.equal(
    subtitleLookupTimeSec({ currentTimeSec: 0.4, originMs: 600_000, delaySec: 1 }),
    599.4,
  );
  assert.ok(Number.isNaN(subtitleLookupTimeSec({ currentTimeSec: Number.NaN })));
});

test("resolveSubtitlePresentation never stacks soft overlay with native tracks", () => {
  assert.deepEqual(resolveSubtitlePresentation({ softTrackSelected: true, softTrackReady: true }), {
    mode: "soft",
    showOverlay: true,
    enableNativeTrack: false,
    disableAllNative: true,
  });
  assert.deepEqual(resolveSubtitlePresentation({ softTrackSelected: true, softTrackReady: false }), {
    mode: "soft-loading",
    showOverlay: false,
    enableNativeTrack: false,
    disableAllNative: true,
  });
  assert.deepEqual(resolveSubtitlePresentation({ nativeTrackIndex: 2 }), {
    mode: "native",
    showOverlay: false,
    enableNativeTrack: true,
    disableAllNative: false,
    nativeTrackIndex: 2,
  });
  assert.deepEqual(resolveSubtitlePresentation({}), {
    mode: "off",
    showOverlay: false,
    enableNativeTrack: false,
    disableAllNative: true,
  });
  // Soft selection wins even if a native index is also set.
  const stacked = resolveSubtitlePresentation({
    softTrackSelected: true,
    softTrackReady: true,
    nativeTrackIndex: 0,
  });
  assert.equal(stacked.mode, "soft");
  assert.equal(stacked.enableNativeTrack, false);
  assert.equal(stacked.disableAllNative, true);
  // Burn-in never keeps an overlay, even if a text track is also selected.
  const burned = resolveSubtitlePresentation({
    burnInSelected: true,
    softTrackSelected: true,
    softTrackReady: true,
  });
  assert.equal(burned.mode, "burn");
  assert.equal(burned.showOverlay, false);
  assert.equal(burned.enableNativeTrack, false);
  assert.equal(burned.disableAllNative, true);
});

test("silenceNativeTextTracks disables every TextTrack mode", () => {
  const tracks = [{ mode: "showing" }, { mode: "hidden" }, { mode: "disabled" }];
  assert.equal(silenceNativeTextTracks({ textTracks: tracks }), 2);
  assert.deepEqual(
    tracks.map((track) => track.mode),
    ["disabled", "disabled", "disabled"],
  );
  assert.equal(silenceNativeTextTracks(null), 0);
});

test("cleanCueText never leaves HTML or ASS overrides", () => {
  assert.equal(cleanCueText("<script>x</script>{\\an8}Hi &amp; bye"), "xHi & bye");
  assert.equal(cleanCueText("a\\Nb"), "a\nb");
});

test("subtitle delay clamps and formats", () => {
  assert.equal(clampSubtitleDelay(99), 30);
  assert.equal(clampSubtitleDelay(-99), -30);
  assert.equal(clampSubtitleDelay("x"), 0);
  assert.equal(formatSubtitleDelay(0), "In sync");
  assert.equal(formatSubtitleDelay(1.5), "+1.5s");
  assert.equal(formatSubtitleDelay(-0.5), "−0.5s");
  assert.equal(stepSubtitleDelay(0, 0.5), 0.5);
  assert.equal(stepSubtitleDelay(0.5, 0.5), 1);
  assert.equal(stepSubtitleDelay(0, -0.5), -0.5);
  assert.equal(stepSubtitleDelay(0, -1), -1);
});

test("iPhone stepper taps change overlay cue offset", () => {
  let delay = 0;
  delay = stepSubtitleDelay(delay, 0.5);
  delay = stepSubtitleDelay(delay, 0.5);
  assert.equal(delay, 1);
  const cues = [{ start: 10, end: 12, text: "English line" }];
  assert.equal(activeCueText(cues, subtitleLookupTimeSec({ currentTimeSec: 10.2, delaySec: 0 })), "English line");
  assert.equal(activeCueText(cues, subtitleLookupTimeSec({ currentTimeSec: 10.2, delaySec: delay })), "");
});

test("overlay cue lookup shifts ±0.5s and ±1s including fetched title time", () => {
  const cues = parseVtt(`WEBVTT

00:00:10.000 --> 00:00:12.000
English line
`);
  const at = (delay) =>
    activeCueText(cues, subtitleLookupTimeSec({ currentTimeSec: 10.2, originMs: 0, delaySec: delay }));
  assert.equal(at(0), "English line");
  assert.equal(at(0.5), "");
  assert.equal(at(-0.5), "English line");
  assert.equal(
    activeCueText(cues, subtitleLookupTimeSec({ currentTimeSec: 0.4, originMs: 10_000, delaySec: 0 })),
    "English line",
  );
  assert.equal(
    activeCueText(cues, subtitleLookupTimeSec({ currentTimeSec: 0.4, originMs: 10_000, delaySec: 1 })),
    "",
  );
});

test("normalizeSubtitleTracks omits undrawable image tracks and keeps English text", () => {
  const tracks = normalizeSubtitleTracks([
    { id: "9001", label: "English (SRT)", language_code: "eng", proxy_url: "/api/library/items/1/subtitles/9001/file", renderable: true },
    { id: "9003", label: "Français", language_code: "fra", proxy_url: "", renderable: false, unavailable_reason: "picture-based" },
    { id: "9004", label: "English", language_code: "eng", proxy_url: "", renderable: false, unavailable_reason: "picture-based" },
  ]);
  assert.equal(tracks.length, 1);
  assert.equal(tracks[0].index, "plex-9001");
  assert.equal(tracks[0].renderable, true);
  assert.ok(!JSON.stringify(tracks).includes("X-Plex-Token"));
  assert.ok(!JSON.stringify(tracks).toLowerCase().includes("can't draw"));
  assert.deepEqual(normalizeSubtitleTracks(null), []);
});

test("undrawable-only title fetches a text track or stays honest Off", () => {
  const pgsOnly = [
    { id: "1", label: "English", language: "English", language_code: "eng", format: "pgs", proxy_url: "", renderable: false, image: true },
    { id: "2", label: "English", language: "English", language_code: "eng", format: "pgs", proxy_url: "", renderable: false, image: true },
  ];
  const listed = resolvePlaySubtitleTracks({ listedStreams: pgsOnly, preferredLanguages: ["en"] });
  assert.equal(listed.needsFetch, true);
  assert.equal(listed.empty, true);
  assert.equal(listed.autoSelectIndex, -1);
  assert.equal(listed.tracks.length, 0);
  assert.equal(listed.burnInTracks.length, 1);
  assert.equal(listed.burnInTracks[0].label, "English (from Plex)");
  assert.equal(listed.burnInTracks[0].burnIn, true);
  assert.ok(!JSON.stringify(listed.burnInTracks).toLowerCase().includes("can't draw"));
  assert.ok(!JSON.stringify(listed.burnInTracks).toLowerCase().includes("pgs"));

  const afterFail = resolvePlaySubtitleTracks({
    listedStreams: pgsOnly,
    downloadedStreams: pgsOnly,
    preferredLanguages: ["en"],
  });
  assert.equal(afterFail.empty, true);
  assert.equal(afterFail.autoSelectIndex, -1);
  assert.equal(afterFail.tracks.length, 0);
  assert.equal(afterFail.burnInTracks.length, 1);
  assert.equal(afterFail.burnInTracks[0].label, "English (from Plex)");

  const afterFetch = resolvePlaySubtitleTracks({
    listedStreams: pgsOnly,
    downloadedStreams: [
      ...pgsOnly,
      {
        id: "99",
        label: "English",
        language_code: "eng",
        proxy_url: "/api/library/items/1/subtitles/99/file",
        renderable: true,
      },
    ],
    preferredLanguages: ["en"],
  });
  assert.equal(afterFetch.empty, false);
  assert.equal(afterFetch.tracks.length, 1);
  assert.equal(afterFetch.tracks[0].label, "English");
  assert.equal(afterFetch.autoSelectIndex, "plex-99");
  assert.equal(afterFetch.burnInTracks.length, 0);
  assert.equal(needsTextSubtitleFetch(afterFetch.tracks, ["en"]), false);
  assert.equal(preferredPickableSubtitle(afterFetch.tracks, ["en"]).index, "plex-99");
});

test("text VTT present does not require a burn-in chip and never auto-picks burn-in", () => {
  const mixed = resolvePlaySubtitleTracks({
    listedStreams: [
      { id: "10", label: "English", language: "English", language_code: "eng", format: "srt", proxy_url: "/api/library/items/1/subtitles/10/file", renderable: true },
      { id: "11", label: "English", language: "English", language_code: "eng", format: "pgs", proxy_url: "", renderable: false, image: true },
    ],
    preferredLanguages: ["en"],
  });
  assert.equal(mixed.tracks.length, 1);
  assert.equal(mixed.burnInTracks.length, 0);
  assert.equal(mixed.autoSelectIndex, -1);
  assert.equal(mixed.needsFetch, false);
});

test("plex burn-in fallback is one chip per language without overlay text", () => {
  const chips = plexBurnInFallbackTracks(
    [
      { id: "1", language: "English", language_code: "eng", format: "pgs", forced: true, image: true },
      { id: "2", language: "English", language_code: "eng", format: "pgs", image: true },
      { id: "3", language: "Français", language_code: "fra", format: "vobsub", image: true },
    ],
    [{ index: "plex-99", language: "eng", renderable: true }],
  );
  assert.equal(chips.length, 1);
  assert.equal(chips[0].id, "3");
  assert.equal(chips[0].label, "Français (from Plex)");
  assert.equal(plexBurnInChipLabel({ language: "English" }), "English (from Plex)");
  assert.ok(!plexBurnInChipLabel({ language: "English", format: "pgs" }).toLowerCase().includes("can't draw"));
});

test("liveProgramClockSec is wall clock minus program start", () => {
  const osd = { nowProgram: { started_at: 1000 } };
  assert.equal(liveProgramClockSec(osd, 1_000_000 + 90_000), 90);
  assert.equal(liveProgramClockSec(osd, 500_000), 0);
  assert.equal(liveProgramClockSec({ nowProgram: null }, 1), null);
});
