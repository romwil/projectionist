import assert from "node:assert/strict";
import test from "node:test";

import {
  liveCaptionAiringKey,
  liveCaptionsDefaultTrack,
  mergeLiveCcTracks,
} from "./liveChannels.ts";
import { describeSubtitleBackfill } from "./scheduledTasks.ts";
import {
  playCaptionsDefaultIndex,
  resolvePlaySubtitleTracks,
  titleLanguageIsHousehold,
} from "./subtitleCues.ts";

const CACHED = {
  id: "cached-en",
  label: "English",
  language_code: "en",
  format: "srt",
  proxy_url: "/api/library/items/55/subtitles/cached-en/file",
  renderable: true,
  cached: true,
};
const PGS = { id: "9", language_code: "fra", format: "pgs", proxy_url: "", renderable: false, image: true };

function livePayload(overrides = {}) {
  return {
    plex_streams: [CACHED, PGS],
    preferred_languages: ["en"],
    household_language: "en",
    media_type: "movie",
    original_language: "fr",
    is_flex: false,
    cached_track: CACHED,
    ...overrides,
  };
}

test("title language compares across 2- and 3-letter codes", () => {
  assert.equal(titleLanguageIsHousehold("fr", "en"), false);
  assert.equal(titleLanguageIsHousehold("eng", "en"), true);
  assert.equal(titleLanguageIsHousehold("", "en"), null);
});

test("Play: the cached track is listed immediately without a fetch", () => {
  const resolved = resolvePlaySubtitleTracks({ listedStreams: [CACHED, PGS], preferredLanguages: ["en"] });
  assert.equal(resolved.needsFetch, false);
  assert.equal(resolved.tracks[0].index, "plex-cached-en");
  assert.equal(resolved.autoSelectIndex, -1, "auto-select-after-fetch rule is unchanged");
});

test("Play: a foreign title turns the cached track on; an English title stays off", () => {
  const resolved = resolvePlaySubtitleTracks({ listedStreams: [CACHED], preferredLanguages: ["en"] });
  assert.equal(
    playCaptionsDefaultIndex({ resolved, titleLanguage: "fr", householdLanguage: "en", preferredLanguages: ["en"] }),
    "plex-cached-en",
  );
  assert.equal(
    playCaptionsDefaultIndex({ resolved, titleLanguage: "en", householdLanguage: "en", preferredLanguages: ["en"] }),
    -1,
  );
});

test("Play: an English title stays off even after an on-the-spot fetch", () => {
  const resolved = resolvePlaySubtitleTracks({
    listedStreams: [PGS],
    downloadedStreams: [CACHED],
    preferredLanguages: ["en"],
  });
  assert.equal(resolved.autoSelectIndex, "plex-cached-en");
  assert.equal(
    playCaptionsDefaultIndex({ resolved, titleLanguage: "en", householdLanguage: "en", preferredLanguages: ["en"] }),
    -1,
  );
  assert.equal(
    playCaptionsDefaultIndex({ resolved, titleLanguage: "", householdLanguage: "en", preferredLanguages: ["en"] }),
    "plex-cached-en",
    "unknown language keeps the existing after-fetch rule",
  );
});

test("Live: a French film airing selects the cached track", () => {
  assert.equal(liveCaptionsDefaultTrack(livePayload()), "plex-cached-en");
});

test("Live: an English film and an episode airing stay off but list the file", () => {
  assert.equal(liveCaptionsDefaultTrack(livePayload({ original_language: "en" })), -1);
  const episode = livePayload({ media_type: "episode" });
  assert.equal(liveCaptionsDefaultTrack(episode), -1);
  assert.equal(mergeLiveCcTracks([], episode).plexTracks[0].index, "plex-cached-en");
});

test("Live: flex/filler never turns captions on", () => {
  assert.equal(liveCaptionsDefaultTrack(livePayload({ is_flex: true })), -1);
});

test("Live: turning captions off sticks for that airing only", () => {
  const airing = liveCaptionAiringKey("104", "55", 1700000000);
  const offFor = airing;
  assert.equal(
    liveCaptionsDefaultTrack(livePayload(), { userTurnedOff: offFor === airing }),
    -1,
  );
  const nextAiring = liveCaptionAiringKey("104", "56", 1700007200);
  assert.equal(
    liveCaptionsDefaultTrack(livePayload(), { userTurnedOff: offFor === nextAiring }),
    "plex-cached-en",
  );
});

test("Live: a fetch that finishes during the airing still turns a foreign film on", () => {
  const before = livePayload({ plex_streams: [PGS], cached_track: null });
  assert.equal(liveCaptionsDefaultTrack(before), -1);
  const after = { ...before, downloaded_streams: [CACHED] };
  assert.equal(liveCaptionsDefaultTrack(after), "plex-cached-en");
});

test("Backfill card shows done, remaining, last error, and running state", () => {
  const view = describeSubtitleBackfill({
    state: "running",
    running: true,
    done: 1200,
    remaining: 34,
    last_error: "OpenSubtitles lookup took longer than 45s",
    opensubtitles_configured: false,
  });
  assert.equal(view.active, true);
  assert.equal(view.stateLabel, "Backfill running");
  assert.match(view.progressLine, /1,?200 done · 34 remaining/);
  assert.match(view.errorLine, /longer than 45s/);
  assert.match(view.keyNote, /OpenSubtitles isn’t set up/);
  assert.equal(describeSubtitleBackfill({ state: "done", done: 5, remaining: 0 }).active, false);
});
