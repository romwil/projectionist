/**
 * Weather Channel boards — current conditions and a days-ahead grid.
 * Uses only fields Open-Meteo already returns. Does not invent days.
 */

/** How long each cable board stays up before the next one. */
export const WEATHER_BOARD_DWELL_MS = 10_000;

const WEEKDAYS = ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"];

/** Mirrors projectionist.theater.weather._WMO. */
const WMO = {
  0: "Clear",
  1: "Mainly clear",
  2: "Partly cloudy",
  3: "Overcast",
  45: "Fog",
  48: "Fog",
  51: "Light drizzle",
  53: "Drizzle",
  55: "Dense drizzle",
  61: "Light rain",
  63: "Rain",
  65: "Heavy rain",
  71: "Light snow",
  73: "Snow",
  75: "Heavy snow",
  80: "Rain showers",
  81: "Rain showers",
  82: "Violent showers",
  95: "Thunderstorm",
};

/**
 * @param {unknown} code
 * @returns {{ sky: "clear"|"cloudy"|"rain"|"storm"|"snow"|"mixed", label: string }}
 */
export function skyFromWeatherCode(code) {
  if (code == null || code === "") return { sky: "mixed", label: "Mixed skies" };
  const n = Number(code);
  if (!Number.isFinite(n)) return { sky: "mixed", label: "Mixed skies" };
  const label = WMO[n] || "Mixed skies";
  if (n === 0 || n === 1) return { sky: "clear", label };
  if (n === 2 || n === 3 || n === 45 || n === 48) return { sky: "cloudy", label };
  if ((n >= 51 && n <= 67) || (n >= 80 && n <= 82)) return { sky: "rain", label };
  if ((n >= 71 && n <= 77) || n === 85 || n === 86) return { sky: "snow", label };
  if (n >= 95) return { sky: "storm", label };
  return { sky: "mixed", label };
}

/**
 * @param {unknown} isoDate
 * @returns {string}
 */
export function forecastWeekday(isoDate) {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(isoDate || "").trim());
  if (!match) return "";
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const date = new Date(Date.UTC(year, month - 1, day));
  if (Number.isNaN(date.getTime())) return "";
  return WEEKDAYS[date.getUTCDay()] || "";
}

/**
 * @param {unknown} current
 */
export function hasCurrentConditions(current) {
  if (!current || typeof current !== "object") return false;
  return (
    current.temperature_2m != null
    || current.weather_code != null
    || current.wind_speed_10m != null
  );
}

/**
 * One column per daily row the payload actually includes.
 * @param {unknown} daily
 */
export function forecastDayColumns(daily) {
  if (!daily || typeof daily !== "object") return [];
  const times = Array.isArray(daily.time) ? daily.time : [];
  const highs = Array.isArray(daily.temperature_2m_max) ? daily.temperature_2m_max : [];
  const lows = Array.isArray(daily.temperature_2m_min) ? daily.temperature_2m_min : [];
  const codes = Array.isArray(daily.weather_code) ? daily.weather_code : [];
  const columns = [];
  for (let i = 0; i < times.length; i += 1) {
    const date = String(times[i] || "").trim();
    if (!date) continue;
    const sky = skyFromWeatherCode(codes[i]);
    const high = Number(highs[i]);
    const low = Number(lows[i]);
    columns.push({
      date,
      weekday: forecastWeekday(date),
      sky: sky.sky,
      condition: sky.label,
      high: Number.isFinite(high) ? Math.round(high) : null,
      low: Number.isFinite(low) ? Math.round(low) : null,
    });
  }
  return columns;
}

/**
 * Crawl copy: humidity and rain chances. Never the current-temperature headline
 * and never the high/low columns (those belong on the days board).
 * @param {object | null | undefined} payload
 * @returns {string[]}
 */
export function weatherTickerLines(payload) {
  const current = payload?.current && typeof payload.current === "object" ? payload.current : {};
  const daily = payload?.daily && typeof payload.daily === "object" ? payload.daily : {};
  const lines = [];
  const humidity = Number(current.relative_humidity_2m);
  if (Number.isFinite(humidity)) lines.push(`Humidity ${Math.round(humidity)}%`);
  const times = Array.isArray(daily.time) ? daily.time : [];
  const precip = Array.isArray(daily.precipitation_probability_max)
    ? daily.precipitation_probability_max
    : [];
  times.forEach((day, i) => {
    const chance = Number(precip[i]);
    if (!Number.isFinite(chance)) return;
    const label = forecastWeekday(day) || String(day || "").trim();
    if (!label) return;
    lines.push(`${label} rain chance ${Math.round(chance)}%`);
  });
  return lines;
}

/**
 * Boards that have something to show. Empty week and empty current are omitted.
 * @param {object | null | undefined} payload
 * @returns {Array<"now"|"ahead">}
 */
export function weatherBoardSequence(payload) {
  const boards = [];
  if (hasCurrentConditions(payload?.current)) boards.push("now");
  if (forecastDayColumns(payload?.daily).length) boards.push("ahead");
  return boards;
}

/**
 * @param {number} index
 * @param {readonly string[]} boards
 */
export function nextWeatherBoardIndex(index, boards) {
  if (!Array.isArray(boards) || boards.length === 0) return 0;
  if (boards.length === 1) return 0;
  const current = Number.isFinite(Number(index)) ? Number(index) : 0;
  return (current + 1) % boards.length;
}

/**
 * Cable NOW-bar clock. Independent of forecast fields.
 * @param {Date} [date]
 */
export function formatWeatherClock(date = new Date()) {
  const when = date instanceof Date ? date : new Date();
  let hour = when.getHours();
  const minute = String(when.getMinutes()).padStart(2, "0");
  const suffix = hour >= 12 ? "PM" : "AM";
  hour = hour % 12 || 12;
  return `${hour}:${minute} ${suffix}`;
}

/**
 * Sky painted behind both boards. Prefers current conditions, then the first day.
 * @param {object | null | undefined} payload
 */
export function weatherSky(payload) {
  const current = payload?.current;
  if (current && typeof current === "object" && current.weather_code != null) {
    return skyFromWeatherCode(current.weather_code).sky;
  }
  const days = forecastDayColumns(payload?.daily);
  return days[0]?.sky || "mixed";
}
