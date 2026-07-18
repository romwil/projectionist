import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getLibraryKnowledgeCoverage } from "../api/client";
import {
  buildKnowledgeCoverageRows,
  summarizeKnowledgeCoverage,
} from "../lib/knowledgeCoverage.js";
import { ROUTES } from "../lib/backNav.js";

/**
 * Knowledge coverage strip/card for Admin Dashboard / Scheduled Tasks / Explore.
 * variant: "panel" (full dash panel) | "strip" (compact honesty line)
 */
export default function KnowledgeCoverageCard({
  variant = "panel",
  showHelpLink = true,
  className = "",
}) {
  const [coverage, setCoverage] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getLibraryKnowledgeCoverage()
      .then((data) => {
        if (cancelled) return;
        setCoverage(data);
        setError("");
      })
      .catch((err) => {
        if (cancelled) return;
        setCoverage(null);
        setError(err.message || "Could not load knowledge coverage.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const rows = buildKnowledgeCoverageRows(coverage);
  const summary = summarizeKnowledgeCoverage(coverage);

  if (variant === "strip") {
    return (
      <aside
        className={`knowledge-coverage-strip ${className}`.trim()}
        data-testid="knowledge-coverage-strip"
      >
        {loading ? (
          <p className="status status-secondary">Loading coverage…</p>
        ) : error ? (
          <p className="status status-secondary">{error}</p>
        ) : summary ? (
          <p className="knowledge-coverage-strip-line">
            <span className="knowledge-coverage-strip-label">Knowledge</span>
            <span data-testid="knowledge-coverage-summary">{summary}</span>
            {showHelpLink ? (
              <>
                {" "}
                <Link to={ROUTES.help} className="app-topbar-link">
                  Why this matters
                </Link>
              </>
            ) : null}
          </p>
        ) : (
          <p className="status status-secondary">No coverage stats yet.</p>
        )}
      </aside>
    );
  }

  return (
    <section
      className={`dash-panel knowledge-coverage-panel ${className}`.trim()}
      data-testid="knowledge-coverage-panel"
    >
      <div className="knowledge-coverage-header">
        <h3 className="dash-panel-title">Knowledge coverage</h3>
        {showHelpLink ? (
          <Link
            to={`${ROUTES.help}#coverage-over-time`}
            className="knowledge-coverage-help-link"
            data-testid="knowledge-coverage-help"
          >
            How to read this
          </Link>
        ) : null}
      </div>
      <p className="status status-secondary knowledge-coverage-blurb">
        How deep the curator knows your shelves — overviews, plot motifs, keywords,
        neighbors, and optional loglines. Sparse bars mean idle tasks still have work.
      </p>
      {loading ? (
        <div className="dash-skeleton" aria-label="Loading coverage">
          <div className="dash-skeleton-bar" />
          <div className="dash-skeleton-bar short" />
        </div>
      ) : error ? (
        <p className="dash-panel-error">{error}</p>
      ) : rows.length ? (
        <>
          {coverage?.total_titles != null ? (
            <p className="knowledge-coverage-total" data-testid="knowledge-coverage-total">
              {Number(coverage.total_titles).toLocaleString()} titles in library
            </p>
          ) : null}
          <ul className="knowledge-coverage-grid" data-testid="knowledge-coverage-grid">
            {rows.map((row) => (
              <li
                key={row.id}
                className="knowledge-coverage-metric"
                data-testid={`knowledge-coverage-${row.id}`}
              >
                <span className="knowledge-coverage-metric-value">{row.pctLabel}</span>
                <span className="knowledge-coverage-metric-label">{row.label}</span>
                {row.detail ? (
                  <span className="knowledge-coverage-metric-detail">{row.detail}</span>
                ) : null}
                <span
                  className="knowledge-coverage-bar"
                  aria-hidden="true"
                  style={{ "--coverage-pct": `${Math.min(100, Math.max(0, row.pct))}%` }}
                />
              </li>
            ))}
          </ul>
        </>
      ) : (
        <p className="dash-empty">No coverage data yet — sync a library first.</p>
      )}
    </section>
  );
}
