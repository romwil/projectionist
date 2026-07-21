import { useCallback, useEffect, useState } from "react";
import { generateWeeklyDigest, getWeeklyDigest } from "../api/client";
import { formatDigestTitle, normalizeWeeklyDigest } from "../lib/weeklyDigest.js";

/** Owner "This week in your library" in-app digest (no email required). */
export default function WeeklyDigestPanel() {
  const [latest, setLatest] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getWeeklyDigest();
      setLatest(data?.latest || null);
      setError("");
    } catch (err) {
      setError(err.message || "Could not load the weekly digest.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function handleGenerate() {
    setBusy(true);
    setError("");
    try {
      const data = await generateWeeklyDigest();
      setLatest(data?.latest || null);
    } catch (err) {
      setError(err.message || "Could not generate the digest.");
    } finally {
      setBusy(false);
    }
  }

  const model = normalizeWeeklyDigest(latest);
  const generatedLabel = model?.generatedAt
    ? new Date(model.generatedAt * 1000).toLocaleString()
    : null;

  return (
    <section className="weekly-digest" data-testid="weekly-digest">
      <div className="weekly-digest-head">
        <div>
          <p className="eyebrow">Weekly digest</p>
          <h3 className="dash-panel-title">This week in your library</h3>
          {generatedLabel ? (
            <p className="weekly-digest-meta">Snapshot from {generatedLabel}</p>
          ) : null}
        </div>
        <button
          type="button"
          className="ghost"
          data-testid="weekly-digest-generate"
          disabled={busy}
          onClick={handleGenerate}
        >
          {busy ? "Generating…" : "Generate now"}
        </button>
      </div>

      {error ? <p className="dash-panel-error">{error}</p> : null}

      {loading ? (
        <p className="status status-secondary">Loading digest…</p>
      ) : !model ? (
        <p className="dash-empty" data-testid="weekly-digest-empty">
          No digest yet. It builds automatically each week, or generate one now.
        </p>
      ) : (
        <>
          <div className="weekly-digest-stats">
            {model.stats.map((stat) => (
              <div
                key={stat.id}
                className="weekly-digest-stat"
                data-testid={`weekly-digest-stat-${stat.id}`}
              >
                <span className="weekly-digest-stat-value">{stat.value}</span>
                <span className="weekly-digest-stat-label">{stat.label}</span>
              </div>
            ))}
          </div>
          {model.newTitles.length ? (
            <>
              <p className="weekly-digest-meta">New additions</p>
              <ul className="weekly-digest-titles">
                {model.newTitles.map((item, index) => (
                  <li
                    key={`${item.title}-${index}`}
                    className="weekly-digest-title-chip"
                  >
                    {formatDigestTitle(item)}
                  </li>
                ))}
              </ul>
            </>
          ) : null}
        </>
      )}
    </section>
  );
}
