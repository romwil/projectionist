import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import {
  activeWarning,
  availableSegments,
  captionDwellMs,
  chyronGroups,
  initialPlannerState,
  isLocalOnThe8s,
  mapFrameIndex,
  nextWeatherSegment,
  pickVariant,
  RECAP_EVERY,
  skyFromWeatherCode,
  weatherSky,
  WEATHER_MIN_DWELL_MS,
} from "./weatherChannel.ts";

const here = dirname(fileURLToPath(import.meta.url));
const playerSource = () => readFileSync(join(here, "../components/live/WeatherChannelPlayer.tsx"), "utf8");

const ALL = [
  "current",
  "overview",
  "hourly",
  "five_day",
  "regional",
  "radar",
  "almanac",
  "seasonal",
  "headlines",
];

function payload({ segments = ALL, warning = false } = {}) {
  const items = warning
    ? [{ id: "w1", event: "Severe Thunderstorm Warning", is_warning: true, area_short: "Cook" }]
    : [];
  const ids = warning && !segments.includes("alerts") ? [...segments, "alerts"] : segments;
  return {
    segments: ids.map((id) => ({ id, label: id })),
    boards: { current: { code: 61 }, alerts: { supported: true, items } },
    scripts: {},
    chyron: [
      { group: "NOW", text: "NOW 41° Light rain" },
      { group: "HOURLY", text: "11 PM 41°" },
      { group: "HOURLY", text: "1 AM 40°" },
      { group: "5-DAY", text: "THU 52°/38°" },
    ],
  };
}

/** Run the planner from a time, one segment per step, 40s apart. */
function run(data, start, steps, state = initialPlannerState()) {
  const out = [];
  let s = state;
  for (let i = 0; i < steps; i += 1) {
    const next = nextWeatherSegment(s, data, new Date(start.getTime() + i * 40_000));
    s = next.state;
    out.push(next.segment);
  }
  return { out, state: s };
}

describe("weather sky", () => {
  it("maps WMO codes and paints from the current board", () => {
    assert.equal(skyFromWeatherCode(0).sky, "clear");
    assert.equal(skyFromWeatherCode(95).sky, "storm");
    assert.equal(skyFromWeatherCode(73).sky, "snow");
    assert.equal(weatherSky(payload()), "rain");
  });
});

describe("weather segment planner", () => {
  it("plays Local on the 8s at :x8 and starts with it on tune-in", () => {
    assert.equal(isLocalOnThe8s(new Date(2026, 10, 4, 22, 18)), true);
    assert.equal(isLocalOnThe8s(new Date(2026, 10, 4, 22, 19)), false);
    const { out } = run(payload(), new Date(2026, 10, 4, 22, 1), 3);
    assert.deepEqual(out, ["current", "overview", "hourly"]);
  });

  it("starts a fresh local block when the clock reaches :x8", () => {
    const data = payload();
    let { state } = run(data, new Date(2026, 10, 4, 22, 1), 4);
    assert.notEqual(state.last, "current");
    const at8 = nextWeatherSegment(state, data, new Date(2026, 10, 4, 22, 8, 5));
    assert.equal(at8.segment, "current");
    state = at8.state;
    // Same :08 minute again does not restart the block once it has finished.
    const rest = run(data, new Date(2026, 10, 4, 22, 8, 10), 3, state).out;
    assert.deepEqual(rest.slice(0, 2), ["overview", "hourly"]);
    const after = nextWeatherSegment(run(data, new Date(2026, 10, 4, 22, 8, 10), 2, state).state, data, new Date(2026, 10, 4, 22, 8, 50));
    assert.notEqual(after.segment, "current");
  });

  it("skips empty boards: only server segments ever play", () => {
    const data = payload({ segments: ["current", "five_day", "almanac"] });
    const { out } = run(data, new Date(2026, 10, 4, 22, 1), 12);
    for (const seg of out) assert.ok(["current", "five_day", "almanac"].includes(seg), seg);
    assert.ok(!out.includes("radar"));
    assert.ok(!out.includes("headlines"));
    assert.deepEqual(availableSegments({ segments: [] }), []);
    assert.equal(nextWeatherSegment(initialPlannerState(), { segments: [] }, new Date()).segment, "");
  });

  it("puts a headline recap between weather segments", () => {
    const { out } = run(payload(), new Date(2026, 10, 4, 22, 1), 14);
    const first = out.indexOf("headlines");
    assert.equal(first, RECAP_EVERY);
    for (let i = 1; i < out.length; i += 1) {
      if (out[i] === "headlines") assert.notEqual(out[i - 1], "headlines");
    }
    assert.ok(out.filter((s) => s === "headlines").length >= 2);
  });

  it("lets a new Warning jump the queue, once", () => {
    const quiet = payload();
    let { state } = run(quiet, new Date(2026, 10, 4, 22, 1), 1);
    assert.deepEqual(state.queue, ["overview", "hourly"]);
    const stormy = payload({ warning: true });
    assert.equal(activeWarning(stormy).event, "Severe Thunderstorm Warning");
    const next = nextWeatherSegment(state, stormy, new Date(2026, 10, 4, 22, 2));
    assert.equal(next.segment, "alerts");
    const after = nextWeatherSegment(next.state, stormy, new Date(2026, 10, 4, 22, 2, 40));
    assert.equal(after.segment, "overview");
  });

  it("plays the bulletin before the recap while a Warning is out", () => {
    const stormy = payload({ warning: true });
    const { out } = run(stormy, new Date(2026, 10, 4, 22, 1), 16);
    assert.equal(out[0], "alerts");
    const recaps = out.map((s, i) => (s === "headlines" ? i : -1)).filter((i) => i > 0);
    assert.ok(recaps.length >= 1);
    for (const i of recaps) assert.equal(out[i - 1], "alerts", `recap at ${i} follows ${out[i - 1]}`);
  });

  it("does not treat an advisory as a bulletin", () => {
    const data = payload({ segments: [...ALL, "alerts"] });
    data.boards.alerts.items = [{ id: "a1", event: "Wind Advisory", is_warning: false }];
    assert.equal(activeWarning(data), null);
    assert.equal(run(data, new Date(2026, 10, 4, 22, 1), 1).out[0], "current");
  });
});

describe("variants, dwell, maps, chyron", () => {
  it("rotates voiceover variants per segment", () => {
    const scripts = { current: [{ text: "a" }, { text: "b" }, { text: "c" }] };
    let counters = {};
    const seen = [];
    for (let i = 0; i < 4; i += 1) {
      const pick = pickVariant(scripts, "current", counters);
      counters = pick.counters;
      seen.push(pick.variant.text);
    }
    assert.deepEqual(seen, ["a", "b", "c", "a"]);
    assert.equal(pickVariant(scripts, "radar", {}).variant, null);
  });

  it("holds caption-only boards long enough to read", () => {
    assert.equal(captionDwellMs("current", "short"), WEATHER_MIN_DWELL_MS);
    const long = Array.from({ length: 60 }, () => "word").join(" ");
    assert.ok(captionDwellMs("current", long) > WEATHER_MIN_DWELL_MS);
  });

  it("stops the radar loop under reduced motion on the latest frame", () => {
    assert.equal(mapFrameIndex(6, 0, true), 5);
    assert.equal(mapFrameIndex(6, 99_999, true), 5);
    assert.equal(mapFrameIndex(6, 0, false), 0);
    assert.equal(mapFrameIndex(6, 550 * 3, false), 3);
    assert.equal(mapFrameIndex(0, 1000, false), 0);
  });

  it("keeps the chyron weather-only", () => {
    const data = payload();
    data.chyron.push({ group: "HEADLINES", text: "Something happened" });
    const groups = chyronGroups(data);
    assert.deepEqual(
      groups.map((g) => g.group),
      ["NOW", "HOURLY", "5-DAY"],
    );
    assert.deepEqual(groups[1].items, ["11 PM 41°", "1 AM 40°"]);
    assert.ok(!JSON.stringify(groups).includes("Something happened"));
  });
});

describe("WeatherChannelPlayer source", () => {
  it("never falls back to browser speech synthesis", () => {
    const player = playerSource();
    assert.doesNotMatch(player, /speechSynthesis|SpeechSynthesisUtterance/);
    assert.match(player, /audio_url/);
    assert.match(player, /weather-caption/);
  });

  it("drives a shuffled music bed and says when there is no soundtrack", () => {
    const player = playerSource();
    assert.match(player, /WeatherMusicBed/);
    assert.match(player, /payload\?\.music\?\.tracks/);
    assert.match(player, /no soundtrack|muzak_note/i);
    assert.match(player, /voiceStart/);
    assert.match(player, /voiceEnd/);
  });

  it("mounts the weather boards through TheaterPlayer", () => {
    const player = playerSource();
    assert.match(player, /import TheaterPlayer from "\.\.\/theater\/TheaterPlayer"/);
    assert.match(player, /<TheaterPlayer/);
    assert.match(player, /data-testid="weather-channel-muzak"/);
    assert.doesNotMatch(player, /new Hls\(/);
  });

  it("announces warnings assertively and lists egress hosts", () => {
    const player = playerSource();
    assert.match(player, /aria-live="assertive"/);
    assert.match(player, /payload\?\.egress/);
    assert.match(player, /weather-chyron-summary/);
  });
});
