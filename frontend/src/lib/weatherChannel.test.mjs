import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  forecastDayColumns,
  skyFromWeatherCode,
  weatherBoardSequence,
  weatherTickerLines,
  nextWeatherBoardIndex,
  WEATHER_BOARD_DWELL_MS,
} from "./weatherChannel.js";

const daily = {
  time: ["2026-10-02", "2026-10-03", "2026-10-04"],
  temperature_2m_max: [78.2, 71.4, 64],
  temperature_2m_min: [61.1, 55, 48.6],
  weather_code: [0, 3, 95],
  precipitation_probability_max: [10, 40, 80],
};

describe("weatherChannel boards", () => {
  it("maps sky codes to calm theater skies", () => {
    assert.equal(skyFromWeatherCode(0).sky, "clear");
    assert.equal(skyFromWeatherCode(3).sky, "cloudy");
    assert.equal(skyFromWeatherCode(63).sky, "rain");
    assert.equal(skyFromWeatherCode(95).sky, "storm");
    assert.equal(skyFromWeatherCode(95).label, "Thunderstorm");
    assert.equal(skyFromWeatherCode(null).sky, "mixed");
  });

  it("builds one column per returned day with high over low", () => {
    const columns = forecastDayColumns(daily);
    assert.equal(columns.length, 3);
    assert.deepEqual(
      columns.map((col) => col.weekday),
      ["FRI", "SAT", "SUN"],
    );
    assert.equal(columns[0].high, 78);
    assert.equal(columns[0].low, 61);
    assert.equal(columns[0].condition, "Clear");
    assert.equal(columns[2].sky, "storm");
    assert.equal(forecastDayColumns({ time: [] }).length, 0);
    assert.equal(forecastDayColumns(null).length, 0);
  });

  it("ticker keeps humidity and rain chance off the current-temp line", () => {
    const lines = weatherTickerLines({
      current: {
        temperature_2m: 84,
        relative_humidity_2m: 75,
        weather_code: 0,
        wind_speed_10m: 8,
      },
      daily,
    });
    const joined = lines.join(" | ");
    assert.match(joined, /Humidity 75%/);
    assert.match(joined, /FRI rain chance 10%/);
    assert.doesNotMatch(joined, /84/);
    assert.doesNotMatch(joined, /NOW/);
    assert.doesNotMatch(joined, /78/);
  });

  it("flips only when both boards have data", () => {
    const both = weatherBoardSequence({
      current: { temperature_2m: 70, weather_code: 1, wind_speed_10m: 4 },
      daily,
    });
    assert.deepEqual(both, ["now", "ahead"]);
    assert.equal(nextWeatherBoardIndex(0, both), 1);
    assert.equal(nextWeatherBoardIndex(1, both), 0);

    const nowOnly = weatherBoardSequence({
      current: { temperature_2m: 70, weather_code: 2 },
      daily: { time: [] },
    });
    assert.deepEqual(nowOnly, ["now"]);
    assert.equal(nextWeatherBoardIndex(0, nowOnly), 0);

    const aheadOnly = weatherBoardSequence({ current: {}, daily });
    assert.deepEqual(aheadOnly, ["ahead"]);
    assert.ok(WEATHER_BOARD_DWELL_MS >= 8000 && WEATHER_BOARD_DWELL_MS <= 12000);
  });
});