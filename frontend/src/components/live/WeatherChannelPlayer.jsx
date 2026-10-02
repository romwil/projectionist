import { useCallback, useEffect, useRef, useState } from "react";
import { getLiveWeatherChannel } from "../../api/client";
import WeatherLocationPicker from "../weather/WeatherLocationPicker";

/**
 * Weather Channel–style cable experience: scrolling ticker + voiceover + optional muzak.
 */
export default function WeatherChannelPlayer({ className = "", onClose }) {
  const [payload, setPayload] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(true);
  const [editingPlace, setEditingPlace] = useState(false);
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
    // Prefer a calmer voice when the browser exposes one.
    const voices = window.speechSynthesis.getVoices?.() || [];
    const preferred =
      voices.find(
        (v) => /en(-|_)US/i.test(v.lang) && /natural|samantha|karen|daniel/i.test(v.name),
      ) || voices.find((v) => /en/i.test(v.lang));
    if (preferred) utter.voice = preferred;
    window.speechSynthesis.speak(utter);
    return () => window.speechSynthesis.cancel();
  }, [payload?.voiceover]);

  const ticker = Array.isArray(payload?.ticker) ? payload.ticker : [];
  const current = payload?.current || {};

  return (
    <div className={`weather-channel ${className}`.trim()} data-testid="weather-channel">
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

      <div className="weather-channel-now" data-testid="weather-channel-now">
        <p className="weather-channel-temp">
          {current.temperature_2m != null ? `${Math.round(Number(current.temperature_2m))}°` : "—"}
        </p>
        <p className="weather-channel-cond">
          {current.weather_code != null ? `Code ${current.weather_code}` : "Standing by"}
          {current.wind_speed_10m != null
            ? ` · Wind ${Math.round(Number(current.wind_speed_10m))} mph`
            : ""}
        </p>
      </div>

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
