import { useState, type ReactNode, SVGProps } from "react";
import {
  alertTimeLabel,
  dayLengthChange,
  mapFrameIndex,
  mapTimeLabel,
  skyFromWeatherCode,
  type WeatherSkyKind,
} from "../../../lib/weatherChannel";

type Row = Record<string, any>;

export function SkyGlyph({ sky, size = "md" }: { sky: WeatherSkyKind; size?: "sm" | "md" | "lg" }) {
  const common: SVGProps<SVGSVGElement> = {
    viewBox: "0 0 48 48",
    "aria-hidden": true,
    className: `weather-sky-glyph weather-sky-glyph--${sky} weather-sky-glyph--${size}`,
  };
  if (sky === "clear") {
    return (
      <svg {...common}>
        <circle cx="24" cy="24" r="8" />
        <path d="M24 6v6M24 36v6M6 24h6M36 24h6M11 11l4 4M33 33l4 4M37 11l-4 4M15 33l-4 4" />
      </svg>
    );
  }
  if (sky === "storm") {
    return (
      <svg {...common}>
        <path d="M16 30h18a8 8 0 0 0 0-16 10 10 0 0 0-19-2A7 7 0 0 0 16 30z" />
        <path d="M22 32l-4 8h6l-3 7" />
      </svg>
    );
  }
  if (sky === "rain" || sky === "snow") {
    return (
      <svg {...common}>
        <path d="M16 28h18a8 8 0 0 0 0-16 10 10 0 0 0-19-2A7 7 0 0 0 16 28z" />
        {sky === "rain" ? (
          <path d="M18 34l-2 6M24 34l-2 6M30 34l-2 6" />
        ) : (
          <path d="M18 35v2M25 37v2M31 34v2" />
        )}
      </svg>
    );
  }
  return (
    <svg {...common}>
      <path d="M16 30h18a8 8 0 0 0 0-16 10 10 0 0 0-19-2A7 7 0 0 0 16 30z" />
    </svg>
  );
}

function sky(code: unknown) {
  return skyFromWeatherCode(code).sky;
}

function deg(value: unknown) {
  return value == null ? "—" : `${value}°`;
}

/** UV index and air quality stay unwired until the person asks. */
export function AirFactsSlot({
  facts,
}: {
  facts?: { uv_index?: unknown; uv_label?: unknown; aqi?: unknown; aqi_label?: unknown } | null;
}) {
  void facts;
  return null;
}

function minutesOfDay(value: unknown): number | null {
  const text = String(value || "");
  const iso = text.match(/T(\d{2}):(\d{2})/);
  if (iso) return Number(iso[1]) * 60 + Number(iso[2]);
  const clock = text.match(/(\d{1,2}):(\d{2})\s*(AM|PM)/i);
  if (!clock) return null;
  let hour = Number(clock[1]) % 12;
  if (clock[3].toUpperCase() === "PM") hour += 12;
  return hour * 60 + Number(clock[2]);
}

export function DaylightArc({ sunrise, sunset }: { sunrise?: unknown; sunset?: unknown }) {
  const start = minutesOfDay(sunrise);
  const end = minutesOfDay(sunset);
  if (start == null || end == null || end <= start) return null;
  const now = new Date();
  const minute = now.getHours() * 60 + now.getMinutes();
  const along = Math.min(1, Math.max(0, (minute - start) / (end - start)));
  const angle = Math.PI * (1 - along);
  const x = 16 + Math.cos(angle) * 68;
  const y = 78 - Math.sin(angle) * 58;
  return (
    <figure className="weather-daylight" data-testid="weather-daylight-arc">
      <svg viewBox="0 0 160 90" role="img" aria-label={`Daylight from ${sunrise} to ${sunset}`}>
        <path d="M16 78 A64 58 0 0 1 144 78" fill="none" />
        <line x1="16" y1="78" x2="144" y2="78" />
        <circle cx={x} cy={y} r="4" />
      </svg>
      <figcaption>
        <span>{String(sunrise).replace(/^\d{4}-\d{2}-\d{2}T/, "")}</span>
        <span>{String(sunset).replace(/^\d{4}-\d{2}-\d{2}T/, "")}</span>
      </figcaption>
    </figure>
  );
}

export function TemperatureCurve({ hours }: { hours: Row[] }) {
  const temps = hours.map((hour) => Number(hour.temp)).filter((n) => Number.isFinite(n));
  if (temps.length < 2) return null;
  const min = Math.min(...temps);
  const max = Math.max(...temps);
  const span = Math.max(1, max - min);
  const width = 100;
  const height = 36;
  const points = hours
    .map((hour, index) => {
      const temp = Number(hour.temp);
      const x = (index / Math.max(1, hours.length - 1)) * width;
      const y = height - 4 - ((temp - min) / span) * (height - 8);
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");
  return (
    <div className="weather-curve" data-testid="weather-temp-curve">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="none"
        role="img"
        aria-label="Temperature over the next 12 hours"
      >
        <polyline points={points} />
      </svg>
      <div className="weather-rain-bars" aria-hidden="true">
        {hours.map((hour) => (
          <span
            key={hour.time}
            style={{ height: `${Math.max(0, Math.min(100, Number(hour.precip) || 0))}%` }}
          />
        ))}
      </div>
    </div>
  );
}

function sharedRange(days: Row[]) {
  const lows = days.map((day) => Number(day.low)).filter((n) => Number.isFinite(n));
  const highs = days.map((day) => Number(day.high)).filter((n) => Number.isFinite(n));
  if (!lows.length || !highs.length) return null;
  const min = Math.min(...lows);
  const max = Math.max(...highs);
  return { min, span: Math.max(1, max - min) };
}

function Board({ id, label, children }: { id: string; label: string; children: ReactNode }) {
  return (
    <section
      className={`weather-board weather-board--${id}`}
      data-testid={`weather-board-${id}`}
      aria-label={label}
    >
      <h2 className="weather-board-title">{label}</h2>
      {children}
    </section>
  );
}

export function CurrentBoard({
  board,
  label,
  daylight,
}: {
  board: Row;
  label: string;
  daylight?: { sunrise?: unknown; sunset?: unknown } | null;
}) {
  const rows: Array<[string, string]> = [];
  if (board.feels_like != null) rows.push(["Feels like", deg(board.feels_like)]);
  if (board.wind != null) {
    const gusts = board.gusts != null && board.gusts > board.wind ? `, gusts ${board.gusts}` : "";
    rows.push(["Wind", `${board.wind_dir || ""} ${board.wind} mph${gusts}`.trim()]);
  }
  if (board.humidity != null) rows.push(["Humidity", `${board.humidity}%`]);
  if (board.dew_point != null) rows.push(["Dew point", deg(board.dew_point)]);
  if (board.pressure_inhg != null)
    rows.push([
      "Pressure",
      `${board.pressure_inhg.toFixed(2)} in${board.pressure_trend ? ` ${board.pressure_trend}` : ""}`,
    ]);
  if (board.visibility_mi != null) rows.push(["Visibility", `${board.visibility_mi} mi`]);
  return (
    <Board id="current" label={label}>
      <div className="weather-current">
        <div className="weather-current-hero">
          <SkyGlyph sky={sky(board.code)} size="lg" />
          <p className="weather-current-temp" data-testid="weather-channel-now">
            {deg(board.temp)}
          </p>
          <p className="weather-current-sky">{board.sky}</p>
        </div>
        <div className="weather-current-side">
          <div className="weather-instruments" data-testid="weather-instruments">
            {rows.slice(0, 4).map(([name, value]) => (
              <div key={name} className="weather-instrument">
                <span>{name}</span>
                <strong>{value}</strong>
              </div>
            ))}
          </div>
          <DaylightArc sunrise={daylight?.sunrise} sunset={daylight?.sunset} />
          <AirFactsSlot facts={null} />
          {rows.length > 4 ? (
            <dl className="weather-facts">
              {rows.slice(4).map(([name, value]) => (
                <div key={name} className="weather-fact">
                  <dt>{name}</dt>
                  <dd>{value}</dd>
                </div>
              ))}
            </dl>
          ) : null}
        </div>
      </div>
    </Board>
  );
}

export function OverviewBoard({ board, label }: { board: Row; label: string }) {
  return (
    <Board id="overview" label={label}>
      <p className="weather-overview-text">{board.text}</p>
      <ol className="weather-overview-days">
        {(board.days || []).map((day: Row) => (
          <li key={day.date}>
            <span className="weather-col-head">{day.weekday_name}</span>
            <SkyGlyph sky={sky(day.code)} size="sm" />
            <span>{day.sky}</span>
            <span className="weather-hilo">
              {deg(day.high)} / {deg(day.low)}
            </span>
          </li>
        ))}
      </ol>
    </Board>
  );
}

export function HourlyBoard({
  hours,
  label,
  compact = false,
}: {
  hours: Row[];
  label: string;
  compact?: boolean;
}) {
  return (
    <Board id="hourly" label={label}>
      <TemperatureCurve hours={hours} />
      <ol
        className={`weather-hourly-strip${compact ? " weather-hourly-strip--compact" : ""}`}
        data-testid="weather-hourly-strip"
      >
        {hours.map((hour) => (
          <li key={hour.time} className="weather-hour">
            <span className="weather-col-head">{hour.label}</span>
            <SkyGlyph sky={sky(hour.code)} size="sm" />
            <span className="weather-hour-temp">{deg(hour.temp)}</span>
            <span className="weather-precip">{hour.precip != null ? `${hour.precip}%` : ""}</span>
          </li>
        ))}
      </ol>
    </Board>
  );
}

export function FiveDayBoard({ days, label }: { days: Row[]; label: string }) {
  const scale = sharedRange(days);
  return (
    <Board id="five_day" label={label}>
      <ol className="weather-day-grid" data-testid="weather-day-grid">
        {days.map((day) => {
          const low = Number(day.low);
          const high = Number(day.high);
          const bar =
            scale && Number.isFinite(low) && Number.isFinite(high)
              ? {
                  left: `${((low - scale.min) / scale.span) * 100}%`,
                  width: `${Math.max(10, ((high - low) / scale.span) * 100)}%`,
                }
              : null;
          return (
            <li key={day.date} className="weather-day-col" data-testid="weather-day-col">
              <span className="weather-col-head">{day.weekday}</span>
              <SkyGlyph sky={sky(day.code)} />
              <span className="weather-day-sky">{day.sky}</span>
              <span className="weather-range" data-testid="weather-range-bar">
                {bar ? <span className="weather-range-fill" style={bar} /> : null}
              </span>
              <span className="weather-day-high">{deg(day.high)}</span>
              <span className="weather-day-low">{deg(day.low)}</span>
              <span className="weather-precip">
                {day.precip != null ? `${day.precip}% precip` : ""}
              </span>
            </li>
          );
        })}
      </ol>
    </Board>
  );
}

export function AlertsBoard({ items, label }: { items: Row[]; label: string }) {
  return (
    <Board id="alerts" label={label}>
      <ul className="weather-alert-list">
        {items.slice(0, 3).map((alert) => (
          <li
            key={alert.id || alert.event}
            className={`weather-alert${alert.is_warning ? " is-warning" : ""}`}
          >
            <p className="weather-alert-event">
              {alert.event} <span className="weather-alert-severity">{alert.severity}</span>
            </p>
            <p className="weather-alert-area">{alert.area}</p>
            <p className="weather-alert-time">
              {alert.onset ? `From ${alertTimeLabel(alert.onset)}` : ""}
              {alert.ends ? ` until ${alertTimeLabel(alert.ends)}` : ""}
            </p>
            {alert.headline ? <p className="weather-alert-headline">{alert.headline}</p> : null}
            {alert.description ? <p className="weather-alert-text">{alert.description}</p> : null}
            {alert.instruction ? (
              <p className="weather-alert-text weather-alert-do">{alert.instruction}</p>
            ) : null}
            {alert.sender ? <p className="weather-board-source">Source: {alert.sender}</p> : null}
          </li>
        ))}
      </ul>
    </Board>
  );
}

export function RegionalBoard({ cities, label }: { cities: Row[]; label: string }) {
  return (
    <Board id="regional" label={label}>
      <ul className="weather-regional">
        {cities.map((city) => (
          <li key={`${city.name}-${city.region}`} className="weather-regional-row">
            <span className="weather-regional-city">{city.name}</span>
            <SkyGlyph sky={sky(city.code)} size="sm" />
            <span className="weather-regional-sky">{city.sky}</span>
            <span className="weather-regional-temp">{deg(city.temp)}</span>
          </li>
        ))}
      </ul>
    </Board>
  );
}

const HEADLINE_TABS: Record<string, string> = {
  local: "Local",
  national: "National",
  world: "World",
};

export function RadarBoard({
  radar,
  label,
  elapsedMs,
  reducedMotion,
  paused = false,
  cities = [],
  onPlay,
}: {
  radar: Row;
  label: string;
  elapsedMs: number;
  reducedMotion: boolean;
  paused?: boolean;
  cities?: Row[];
  onPlay?: () => void;
}) {
  const frames: Row[] = radar.frames || [];
  const [playing, setPlaying] = useState(!paused && !reducedMotion);
  const [manual, setManual] = useState<number | null>(null);
  const index =
    manual != null
      ? Math.min(manual, Math.max(0, frames.length - 1))
      : mapFrameIndex(frames.length, elapsedMs, reducedMotion || !playing);
  const frame = frames[index] || {};
  const marker = radar.marker || { x: 0.5, y: 0.5 };
  const animating = playing && !reducedMotion;
  return (
    <Board id="radar" label={label}>
      <figure
        className="weather-map"
        data-testid="weather-radar"
        data-frame={index}
        data-animating={animating ? "true" : "false"}
      >
        <div className="weather-map-frame">
          {frames.map((f, i) => (
            <img
              key={f.url}
              src={f.url}
              alt={i === index ? `Radar at ${mapTimeLabel(f.time)}` : ""}
              aria-hidden={i === index ? undefined : true}
              className={`weather-map-img${i === index ? " is-current" : ""}`}
              loading="eager"
            />
          ))}
          <span
            className="weather-map-marker"
            aria-hidden="true"
            style={{ left: `${marker.x * 100}%`, top: `${marker.y * 100}%` }}
          />
        </div>
        <figcaption className="weather-board-source">
          {radar.source} · {mapTimeLabel(frame.time)}
        </figcaption>
        <div className="weather-radar-tools">
          {paused && !playing ? (
            <button
              type="button"
              className="ghost"
              data-testid="weather-radar-play"
              onClick={() => {
                setPlaying(true);
                onPlay?.();
              }}
            >
              Play radar
            </button>
          ) : null}
          {frames.length > 1 ? (
            <input
              className="weather-radar-scrubber"
              type="range"
              min={0}
              max={frames.length - 1}
              value={index}
              aria-label="Radar time"
              data-testid="weather-radar-scrubber"
              onChange={(event) => setManual(Number(event.target.value))}
            />
          ) : null}
          <ul className="weather-radar-legend" aria-label="Radar legend">
            <li>Light</li>
            <li>Moderate</li>
            <li>Heavy</li>
          </ul>
        </div>
        {cities.length ? (
          <ul className="weather-regional weather-radar-obs" aria-label="Regional observations">
            {cities.slice(0, 6).map((city) => (
              <li key={`${city.name}-${city.region}`}>
                <span>{city.name}</span>
                <span>{deg(city.temp)}</span>
              </li>
            ))}
          </ul>
        ) : null}
      </figure>
    </Board>
  );
}

export function SatelliteBoard({ satellite, label }: { satellite: Row; label: string }) {
  return (
    <Board id="satellite" label={label}>
      <figure className="weather-map" data-testid="weather-satellite">
        <div className="weather-map-frame weather-map-frame--square">
          <img
            src={satellite.url}
            alt={`Satellite at ${mapTimeLabel(satellite.time)}`}
            className="weather-map-img is-current"
          />
        </div>
        <figcaption className="weather-board-source">
          {satellite.source} · {mapTimeLabel(satellite.time)}
        </figcaption>
      </figure>
    </Board>
  );
}

export function WebcamsBoard({ cams, label }: { cams: Row[]; label: string }) {
  return (
    <Board id="webcams" label={label}>
      <ul className="weather-webcams">
        {cams.map((cam) => (
          <li key={cam.url}>
            <figure>
              <img src={cam.url} alt={cam.title} />
              <figcaption className="weather-board-source">
                {cam.title} · {mapTimeLabel(cam.time)} · Windy
              </figcaption>
            </figure>
          </li>
        ))}
      </ul>
    </Board>
  );
}

export function AlmanacBoard({ board, label }: { board: Row; label: string }) {
  const moon = board.moon || {};
  return (
    <Board id="almanac" label={label}>
      <dl className="weather-facts weather-facts--wide">
        {board.sunrise ? (
          <div className="weather-fact">
            <dt>Sunrise</dt>
            <dd>{board.sunrise}</dd>
          </div>
        ) : null}
        {board.sunset ? (
          <div className="weather-fact">
            <dt>Sunset</dt>
            <dd>{board.sunset}</dd>
          </div>
        ) : null}
        {board.day_length_min != null ? (
          <div className="weather-fact">
            <dt>Daylight</dt>
            <dd>
              {Math.floor(board.day_length_min / 60)}h {board.day_length_min % 60}m
              <span className="weather-fact-note">
                {dayLengthChange(board.day_length_change_s)}
              </span>
            </dd>
          </div>
        ) : null}
        {moon.name ? (
          <div className="weather-fact">
            <dt>Moon</dt>
            <dd>
              {moon.name}
              <span className="weather-fact-note">{moon.illumination}% lit</span>
            </dd>
          </div>
        ) : null}
        {board.record_high ? (
          <div className="weather-fact">
            <dt>Record high</dt>
            <dd>
              {deg(board.record_high.value)}{" "}
              <span className="weather-fact-note">{board.record_high.year}</span>
            </dd>
          </div>
        ) : null}
        {board.record_low ? (
          <div className="weather-fact">
            <dt>Record low</dt>
            <dd>
              {deg(board.record_low.value)}{" "}
              <span className="weather-fact-note">{board.record_low.year}</span>
            </dd>
          </div>
        ) : null}
      </dl>
      {board.trivia ? <p className="weather-trivia">{board.trivia}</p> : null}
      {board.archive_years ? (
        <p className="weather-board-source">
          Records: Open-Meteo archive, {board.archive_years} years
        </p>
      ) : null}
    </Board>
  );
}

export function SeasonalBoard({ board, label }: { board: Row; label: string }) {
  const season = board.next_season || {};
  return (
    <Board id="seasonal" label={label}>
      <dl className="weather-facts weather-facts--wide">
        {board.uv_index != null ? (
          <div className="weather-fact">
            <dt>UV index</dt>
            <dd>
              {board.uv_index} <span className="weather-fact-note">{board.uv_label}</span>
            </dd>
          </div>
        ) : null}
        {board.aqi != null ? (
          <div className="weather-fact">
            <dt>Air quality</dt>
            <dd>
              {board.aqi} <span className="weather-fact-note">{board.aqi_label}</span>
            </dd>
          </div>
        ) : null}
        {(board.pollen || []).map((p: Row) => (
          <div className="weather-fact" key={p.kind}>
            <dt>{p.kind} pollen</dt>
            <dd>{p.level}</dd>
          </div>
        ))}
        {board.frost ? (
          <div className="weather-fact">
            <dt>Frost, on average</dt>
            <dd>
              Last {board.frost.last_spring} · First {board.frost.first_fall}
            </dd>
          </div>
        ) : null}
        {board.first_snow_by ? (
          <div className="weather-fact">
            <dt>First snow, most years</dt>
            <dd>by {board.first_snow_by}</dd>
          </div>
        ) : null}
        {season.name ? (
          <div className="weather-fact">
            <dt>Next season</dt>
            <dd>
              {season.days} days <span className="weather-fact-note">to the {season.name}</span>
            </dd>
          </div>
        ) : null}
      </dl>
      {(board.holidays || []).map((tie: Row) => (
        <p key={tie.name} className="weather-trivia">
          {tie.kind === "forecast"
            ? `${tie.name}, ${tie.weekday_name}: ${tie.sky}, ${deg(tie.high)} / ${deg(tie.low)}`
            : `${tie.name}: first snow most years arrives by ${tie.first_snow_by}`}
        </p>
      ))}
    </Board>
  );
}

function HeadlineList({ scope }: { scope: Row }) {
  const items = scope.available === false ? [] : scope.items || [];
  return (
    <ul>
      {items.map((item: Row) => (
        <li key={item.title} className="weather-headline">
          <span className="weather-headline-title">{item.title}</span>
          <span className="weather-headline-source">
            {item.source}
            {item.age ? ` · ${item.age}` : ""}
          </span>
        </li>
      ))}
    </ul>
  );
}

export function HeadlinesBoard({
  scopes,
  label,
  tabs = false,
}: {
  scopes: Row[];
  label: string;
  tabs?: boolean;
}) {
  const visible = scopes.filter((scope) => scope.available !== false && (scope.items || []).length);
  const [active, setActive] = useState(String(visible[0]?.scope || "local"));
  if (!visible.length) return null;
  if (tabs) {
    const current = visible.find((scope) => scope.scope === active) || visible[0];
    return (
      <Board id="headlines" label={label}>
        <div
          className="weather-headline-tabs"
          role="tablist"
          aria-label="Headline scopes"
          data-testid="weather-headline-tabs"
        >
          {visible.map((scope) => (
            <button
              key={scope.scope}
              type="button"
              role="tab"
              aria-selected={scope.scope === current.scope}
              onClick={() => setActive(String(scope.scope))}
            >
              {HEADLINE_TABS[scope.scope] || scope.label}
            </button>
          ))}
        </div>
        <section
          className="weather-headline-scope"
          aria-label={`${HEADLINE_TABS[current.scope] || current.label} headlines`}
        >
          <HeadlineList scope={current} />
        </section>
      </Board>
    );
  }
  return (
    <Board id="headlines" label={label}>
      <div className="weather-headlines">
        {visible.map((scope) => (
          <section
            key={scope.scope}
            className="weather-headline-scope"
            aria-label={`${scope.label} headlines`}
          >
            <h3 className="weather-col-head">{HEADLINE_TABS[scope.scope] || scope.label}</h3>
            <HeadlineList scope={scope} />
          </section>
        ))}
      </div>
    </Board>
  );
}
