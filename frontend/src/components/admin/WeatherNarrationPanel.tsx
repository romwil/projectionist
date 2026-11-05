import { useCallback, useEffect, useState } from "react";
import { getLiveWeatherAdmin, saveLiveWeatherAdmin } from "../../api/client";

type Status = Record<string, any>;

function megabytes(bytes: unknown): string {
  const n = Number(bytes) || 0;
  return `${Math.max(1, Math.round(n / 1_000_000))} MB`;
}

/**
 * Owner controls for Weather Channel narration: local neural voice (downloaded
 * on enable, never baked into the image), voice and pace, optional Windy
 * webcams key, and a read-only preview of the scripts now on air.
 */
export default function WeatherNarrationPanel() {
  const [status, setStatus] = useState<Status | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [windyKey, setWindyKey] = useState("");

  const load = useCallback(async () => {
    try {
      setStatus((await getLiveWeatherAdmin()) as Status);
    } catch (error: unknown) {
      setMessage((error as any)?.message || "Could not load Weather narration settings.");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const narration = status?.narration || {};
  const downloading = !!narration.downloading;
  useEffect(() => {
    if (!downloading) return undefined;
    const id = window.setInterval(load, 2_000);
    return () => window.clearInterval(id);
  }, [downloading, load]);

  async function save(body: Record<string, unknown>, done: string) {
    setBusy(true);
    setMessage("");
    try {
      setStatus((await saveLiveWeatherAdmin(body)) as Status);
      setMessage(done);
    } catch (error: unknown) {
      setMessage((error as any)?.message || "Could not save Weather narration settings.");
    } finally {
      setBusy(false);
    }
  }

  const engines: Array<{ id: string; label: string; voices: Array<{ id: string; label: string }> }> =
    narration.engines || [];
  const engine = engines.find((e) => e.id === narration.engine) || engines[0];
  const total = Number(narration.download_total_bytes) || 0;
  const done = Number(narration.download_done_bytes) || 0;
  const previews: Array<{ place: string; scripts: Record<string, Array<{ text: string; source: string }>> }> =
    status?.previews || [];

  return (
    <div className="service-card weather-narration-card" data-testid="weather-narration-panel">
      <div className="service-card-header">
        <div className="service-card-title">
          <h3>Weather Channel narration</h3>
        </div>
      </div>
      <p className="wizard-note">
        A local voice on this server reads each forecast segment. The voice model downloads once when you turn
        narration on ({megabytes(narration.download_bytes)} for this voice). If the voice is off or fails, viewers see
        captions instead. Browsers never synthesize speech.
      </p>
      <label className="checkbox-row">
        <input
          type="checkbox"
          data-testid="weather-narration-enabled"
          checked={!!narration.enabled}
          disabled={busy || !status}
          onChange={(e) =>
            save(
              { narration_enabled: e.target.checked },
              e.target.checked
                ? narration.installed
                  ? "Narration on."
                  : "Narration on. Downloading the voice model…"
                : "Narration off. The forecast is captioned.",
            )
          }
        />
        <span>Narrate the forecast</span>
      </label>
      {downloading ? (
        <div className="weather-narration-progress" data-testid="weather-narration-progress">
          <progress max={total || 1} value={done} aria-label="Voice model download" />
          <span>
            {megabytes(done)} of {megabytes(total)}
          </span>
        </div>
      ) : null}
      {narration.download_error ? (
        <p className="field-help" role="status">
          Voice download failed: {narration.download_error}
        </p>
      ) : null}
      {narration.enabled && narration.installed ? (
        <p className="field-help" data-testid="weather-narration-ready">
          Voice installed.
        </p>
      ) : null}
      {narration.enabled && narration.engine_available === false ? (
        <p className="field-help">
          The {engine?.label || narration.engine} engine is not installed in this image, so viewers get captions.
        </p>
      ) : null}

      <div className="settings-grid">
        <label>
          <span>Voice engine</span>
          <select
            data-testid="weather-tts-engine"
            value={narration.engine || ""}
            disabled={busy || !status}
            onChange={(e) => save({ tts_engine: e.target.value, tts_voice: "" }, "Voice engine saved.")}
          >
            {engines.map((e) => (
              <option key={e.id} value={e.id}>
                {e.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Voice</span>
          <select
            data-testid="weather-tts-voice"
            value={narration.voice || ""}
            disabled={busy || !status}
            onChange={(e) => save({ tts_voice: e.target.value }, "Voice saved.")}
          >
            {(engine?.voices || []).map((v) => (
              <option key={v.id} value={v.id}>
                {v.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Pace</span>
          <select
            data-testid="weather-tts-rate"
            value={String(narration.rate ?? 1)}
            disabled={busy || !status}
            onChange={(e) => save({ tts_rate: Number(e.target.value) }, "Pace saved.")}
          >
            <option value="0.9">Relaxed</option>
            <option value="1">Normal</option>
            <option value="1.1">Brisk</option>
          </select>
        </label>
      </div>

      <div className="settings-grid">
        <label>
          <span>Windy webcams key (optional)</span>
          <input
            type="password"
            autoComplete="off"
            data-testid="weather-windy-key"
            placeholder={status?.windy_api_key_set ? "Saved — enter a new key to replace" : "Not set — no webcams board"}
            value={windyKey}
            onChange={(e) => setWindyKey(e.target.value)}
          />
        </label>
      </div>
      <div className="button-row">
        <button
          type="button"
          className="ghost"
          disabled={busy || !windyKey.trim()}
          onClick={async () => {
            await save({ windy_api_key: windyKey.trim() }, "Windy key saved. Webcams appear on the next refresh.");
            setWindyKey("");
          }}
        >
          Save key
        </button>
        {status?.windy_api_key_set ? (
          <button
            type="button"
            className="ghost"
            disabled={busy}
            onClick={() => save({ clear_windy_api_key: true }, "Windy key removed. No webcams board.")}
          >
            Remove key
          </button>
        ) : null}
      </div>

      {status?.alerts_note ? <p className="field-help">{status.alerts_note}</p> : null}
      <p className="field-help">
        {status?.llm_configured
          ? "Scripts are written by your household AI from the forecast numbers, then checked against them."
          : "No household AI is set up, so scripts use built-in templates."}
      </p>

      {previews.length ? (
        <details className="weather-script-preview" data-testid="weather-script-preview">
          <summary>Scripts on air now</summary>
          {previews.map((preview) => (
            <div key={preview.place}>
              <h4>{preview.place}</h4>
              <dl>
                {Object.entries(preview.scripts).map(([segment, rows]) => (
                  <div key={segment}>
                    <dt>{segment.replace(/_/g, " ")}</dt>
                    {rows.map((row, index) => (
                      <dd key={index}>
                        {row.text} <span className="muted">({row.source})</span>
                      </dd>
                    ))}
                  </div>
                ))}
              </dl>
            </div>
          ))}
        </details>
      ) : null}

      {message ? (
        <p className="muzak-folder-status" role="status" data-testid="weather-narration-status">
          {message}
        </p>
      ) : null}
    </div>
  );
}
