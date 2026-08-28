import { useCallback, useEffect, useMemo, useState } from "react";
import BarChart from "../components/charts/BarChart";
import { getLlmUsage } from "../api/client";

const DAY_OPTIONS = [
  { value: 1, label: "1 day" },
  { value: 7, label: "7 days" },
  { value: 30, label: "30 days" },
  { value: 90, label: "90 days" },
];

function formatUsd(value) {
  const n = Number(value || 0);
  if (!Number.isFinite(n) || n <= 0) return "—";
  if (n < 0.01) return `$${n.toFixed(4)}`;
  return `$${n.toFixed(2)}`;
}

function formatTokens(value) {
  const n = Number(value || 0);
  if (!Number.isFinite(n) || n <= 0) return "0";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(Math.round(n));
}

function StatCard({ value, label, detail }) {
  return (
    <div className="dash-stat-card" data-testid="llm-usage-stat">
      <span className="dash-stat-value">{value}</span>
      <span className="dash-stat-label">{label}</span>
      {detail ? <span className="dash-stat-detail">{detail}</span> : null}
    </div>
  );
}

export default function LlmUsagePage({ embedded = false }) {
  const [days, setDays] = useState(7);
  const [model, setModel] = useState("");
  const [purpose, setPurpose] = useState("");
  const [personaId, setPersonaId] = useState("");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    setLoading(true);
    setError("");
    getLlmUsage({
      days,
      model: model || undefined,
      purpose: purpose || undefined,
      persona_id: personaId || undefined,
    })
      .then(setData)
      .catch((err) => setError(err.message || "Failed to load usage"))
      .finally(() => setLoading(false));
  }, [days, model, purpose, personaId]);

  useEffect(() => {
    load();
  }, [load]);

  const totals = data?.totals || {};
  const dayChart = useMemo(
    () =>
      (data?.by_day || []).map((row) => ({
        label: String(row.day || "").slice(5) || "—",
        value: Number(row.total_tokens || 0),
      })),
    [data],
  );
  const purposeChart = useMemo(
    () =>
      (data?.by_purpose || []).map((row) => ({
        label: row.purpose || "—",
        value: Number(row.call_count || 0),
      })),
    [data],
  );
  const modelChart = useMemo(
    () =>
      (data?.by_model || []).slice(0, 8).map((row) => ({
        label: row.model || "(unknown)",
        value: Number(row.total_tokens || 0),
      })),
    [data],
  );

  return (
    <div
      className={`admin-page llm-usage-page${embedded ? " llm-usage-page-embedded" : ""}`}
      data-testid="llm-usage-page"
    >
      {embedded ? (
        <div className="admin-page-header admin-page-header-embedded">
          <p className="muted">
            Token spend across chat, wrap-up, library saves, loglines, and embeddings. Estimated USD
            uses a small built-in price table — unknown models show tokens only.
          </p>
          <button type="button" className="ghost" onClick={load} disabled={loading}>
            {loading ? "Refreshing…" : "Refresh"}
          </button>
        </div>
      ) : (
        <header className="admin-page-header">
          <div>
            <h1>Usage</h1>
            <p className="muted">
              Token spend across chat, wrap-up, library saves, loglines, and embeddings. Estimated USD
              uses a small built-in price table — unknown models show tokens only.
            </p>
          </div>
          <button type="button" className="ghost" onClick={load} disabled={loading}>
            {loading ? "Refreshing…" : "Refresh"}
          </button>
        </header>
      )}

      <div className="llm-usage-filters" data-testid="llm-usage-filters">
        <label>
          <span>Window</span>
          <select value={days} onChange={(e) => setDays(Number(e.target.value))}>
            {DAY_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Model</span>
          <select value={model} onChange={(e) => setModel(e.target.value)}>
            <option value="">All models</option>
            {(data?.filters?.models || []).map((id) => (
              <option key={id} value={id}>
                {id}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Purpose</span>
          <select value={purpose} onChange={(e) => setPurpose(e.target.value)}>
            <option value="">All purposes</option>
            {(data?.filters?.purposes || []).map((id) => (
              <option key={id} value={id}>
                {id}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Persona</span>
          <select value={personaId} onChange={(e) => setPersonaId(e.target.value)}>
            <option value="">All personas</option>
            {(data?.filters?.personas || []).map((id) => (
              <option key={id} value={id}>
                {id}
              </option>
            ))}
          </select>
        </label>
      </div>

      {error ? <p className="dash-panel-error">{error}</p> : null}

      <div className="dash-stat-row">
        <StatCard
          value={loading ? "…" : formatTokens(totals.total_tokens)}
          label="Tokens"
          detail={`${formatTokens(totals.prompt_tokens)} in · ${formatTokens(totals.completion_tokens)} out`}
        />
        <StatCard
          value={loading ? "…" : formatUsd(totals.estimated_usd)}
          label="Est. USD"
          detail="From known model prices"
        />
        <StatCard
          value={loading ? "…" : String(totals.call_count || 0)}
          label="Calls"
          detail={
            totals.avg_latency_ms
              ? `avg ${Math.round(totals.avg_latency_ms)} ms`
              : "provider rounds"
          }
        />
      </div>

      <div className="llm-usage-grid">
        <section className="dash-panel">
          <h3 className="dash-panel-title">Tokens by day</h3>
          {loading ? (
            <div className="dash-skeleton" aria-label="Loading">
              <div className="dash-skeleton-bar" />
            </div>
          ) : dayChart.length ? (
            <BarChart data={dayChart} />
          ) : (
            <p className="muted">No LLM calls in this window yet.</p>
          )}
        </section>
        <section className="dash-panel">
          <h3 className="dash-panel-title">Calls by purpose</h3>
          {loading ? (
            <div className="dash-skeleton" aria-label="Loading">
              <div className="dash-skeleton-bar" />
            </div>
          ) : purposeChart.length ? (
            <BarChart data={purposeChart} />
          ) : (
            <p className="muted">No purpose breakdown yet.</p>
          )}
        </section>
        <section className="dash-panel">
          <h3 className="dash-panel-title">Tokens by model</h3>
          {loading ? (
            <div className="dash-skeleton" aria-label="Loading">
              <div className="dash-skeleton-bar" />
            </div>
          ) : modelChart.length ? (
            <BarChart data={modelChart} />
          ) : (
            <p className="muted">No model breakdown yet.</p>
          )}
        </section>
        <section className="dash-panel">
          <h3 className="dash-panel-title">By persona</h3>
          {loading ? (
            <div className="dash-skeleton" aria-label="Loading">
              <div className="dash-skeleton-bar" />
            </div>
          ) : (data?.by_persona || []).length ? (
            <table className="llm-usage-table">
              <thead>
                <tr>
                  <th>Persona</th>
                  <th>Calls</th>
                  <th>Tokens</th>
                  <th>Est. USD</th>
                </tr>
              </thead>
              <tbody>
                {(data?.by_persona || []).map((row) => (
                  <tr key={row.persona_id || "none"}>
                    <td>{row.persona_id || "(none)"}</td>
                    <td>{row.call_count}</td>
                    <td>{formatTokens(row.total_tokens)}</td>
                    <td>{formatUsd(row.estimated_usd)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="muted">No persona-tagged calls yet.</p>
          )}
        </section>
      </div>
    </div>
  );
}
