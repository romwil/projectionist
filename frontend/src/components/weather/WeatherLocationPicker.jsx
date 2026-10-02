import { useState } from "react";
import { patchAuthMe, searchWeatherPlaces } from "../../api/client";

/**
 * Search for a weather place and store the chosen label + coordinates
 * on the signed-in profile. Forecasts reuse those coordinates.
 */
export default function WeatherLocationPicker({
  savedPlace = "",
  source = "household",
  householdPlace = "",
  onSaved,
  variant = "settings",
}) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);

  async function handleSearch(event) {
    event?.preventDefault?.();
    const text = query.trim();
    if (text.length < 2) {
      setStatus("Type a ZIP, city and state, or city and country.");
      setResults([]);
      return;
    }
    setBusy(true);
    setStatus("");
    try {
      const payload = await searchWeatherPlaces(text);
      const next = Array.isArray(payload?.results) ? payload.results : [];
      setResults(next);
      setStatus(next.length ? "" : "No matches. Try a city name, or city and country.");
    } catch (error) {
      setResults([]);
      setStatus(error?.message || "Place search is unavailable right now.");
    } finally {
      setBusy(false);
    }
  }

  async function handleChoose(candidate) {
    setBusy(true);
    setStatus("");
    try {
      const result = await patchAuthMe({
        weather_place: candidate.label,
        weather_lat: candidate.latitude,
        weather_lon: candidate.longitude,
      });
      setResults([]);
      setQuery("");
      setStatus(`Saved ${candidate.label} on your profile.`);
      onSaved?.(result?.user || null);
    } catch (error) {
      setStatus(error?.message || "Could not save that place.");
    } finally {
      setBusy(false);
    }
  }

  async function handleClear() {
    setBusy(true);
    setStatus("");
    try {
      const result = await patchAuthMe({ clear_weather_location: true });
      setStatus("Using the household default.");
      onSaved?.(result?.user || null);
    } catch (error) {
      setStatus(error?.message || "Could not clear your place.");
    } finally {
      setBusy(false);
    }
  }

  const usingProfile = source === "profile" && Boolean(savedPlace);
  const householdLabel =
    householdPlace && householdPlace !== "your area" ? householdPlace : "the household default";

  return (
    <div
      className={`weather-place-picker weather-place-picker--${variant}`}
      data-testid="weather-location-picker"
    >
      <p className="weather-place-current" data-testid="weather-location-current">
        {usingProfile
          ? `Your place: ${savedPlace}`
          : `Using ${householdLabel} until you pick a place.`}
      </p>
      <div className="weather-place-search">
        <label>
          <span className="sr-only">Search for a place</span>
          <input
            type="search"
            value={query}
            maxLength={120}
            placeholder="ZIP, city and state, or city and country"
            data-testid="weather-location-query"
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                handleSearch(event);
              }
            }}
          />
        </label>
        <button
          type="button"
          className="ghost"
          data-testid="weather-location-search"
          disabled={busy}
          onClick={handleSearch}
        >
          {busy ? "Searching…" : "Search"}
        </button>
      </div>
      <p className="field-help">
        Search looks up the place once (Open-Meteo, leaves the LAN). Saving stores the name and map
        point on your profile so the forecast doesn’t search again.
      </p>
      {results.length ? (
        <ul className="weather-place-results" data-testid="weather-location-results">
          {results.map((candidate) => (
            <li key={`${candidate.label}-${candidate.latitude}-${candidate.longitude}`}>
              <button
                type="button"
                className="ghost weather-place-result"
                disabled={busy}
                onClick={() => handleChoose(candidate)}
              >
                {candidate.label}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      {usingProfile ? (
        <button
          type="button"
          className="ghost"
          data-testid="weather-location-clear"
          disabled={busy}
          onClick={handleClear}
        >
          Use household default
        </button>
      ) : null}
      {status ? (
        <p className="weather-place-status" data-testid="weather-location-status" role="status">
          {status}
        </p>
      ) : null}
    </div>
  );
}
