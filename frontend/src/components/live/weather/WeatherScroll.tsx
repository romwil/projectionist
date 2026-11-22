import { useEffect, useState } from "react";
import { activeWarning } from "../../../lib/weatherChannel";
import {
  AlmanacBoard,
  CurrentBoard,
  FiveDayBoard,
  HeadlinesBoard,
  HourlyBoard,
  RadarBoard,
} from "./WeatherBoards";

type WeatherPayload = Record<string, any>;

const CHIPS = [
  { id: "weather-now", label: "Now" },
  { id: "weather-five-day", label: "5-day" },
  { id: "weather-radar", label: "Radar" },
  { id: "weather-headlines", label: "Headlines" },
  { id: "weather-almanac", label: "Almanac" },
];

function daylightOf(payload: WeatherPayload | null) {
  const day = payload?.boards?.five_day?.[0];
  const almanac = payload?.boards?.almanac;
  if (!day && !almanac) return null;
  return { sunrise: day?.sunrise || almanac?.sunrise, sunset: day?.sunset || almanac?.sunset };
}

/**
 * Under 768px the forecast is one scrolling page. It does not rotate boards.
 */
export default function WeatherScroll({
  payload,
  reducedMotion,
  busy,
  error,
}: {
  payload: WeatherPayload | null;
  reducedMotion: boolean;
  busy?: boolean;
  error?: string;
}) {
  const [radarOn, setRadarOn] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const warning = activeWarning(payload);
  const boards = payload?.boards || {};
  const headlinesOn =
    payload?.headlines?.enabled !== false &&
    (payload?.headlines?.scopes || []).some((scope: any) => (scope.items || []).length);
  const chips = CHIPS.filter((chip) => chip.id !== "weather-headlines" || headlinesOn);

  useEffect(() => {
    if (!radarOn || reducedMotion) return undefined;
    const id = window.setInterval(() => setElapsed((value) => value + 250), 250);
    return () => window.clearInterval(id);
  }, [radarOn, reducedMotion]);

  function jump(id: string) {
    document
      .getElementById(id)
      ?.scrollIntoView({ behavior: reducedMotion ? "auto" : "smooth", block: "start" });
  }

  return (
    <div className="weather-scroll">
      {busy && !payload ? <p className="weather-channel-status">Tuning the forecast…</p> : null}
      {error ? (
        <p className="weather-channel-status weather-channel-status--error">{error}</p>
      ) : null}
      {payload?.error ? <p className="weather-channel-status">{payload.error}</p> : null}
      {warning ? (
        <p className="weather-bulletin-bar" data-testid="weather-bulletin-bar">
          <span className="weather-bulletin-kicker">Weather bulletin</span>
          <span>
            {warning.event} · {warning.area_short}
          </span>
        </p>
      ) : null}
      <section id="weather-now">
        {boards.current ? (
          <CurrentBoard board={boards.current} label="Right now" daylight={daylightOf(payload)} />
        ) : (
          <p className="weather-channel-status">The forecast is still tuning.</p>
        )}
      </section>
      <section id="weather-hourly">
        <HourlyBoard hours={boards.hourly || []} label="Next 12 hours" compact />
      </section>
      <div className="weather-section-chips" data-testid="weather-section-chips">
        {chips.map((chip) => (
          <button key={chip.id} type="button" onClick={() => jump(chip.id)}>
            {chip.label}
          </button>
        ))}
      </div>
      <section id="weather-five-day">
        <FiveDayBoard days={boards.five_day || []} label="5-day" />
      </section>
      {headlinesOn ? (
        <section id="weather-headlines">
          <HeadlinesBoard scopes={payload?.headlines?.scopes || []} label="Headlines" tabs />
        </section>
      ) : null}
      <section id="weather-radar">
        {boards.radar ? (
          <RadarBoard
            radar={boards.radar}
            label="Radar"
            elapsedMs={elapsed}
            reducedMotion={reducedMotion}
            paused
            cities={boards.regional || []}
            onPlay={() => setRadarOn(true)}
          />
        ) : null}
      </section>
      <section id="weather-almanac">
        {boards.almanac ? <AlmanacBoard board={boards.almanac} label="Almanac" /> : null}
      </section>
    </div>
  );
}
