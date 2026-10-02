import assert from "node:assert/strict";
import test from "node:test";

import {
  activeCueText,
  clampSubtitleDelay,
  cleanCueText,
  formatSubtitleDelay,
  liveProgramClockSec,
  normalizeSubtitleTracks,
  parseCueTimestamp,
  parseVtt,
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

test("activeCueText finds cues and stacks overlaps", () => {
  const cues = parseVtt(VTT);
  assert.equal(activeCueText(cues, 0.5), "");
  assert.equal(activeCueText(cues, 1.5), "Hello there");
  assert.equal(activeCueText(cues, 2.75), "Hello there\nGeneral Kenobi\nsecond line");
  assert.equal(activeCueText(cues, 3.5), "General Kenobi\nsecond line");
  assert.equal(activeCueText(cues, 4.0), "");
  assert.equal(activeCueText([], 1), "");
  assert.equal(activeCueText(cues, Number.NaN), "");
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
});

test("normalizeSubtitleTracks keeps image tracks listed but unavailable, no token fields", () => {
  const tracks = normalizeSubtitleTracks([
    { id: "9001", label: "English (SRT)", language_code: "eng", proxy_url: "/api/library/items/1/subtitles/9001/file", renderable: true },
    { id: "9003", label: "Japanese", language_code: "jpn", proxy_url: "", renderable: false, unavailable_reason: "picture-based" },
  ]);
  assert.equal(tracks[0].index, "plex-9001");
  assert.equal(tracks[0].renderable, true);
  assert.equal(tracks[1].renderable, false);
  assert.equal(tracks[1].unavailableReason, "picture-based");
  assert.ok(!JSON.stringify(tracks).includes("X-Plex-Token"));
  assert.deepEqual(normalizeSubtitleTracks(null), []);
});

test("liveProgramClockSec is wall clock minus program start", () => {
  const osd = { nowProgram: { started_at: 1000 } };
  assert.equal(liveProgramClockSec(osd, 1_000_000 + 90_000), 90);
  assert.equal(liveProgramClockSec(osd, 500_000), 0);
  assert.equal(liveProgramClockSec({ nowProgram: null }, 1), null);
});
