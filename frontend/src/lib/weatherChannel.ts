import type { JsParam } from "../api/types";
/**
 * Weather Channel segment player — pure helpers.
 *
 * The server sends only boards with real data (`payload.segments`). This module
 * decides what plays next: "Local on the 8s" at :08 :18 :28 :38 :48 :58, a
 * Warning ahead of everything, a short headline recap between weather pieces
 * (after the bulletin when a Warning is out), and the longer boards in between.
 */

export type WeatherSkyKind = "clear" | "cloudy" | "rain" | "storm" | "snow" | "mixed";

export const LOCAL_ON_THE_8S: readonly string[] = ["current", "overview", "hourly"];
export const LONG_SEGMENTS: readonly string[] = [
  "five_day",
  "alerts",
  "regional",
  "radar",
  "satellite",
  "webcams",
  "almanac",
  "seasonal",
];
/** Weather segments between headline recaps. */
export const RECAP_EVERY = 3;
export const WEATHER_MIN_DWELL_MS = 9_000;
export const WEATHER_MAX_DWELL_MS = 32_000;
export const MAP_DWELL_MS = 12_000;
export const MAP_FRAME_MS = 550;
export const CHYRON_SUMMARY_MS = 60_000;
export const PAYLOAD_POLL_MS = 60_000;

const WMO: Record<number, string> = {
  0: "Clear",
  1: "Mainly clear",
  2: "Partly cloudy",
  3: "Overcast",
  45: "Fog",
  48: "Freezing fog",
  51: "Light drizzle",
  53: "Drizzle",
  55: "Dense drizzle",
  61: "Light rain",
  63: "Rain",
  65: "Heavy rain",
  66: "Freezing rain",
  67: "Freezing rain",
  71: "Light snow",
  73: "Snow",
  75: "Heavy snow",
  80: "Rain showers",
  81: "Rain showers",
  82: "Violent showers",
  85: "Snow showers",
  86: "Heavy snow showers",
  95: "Thunderstorm",
  96: "Thunderstorm with hail",
  99: "Thunderstorm with hail",
};

export function skyFromWeatherCode(code: unknown): { sky: WeatherSkyKind; label: string } {
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

/** Sky painted behind the boards: current conditions, then the first forecast day. */
export function weatherSky(payload: JsParam): WeatherSkyKind {
  const current = payload?.boards?.current;
  if (current && current.code != null) return skyFromWeatherCode(current.code).sky;
  const first = Array.isArray(payload?.boards?.five_day) ? payload.boards.five_day[0] : null;
  return first ? skyFromWeatherCode(first.code).sky : "mixed";
}

export function formatWeatherClock(date = new Date()): string {
  const when = date instanceof Date ? date : new Date();
  let hour = when.getHours();
  const minute = String(when.getMinutes()).padStart(2, "0");
  const suffix = hour >= 12 ? "PM" : "AM";
  hour = hour % 12 || 12;
  return `${hour}:${minute} ${suffix}`;
}

/** Board ids the server says have data, in its order. Empty boards never appear. */
export function availableSegments(payload: JsParam): string[] {
  const rows = Array.isArray(payload?.segments) ? payload.segments : [];
  return rows.map((row: JsParam) => String(row?.id || "")).filter(Boolean);
}

export function segmentLabel(payload: JsParam, id: string): string {
  const rows = Array.isArray(payload?.segments) ? payload.segments : [];
  return String(rows.find((row: JsParam) => row?.id === id)?.label || id);
}

/** The first active Warning (the server sorts Warnings first), or null. */
export function activeWarning(payload: JsParam): JsParam | null {
  const items = payload?.boards?.alerts?.items;
  if (!payload?.boards?.alerts?.supported || !Array.isArray(items)) return null;
  return items.find((item: JsParam) => item?.is_warning) || null;
}

export function isLocalOnThe8s(date: Date): boolean {
  return date.getMinutes() % 10 === 8;
}

export function localSlotKey(date: Date): string {
  return `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}T${date.getHours()}:${date.getMinutes()}`;
}

export type PlannerState = {
  queue: string[];
  cursor: number;
  sinceRecap: number;
  last: string;
  lastLocalSlot: string;
  warningsPlayed: string[];
  recapAfterBulletin: boolean;
};

export function initialPlannerState(): PlannerState {
  return {
    queue: [],
    cursor: 0,
    sinceRecap: 0,
    last: "",
    lastLocalSlot: "",
    warningsPlayed: [],
    recapAfterBulletin: false,
  };
}

function commit(state: PlannerState, segment: string, patch: Partial<PlannerState> = {}) {
  const isWeather = segment !== "headlines";
  return {
    segment,
    state: {
      ...state,
      ...patch,
      last: segment,
      sinceRecap: segment === "headlines" ? 0 : (patch.sinceRecap ?? state.sinceRecap) + (isWeather ? 1 : 0),
    },
  };
}

/**
 * What plays next. Order of precedence:
 * 1. A new Warning (not yet played) jumps every queue.
 * 2. The rest of a "Local on the 8s" block already under way.
 * 3. A fresh :x8 minute (or tune-in) starts the local block.
 * 4. A due headline recap — after the bulletin when a Warning is out.
 * 5. The next longer board in rotation.
 */
export function nextWeatherSegment(
  state: PlannerState,
  payload: JsParam,
  now: Date,
): { segment: string; state: PlannerState } {
  const available = availableSegments(payload);
  if (!available.length) return { segment: "", state };
  const warning = activeWarning(payload);
  const warningId = warning ? String(warning.id || warning.event || "warning") : "";
  if (warningId && available.includes("alerts") && !state.warningsPlayed.includes(warningId)) {
    return commit(state, "alerts", { warningsPlayed: [...state.warningsPlayed, warningId] });
  }

  const queue = state.queue.filter((id) => available.includes(id));
  if (queue.length) {
    return commit(state, queue[0], { queue: queue.slice(1) });
  }

  const slot = localSlotKey(now);
  const local = LOCAL_ON_THE_8S.filter((id) => available.includes(id));
  if (local.length && ((isLocalOnThe8s(now) && slot !== state.lastLocalSlot) || !state.last)) {
    return commit(state, local[0], { queue: local.slice(1), lastLocalSlot: isLocalOnThe8s(now) ? slot : state.lastLocalSlot });
  }

  const recapReady = available.includes("headlines") && state.last !== "headlines";
  if (recapReady && state.recapAfterBulletin && state.last === "alerts") {
    return commit(state, "headlines", { recapAfterBulletin: false });
  }
  if (recapReady && state.sinceRecap >= RECAP_EVERY) {
    if (warningId && available.includes("alerts") && state.last !== "alerts") {
      return commit(state, "alerts", { recapAfterBulletin: true });
    }
    return commit(state, "headlines", { recapAfterBulletin: false });
  }

  const rotation = LONG_SEGMENTS.filter((id) => available.includes(id));
  const pool = rotation.length ? rotation : available.filter((id) => id !== "headlines");
  if (!pool.length) return commit(state, available[0]);
  let cursor = state.cursor % pool.length;
  if (pool.length > 1 && pool[cursor] === state.last) cursor = (cursor + 1) % pool.length;
  return commit(state, pool[cursor], { cursor: cursor + 1 });
}

/** Rotate through the variants of each segment; a new scripts_version starts over. */
export function pickVariant(
  scripts: JsParam,
  segment: string,
  counters: Record<string, number>,
): { variant: JsParam | null; counters: Record<string, number> } {
  const rows = Array.isArray(scripts?.[segment]) ? scripts[segment] : [];
  if (!rows.length) return { variant: null, counters };
  const index = (counters[segment] || 0) % rows.length;
  return { variant: rows[index], counters: { ...counters, [segment]: index + 1 } };
}

/** How long a board stays up when there is no voice to wait for. */
export function captionDwellMs(segment: string, text: string): number {
  const words = String(text || "").split(/\s+/).filter(Boolean).length;
  const reading = Math.round((words / 2.6) * 1000) + 1500;
  const floor = segment === "radar" || segment === "satellite" ? MAP_DWELL_MS : WEATHER_MIN_DWELL_MS;
  return Math.min(WEATHER_MAX_DWELL_MS, Math.max(floor, reading));
}

/** Map loop frame for a moment in time. Reduced motion holds the latest frame. */
export function mapFrameIndex(frameCount: number, elapsedMs: number, reducedMotion: boolean): number {
  if (frameCount <= 0) return 0;
  if (reducedMotion) return frameCount - 1;
  const cycle = frameCount + 2; // hold the newest frame a beat before looping
  const step = Math.floor(Math.max(0, elapsedMs) / MAP_FRAME_MS) % cycle;
  return Math.min(step, frameCount - 1);
}

/** Chyron groups exactly as the server built them (NOW, HOURLY, 5-DAY). Never headlines. */
export function chyronGroups(payload: JsParam): Array<{ group: string; items: string[] }> {
  const rows = Array.isArray(payload?.chyron) ? payload.chyron : [];
  const out: Array<{ group: string; items: string[] }> = [];
  for (const row of rows) {
    const group = String(row?.group || "");
    if (!["NOW", "HOURLY", "5-DAY"].includes(group)) continue;
    const last = out[out.length - 1];
    if (last && last.group === group) last.items.push(String(row.text || ""));
    else out.push({ group, items: [String(row.text || "")] });
  }
  return out;
}

export function alertTimeLabel(iso: unknown): string {
  const when = new Date(String(iso || ""));
  if (Number.isNaN(when.getTime())) return "";
  return when.toLocaleString(undefined, { weekday: "short", hour: "numeric", minute: "2-digit" });
}

export function mapTimeLabel(iso: unknown): string {
  const when = new Date(String(iso || ""));
  if (Number.isNaN(when.getTime())) return "";
  return when.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

export function dayLengthChange(seconds: unknown): string {
  const n = Number(seconds);
  if (!Number.isFinite(n) || n === 0) return "";
  const abs = Math.abs(Math.round(n));
  const minutes = Math.floor(abs / 60);
  const secs = abs % 60;
  const parts = [minutes ? `${minutes}m` : "", secs ? `${secs}s` : ""].filter(Boolean).join(" ");
  return `${parts} ${n < 0 ? "shorter" : "longer"} than yesterday`;
}
