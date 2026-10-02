import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getLiveWeatherChannel } from "../../api/client";
import {
  forecastDayColumns,
  formatWeatherClock,
  hasCurrentConditions,
  nextWeatherBoardIndex,
  skyFromWeatherCode,
  weatherBoardSequence,
  WEATHER_BOARD_DWELL_MS,
  weatherSky,
  weatherTickerLines,
} from "../../lib/weatherChannel.js";
import WeatherLocationPicker from "../weather/WeatherLocationPicker";

function SkyGlyph({ sky }) {
  const common = {
    viewBox: "0 0 48 48",
    "aria-hidden": "true",
    className: `weather-sky-glyph weather-sky-glyph--${sky}`,
  };
  if (sky === "clear") {
    return (
      <svg {...common}>
        <circle cx="24" cy="24" r="8" />
        <g strokeWidth="2" strokeLinecap="round">
          <path d="M24 6v6M24 36v6M6 24h6M36 24h6M11 11l4 4M33 33l4 4M37 11l-4 4M15 33l-4 4" />
        </g>
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
          <g strokeWidth="2" strokeLinecap="round">
            <path d="M18 34l-2 6M24 34l-2 6M30 34l-2 6" />
          </g>
        ) : (
          <g>
            <circle cx="18" cy="36" r="1.4" />
            <circle cx="25" cy="38" r="1.4" />
            <circle cx="31" cy="35" r="1.4" />
          </g>
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

/**
 * Weather Channel cable experience: two boards (now, then the days ahead),
 * a crawl of the other forecast fields, optional music, and a spoken readout.
 */
export default function WeatherChannelPlayer({ className = "", onClose }) {
  const [payload, setPayload] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(true);
  const [editingPlace, setEditingPlace] = useState(false);
  const [boardCursor, setBoardCursor] = useState({ key: "", index: 0 });
  const [clock, setClock] = useState(() => formatWeatherClock());
  const audioRef = useRef(null);
  const spokenRef = useRef(false);

  const loadForecast = useCallback(async () => {
    setBusy(true);
    setError("");
    try {
      const data = await getLiveWeatherChannel();
      setPayload(data);
      spokenRef.current = false;
    } catch (err) {
      setError(err?.message || "Weather channel unavailable.");
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setBusy(true);
      try {
        const data = await getLiveWeatherChannel();
        if (!cancelled) setPayload(data);
      } catch (err) {
        if (!cancelled) setError(err?.message || "Weather channel unavailable.");
      } finally {
        if (!cancelled) setBusy(false);
      }
    })();
    return () => {
      cancelled = true;
      if (typeof window !== "undefined" && window.speechSynthesis) {
        window.speechSynthesis.cancel();
      }
    };
  }, []);

  useEffect(() => {
    if (!payload?.muzak?.url || !audioRef.current) return undefined;
    const audio = audioRef.current;
    audio.src = payload.muzak.url;
    audio.loop = true;
    audio.volume = 0.35;
    audio.play?.().catch(() => {});
    return () => {
      audio.pause();
      audio.removeAttribute("src");
    };
  }, [payload?.muzak?.url]);

  useEffect(() => {
    if (!payload?.voiceover || spokenRef.current) return undefined;
    if (typeof window === "undefined" || !window.speechSynthesis) return undefined;
    spokenRef.current = true;
    const utter = new SpeechSynthesisUtterance(payload.voiceover);
    utter.rate = 0.95;
    utter.pitch = 1;
    const voices = window.speechSynthesis.getVoices?.() || [];
    const preferred =
      voices.find(
        (v) => /en(-|_)US/i.test(v.lang) && /natural|samantha|karen|daniel/i.test(v.name),
      ) || voices.find((v) => /en/i.test(v.lang));
    if (preferred) utter.voice = preferred;
    window.speechSynthesis.speak(utter);
    return () => window.speechSynthesis.cancel();
  }, [payload?.voiceover]);

  const boards = useMemo(() => weatherBoardSequence(payload), [payload]);
  const sequenceKey = boards.join(",");
  const days = useMemo(() => forecastDayColumns(payload?.daily), [payload]);
  const ticker = useMemo(() => weatherTickerLines(payload), [payload]);
  const sky = weatherSky(payload);
  const current = payload?.current && typeof payload.current === "object" ? payload.current : {};
  const currentSky = skyFromWeatherCode(current.weather_code);
  const showNow = hasCurrentConditions(current);
  const boardIndex = boardCursor.key === sequenceKey ? boardCursor.index : 0;
  const active = boards.length ? boards[boardIndex % boards.length] : "";

  useEffect(() => {
    if (boards.length < 2) return undefined;
    const id = window.setInterval(() => {
      setBoardCursor((prev) => {
        const index = prev.key === sequenceKey ? prev.index : 0;
        return { key: sequenceKey, index: nextWeatherBoardIndex(index, boards) };
      });
    }, WEATHER_BOARD_DWELL_MS);
    return () => window.clearInterval(id);
  }, [boards, sequenceKey]);

  useEffect(() => {
    const id = window.setInterval(() => setClock(formatWeatherClock()), 30_000);
    return () => window.clearInterval(id);
  }, []);

  const temp = current.temperature_2m != null && Number.isFinite(Number(current.temperature_2m))
    ? Math.round(Number(current.temperature_2m))
    : null;
  const wind = current.wind_speed_10m != null && Number.isFinite(Number(current.wind_speed_10m))
    ? Math.round(Number(current.wind_speed_10m))
    : null;
  const humidity = current.relative_humidity_2m != null
    && Number.isFinite(Number(current.relative_humidity_2m))
    ? Math.round(Number(current.relative_humidity_2m))
    : null;

  return (
    <div
      className={`weather-channel ${className}`.trim()}
      data-testid="weather-channel"
      data-sky={sky}
      data-board={active || "empty"}
    >
      <div className="weather-channel-sky" aria-hidden="true" />
      <header className="weather-channel-header">
        <p className="weather-channel-eyebrow">Projectionist Weather Channel</p>
        <h1 className="weather-channel-place">{payload?.place || "Local conditions"}</h1>
        {onClose ? (
          <button
            type="button"
            className="ghost weather-channel-close"
            onClick={onClose}
            data-testid="weather-channel-close"
          >
            Back to Live
          </button>
        ) : null}
        <button
          type="button"
          className="ghost weather-channel-place-toggle"
          data-testid="weather-location-toggle"
          onClick={() => setEditingPlace((open) => !open)}
        >
          {editingPlace ? "Hide place" : "Change place"}
        </button>
      </header>
      {editingPlace ? (
        <WeatherLocationPicker
          variant="channel"
          savedPlace={payload?.location_source === "profile" ? payload?.place || "" : ""}
          source={payload?.location_source || "household"}
          householdPlace={payload?.household_place || ""}
          onSaved={() => {
            setEditingPlace(false);
            loadForecast();
          }}
        />
      ) : null}

      {busy ? <p className="weather-channel-status">Tuning the forecast…</p> : null}
      {error ? (
        <p className="weather-channel-status weather-channel-status--error">{error}</p>
      ) : null}
      {payload?.error ? <p className="weather-channel-status muted">{payload.error}</p> : null}

      <div className="weather-board-stage" data-testid="weather-board-stage">
        {showNow ? (
          <section
            className={`weather-board weather-board--now${active === "now" ? " is-active" : ""}`}
            data-testid="weather-board-now"
            aria-hidden={active !== "now"}
          >
            <p className="weather-board-kicker">Right now</p>
            <SkyGlyph sky={currentSky.sky} />
            <p className="weather-channel-temp" data-testid="weather-channel-now">
              {temp != null ? `${temp}°` : "—"}
            </p>
            <p className="weather-channel-cond">{currentSky.label}</p>
            {wind != null ? <p className="weather-channel-wind">Wind {wind} mph</p> : null}
          </section>
        ) : null}

        {days.length ? (
          <section
            className={`weather-board weather-board--ahead${active === "ahead" ? " is-active" : ""}`}
            data-testid="weather-board-ahead"
            aria-hidden={active !== "ahead"}
          >
            <p className="weather-board-kicker">The days ahead</p>
            <p className="weather-board-place">{payload?.place || "Local conditions"}</p>
            <ol className="weather-day-grid" data-testid="weather-day-grid">
              {days.map((day) => (
                <li key={day.date} className="weather-day-col" data-testid="weather-day-col">
                  <p className="weather-day-weekday">{day.weekday || day.date}</p>
                  <SkyGlyph sky={day.sky} />
                  <p className="weather-day-cond">{day.condition}</p>
                  <p className="weather-day-high">{day.high != null ? day.high : "—"}</p>
                  <p className="weather-day-low">{day.low != null ? day.low : "—"}</p>
                </li>
              ))}
            </ol>
            <div className="weather-now-bar" data-testid="weather-now-bar">
              <span className="weather-now-bar-kicker">Now</span>
              <span className="weather-now-bar-place">{payload?.place || "Local"}</span>
              {humidity != null ? <span>Humidity {humidity}%</span> : null}
              <span>{clock}</span>
              {temp != null ? <span className="weather-now-bar-temp">{temp}°</span> : null}
            </div>
          </section>
        ) : null}
      </div>

      {ticker.length ? (
        <div
          className="weather-channel-ticker"
          data-testid="weather-channel-ticker"
          aria-live="polite"
        >
          <div className="weather-channel-ticker-track">
            {[...ticker, ...ticker].map((line, idx) => (
              <span key={`${line}-${idx}`} className="weather-channel-ticker-item">
                {line}
              </span>
            ))}
          </div>
        </div>
      ) : null}

      <p className="weather-channel-egress muted">
        Forecast via Open-Meteo (leaves LAN).{" "}
        {payload?.muzak
          ? `Music: ${payload.muzak.title}.`
          : payload?.muzak_note || "No music folder is set."}
      </p>
      <audio ref={audioRef} data-testid="weather-channel-muzak" />
    </div>
  );
}
