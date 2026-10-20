import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getLibraryKnowledgeCoverage } from "../api/client";
import {
  KNOWLEDGE_COVERAGE_REQUEST_MS,
  buildKnowledgeCoverageRows,
  embeddingCoverageLabel,
  knowledgeCoverageFailureCopy,
  knowledgeStripContent,
  summarizeKnowledgeCoverage,
} from "../lib/knowledgeCoverage.js";
import { helpAnchor } from "../lib/backNav.js";
import SectionHelp from "./SectionHelp.jsx";

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
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), KNOWLEDGE_COVERAGE_REQUEST_MS);
    setLoading(true);
    getLibraryKnowledgeCoverage({ signal: controller.signal })
      .then((data) => {
        if (cancelled) return;
        setCoverage(data);
        setError("");
      })
      .catch((err) => {
        if (cancelled) return;
        setCoverage(null);
        // Transport failures stay blank. The strip then renders nothing.
        setError(knowledgeCoverageFailureCopy(err));
      })
      .finally(() => {
        window.clearTimeout(timer);
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
      controller.abort();
    };
  }, []);

  const rows = buildKnowledgeCoverageRows(coverage);
  const summary = summarizeKnowledgeCoverage(coverage);
  const embeddingLabel = embeddingCoverageLabel(coverage);

  if (variant === "strip") {
    const line = knowledgeStripContent({ loading, error, summary });
    if (!line) return null;
    return (
      <aside
        className={`knowledge-coverage-strip ${className}`.trim()}
        data-testid="knowledge-coverage-strip"
      >
        <p className="knowledge-coverage-strip-line">
          <span className="knowledge-coverage-strip-label">Knowledge</span>
          <span data-testid="knowledge-coverage-summary">{line}</span>
          {embeddingLabel ? (
            <>
              {" "}
              <span className="knowledge-coverage-embedding" data-testid="knowledge-coverage-embedding">
                · {embeddingLabel}
              </span>
            </>
          ) : null}
          {showHelpLink ? (
            <>
              {" "}
              <Link
                to={helpAnchor("what-knowledge-coverage-means")}
                className="app-topbar-link"
              >
                Why this matters
              </Link>
            </>
          ) : null}
        </p>
      </aside>
    );
  }

  return (
    <section
      className={`dash-panel knowledge-coverage-panel ${className}`.trim()}
      data-testid="knowledge-coverage-panel"
    >
      <div className="knowledge-coverage-header">
        <div className="grooming-panel-title-row">
          <h3 className="dash-panel-title">Knowledge coverage</h3>
          <SectionHelp label="About knowledge coverage" testId="knowledge-coverage-section-help">
            <p>
              Each bar is the share of your library that already has that kind of curator
              knowledge. Gaps usually clear as scheduled enrichment runs — they are not
              missing Plex files.
            </p>
          </SectionHelp>
        </div>
        {showHelpLink ? (
          <Link
            to={helpAnchor("coverage-over-time")}
            className="knowledge-coverage-help-link"
            data-testid="knowledge-coverage-help"
          >
            How to read this
          </Link>
        ) : null}
      </div>
      <p className="status status-secondary knowledge-coverage-blurb">
        Named kinship is the health that matters for More Like This and inbox bridges.
        Similar cache can look full while Named kinship stays low — empty shelves queue
        catch-up on{" "}
        <Link to="/admin/scheduled-tasks" className="app-topbar-link">
          Scheduled Tasks
        </Link>
        . Sparse bars mean enrichment still has work.
        {embeddingLabel ? (
          <>
            {" "}
            <span data-testid="knowledge-coverage-embedding">{embeddingLabel}.</span>
          </>
        ) : null}
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
