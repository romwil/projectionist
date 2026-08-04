import { useCallback, useEffect, useMemo, useState } from "react";
import {
  approveStagedAugmentation,
  getKnowledgeOpsSummary,
  getKnowledgeOpsTaxonomyRegistry,
  getKnowledgeOpsTelemetryTopEvents,
  getKnowledgeOpsTelemetryTrend,
  listStagedAugmentations,
  rejectStagedAugmentation,
} from "../api/client";
import SectionHelp from "../components/SectionHelp.jsx";
import SettingsPageHeader from "../components/settings/SettingsPageHeader";
import SettingsPanel from "../components/settings/SettingsPanel";
import {
  buildKnowledgeCoverageRows,
  summarizeKnowledgeCoverage,
} from "../lib/knowledgeCoverage.js";
import {
  actDescriptionForStagedItem,
  actLabelForStagedItem,
  canActOnStagedItem,
  stagedItemDisplayTitle,
} from "../lib/knowledgeOpsActions.js";
import {
  knowledgeEventDisplayName,
  knowledgeGapDisplayName,
  knowledgeTaskDisplayName,
} from "../lib/knowledgeOpsDisplay.js";

const TABS = [
  { id: "taxonomy", label: "Name mappings" },
  { id: "demand", label: "Requested details" },
  { id: "coverage", label: "Missing knowledge" },
  { id: "activity", label: "Activity" },
  { id: "all", label: "All exceptions" },
];

const TASK_FILTERS = {
  taxonomy: "facet_taxonomy_audit",
  demand: "entity_memory_enrichment",
  coverage: "coverage_deficit_audit",
  all: null,
};

function formatRate(rate) {
  if (rate == null || Number.isNaN(Number(rate))) return "—";
  return `${Math.round(Number(rate) * 100)}%`;
}

function FunnelBar({ label, value, max, accent }) {
  const pct = max > 0 ? Math.max(4, Math.round((value / max) * 100)) : 0;
  return (
    <div className="knowledge-ops-funnel-step" data-testid={`knowledge-ops-funnel-${label}`}>
      <div className="knowledge-ops-funnel-label">
        <span>{label}</span>
        <strong>{value}</strong>
      </div>
      <div className="knowledge-ops-funnel-track">
        <div
          className="knowledge-ops-funnel-fill"
          style={{ width: `${pct}%`, background: accent || "var(--accent)" }}
        />
      </div>
    </div>
  );
}

function SummaryStrip({ summary, loading }) {
  if (loading) {
    return <p className="status status-secondary" data-testid="knowledge-ops-summary-loading">Loading summary…</p>;
  }
  if (!summary) return null;
  const funnel = summary.funnel || {};
  return (
    <section className="knowledge-ops-summary" data-testid="knowledge-ops-summary">
      <div className="knowledge-ops-stat-grid">
        <div className="dash-stat-card" data-testid="knowledge-ops-stat-facet-pending">
          <span className="dash-stat-value">{summary.pending_facet_candidates ?? 0}</span>
          <span className="dash-stat-label">Name mappings to review</span>
        </div>
        <div className="dash-stat-card" data-testid="knowledge-ops-stat-all-pending">
          <span className="dash-stat-value">{summary.pending_all_augmentations ?? 0}</span>
          <span className="dash-stat-label">Pending exceptions</span>
        </div>
        <div className="dash-stat-card" data-testid="knowledge-ops-stat-signals-7d">
          <span className="dash-stat-value">{summary.signals_7d ?? 0}</span>
          <span className="dash-stat-label">Findings (7d)</span>
        </div>
        <div className="dash-stat-card" data-testid="knowledge-ops-stat-signals-30d">
          <span className="dash-stat-value">{summary.signals_30d ?? 0}</span>
          <span className="dash-stat-label">Findings (30d)</span>
        </div>
        <div className="dash-stat-card" data-testid="knowledge-ops-stat-approve-rate">
          <span className="dash-stat-value">{formatRate(summary.approve_rate_30d)}</span>
          <span className="dash-stat-label">Saved (30d)</span>
        </div>
        <div className="dash-stat-card" data-testid="knowledge-ops-stat-reject-rate">
          <span className="dash-stat-value">{formatRate(summary.reject_rate_30d)}</span>
          <span className="dash-stat-label">Dismissed (30d)</span>
        </div>
      </div>
      <div className="knowledge-ops-funnel" data-testid="knowledge-ops-funnel">
        <h3 className="knowledge-ops-section-title">Review progress</h3>
        <FunnelBar label="noticed" value={funnel.observed ?? 0} max={funnel.observed ?? 1} />
        <FunnelBar
          label="ready for review"
          value={funnel.at_threshold ?? 0}
          max={funnel.observed ?? 1}
        />
        <FunnelBar
          label="waiting"
          value={funnel.staged_pending ?? 0}
          max={funnel.observed ?? 1}
        />
        <FunnelBar
          label="saved"
          value={funnel.staged_approved ?? 0}
          max={funnel.observed ?? 1}
          accent="var(--success, #6bcf7f)"
        />
        <FunnelBar
          label="dismissed"
          value={funnel.staged_rejected ?? 0}
          max={funnel.observed ?? 1}
          accent="var(--muted)"
        />
      </div>
    </section>
  );
}

function Sparkline({ series }) {
  const points = useMemo(() => {
    const byDay = {};
    for (const row of series || []) {
      const day = row.day;
      byDay[day] = (byDay[day] || 0) + Number(row.signal_volume || 0);
    }
    const days = Object.keys(byDay).sort();
    const values = days.map((d) => byDay[d]);
    const max = Math.max(...values, 1);
    return values.map((v, i) => ({
      x: values.length <= 1 ? 50 : (i / (values.length - 1)) * 100,
      y: 100 - (v / max) * 100,
      v,
    }));
  }, [series]);

  if (!points.length) {
    return <p className="status status-secondary">No signal trend yet.</p>;
  }

  const path = points.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x} ${p.y}`).join(" ");
  return (
    <svg
      className="knowledge-ops-sparkline"
      viewBox="0 0 100 100"
      preserveAspectRatio="none"
      data-testid="knowledge-ops-sparkline"
      aria-hidden="true"
    >
      <path d={path} fill="none" stroke="var(--accent)" strokeWidth="2" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

function ContextPanel({ item, onClose }) {
  if (!item) return null;
  const candidate = item.candidate || {};
  const isFacet = item.target_entity_type === "facet";
  const displayTitle = stagedItemDisplayTitle(item);
  return (
    <aside className="knowledge-ops-context" data-testid="knowledge-ops-context">
      <div className="knowledge-ops-context-header">
        <h3>Candidate context</h3>
        <button type="button" className="ghost" onClick={onClose} data-testid="knowledge-ops-context-close">
          Close
        </button>
      </div>
      <dl className="knowledge-ops-context-list">
        <div>
          <dt>Task</dt>
          <dd>{knowledgeTaskDisplayName(item.task_name)}</dd>
        </div>
        <div>
          <dt>Priority</dt>
          <dd>{item.priority_tier}</dd>
        </div>
        {displayTitle ? (
          <div>
            <dt>Title</dt>
            <dd>{displayTitle}</dd>
          </div>
        ) : null}
        <div>
          <dt>Library item</dt>
          <dd>
            {item.target_entity_type}:{item.target_entity_id}
          </dd>
        </div>
        {candidate.alias && candidate.alias !== displayTitle ? (
          <div>
            <dt>Unrecognized name</dt>
            <dd>{candidate.alias}</dd>
          </div>
        ) : null}
        {candidate.suggested_concept_id ? (
          <div>
            <dt>Suggested known group</dt>
            <dd>{candidate.suggested_concept_id}</dd>
          </div>
        ) : null}
        {candidate.suggested_canonical_name ? (
          <div>
            <dt>Suggested TMDB name</dt>
            <dd>{candidate.suggested_canonical_name}</dd>
          </div>
        ) : null}
        {candidate.context_source ? (
          <div>
            <dt>Source</dt>
            <dd>{candidate.context_source}</dd>
          </div>
        ) : null}
        {candidate.deficit_kind ? (
          <div>
            <dt>Missing</dt>
            <dd>{knowledgeGapDisplayName(candidate.deficit_kind)}</dd>
          </div>
        ) : null}
        {candidate.reason ? (
          <div>
            <dt>Why</dt>
            <dd>{candidate.reason}</dd>
          </div>
        ) : null}
        {candidate.name && candidate.name !== displayTitle ? (
          <div>
            <dt>Name</dt>
            <dd>{candidate.name}</dd>
          </div>
        ) : null}
        {candidate.overlay_path || candidate.promoted_concept_id ? (
          <div>
            <dt>Saved mapping</dt>
            <dd>{candidate.promoted_concept_id || "Saved"}</dd>
          </div>
        ) : null}
        {candidate.action || candidate.act_result?.action ? (
          <div>
            <dt>Last action</dt>
            <dd>{candidate.action || candidate.act_result?.action}</dd>
          </div>
        ) : null}
        {canActOnStagedItem(item) ? (
          <div>
            <dt>Act</dt>
            <dd>{actDescriptionForStagedItem(item)}</dd>
          </div>
        ) : !isFacet ? (
          <div>
            <dt>Note</dt>
            <dd>Reject clears this exception without side effects.</dd>
          </div>
        ) : null}
      </dl>
    </aside>
  );
}

function StagedRow({
  item,
  busyId,
  overrides,
  onSelect,
  onApprove,
  onReject,
  patchOverride,
  overrideFor,
  selected,
}) {
  const candidate = item.candidate || {};
  const suggested =
    candidate.suggested_concept_id || candidate.suggested_canonical_name || "";
  const pending = item.status === "pending";
  const isFacet = item.target_entity_type === "facet";
  const actLabel = actLabelForStagedItem(item);
  const actDescription = actDescriptionForStagedItem(item);
  const title = stagedItemDisplayTitle(item) || "Untitled";
  return (
    <li>
      <article
        className={`review-prompt-card knowledge-ops-row${selected ? " is-selected" : ""}`}
        data-testid={`taxonomy-row-${item.id}`}
        onClick={() => onSelect(item)}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") onSelect(item);
        }}
        role="button"
        tabIndex={0}
      >
        <strong>
          {title}
          {candidate.hit_count != null ? ` · ${candidate.hit_count} hits` : ""}
        </strong>
        <p>
          {knowledgeTaskDisplayName(item.task_name)}
          {candidate.deficit_kind
            ? ` · ${knowledgeGapDisplayName(candidate.deficit_kind)}`
            : ""}
          {" · confidence "}
          {(Number(item.confidence_score) || 0).toFixed(2)}
          {suggested ? ` · suggested ${suggested}` : ""}
        </p>
        <small>
          {item.status}
          {candidate.context_source ? ` · ${candidate.context_source}` : ""}
          {item.created_at ? ` · ${new Date(item.created_at).toLocaleString()}` : ""}
        </small>
        {pending ? (
          <div className="media-issue-actions" style={{ flexWrap: "wrap", gap: "0.5rem" }}>
            {isFacet ? (
              <>
                <label className="tag-sort-control">
                  <span>Known group ID</span>
                  <input
                    type="text"
                    placeholder={candidate.suggested_concept_id || "science_fiction"}
                    value={overrideFor(item.id).concept_id}
                    onChange={(event) =>
                      patchOverride(item.id, { concept_id: event.target.value })
                    }
                    onClick={(event) => event.stopPropagation()}
                    data-testid={`taxonomy-concept-${item.id}`}
                  />
                </label>
                <label className="tag-sort-control">
                  <span>Or standard genre name</span>
                  <input
                    type="text"
                    placeholder={candidate.suggested_canonical_name || "Science Fiction"}
                    value={overrideFor(item.id).canonical_name}
                    onChange={(event) =>
                      patchOverride(item.id, { canonical_name: event.target.value })
                    }
                    onClick={(event) => event.stopPropagation()}
                    data-testid={`taxonomy-canonical-${item.id}`}
                  />
                </label>
                <button
                  type="button"
                  disabled={busyId === item.id}
                  onClick={(event) => {
                    event.stopPropagation();
                    onApprove(item);
                  }}
                  data-testid={`taxonomy-approve-${item.id}`}
                >
                  Save mapping
                </button>
              </>
            ) : actLabel ? (
              <button
                type="button"
                disabled={busyId === item.id}
                title={actDescription}
                onClick={(event) => {
                  event.stopPropagation();
                  onApprove(item);
                }}
                data-testid={`taxonomy-act-${item.id}`}
              >
                {actLabel}
              </button>
            ) : null}
            <button
              type="button"
              className="ghost"
              disabled={busyId === item.id}
              onClick={(event) => {
                event.stopPropagation();
                onReject(item);
              }}
              data-testid={`taxonomy-reject-${item.id}`}
            >
              Reject
            </button>
          </div>
        ) : null}
      </article>
    </li>
  );
}

/**
 * Admin → Library knowledge: activity, queued reviews, and saved name mappings.
 * Route and backend identifiers stay stable; only owner-facing copy is translated.
 */
export default function StagedAugmentationsPage() {
  const [tab, setTab] = useState("taxonomy");
  const [statusFilter, setStatusFilter] = useState("pending");
  const [summary, setSummary] = useState(null);
  const [registry, setRegistry] = useState(null);
  const [trend, setTrend] = useState([]);
  const [topEvents, setTopEvents] = useState([]);
  const [items, setItems] = useState([]);
  const [selected, setSelected] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [feedback, setFeedback] = useState("");
  const [busyId, setBusyId] = useState(null);
  const [overrides, setOverrides] = useState({});

  const coverageRows = useMemo(
    () => buildKnowledgeCoverageRows(summary?.coverage),
    [summary?.coverage],
  );
  const coverageSummary = useMemo(
    () => summarizeKnowledgeCoverage(summary?.coverage),
    [summary?.coverage],
  );

  const reloadSummary = useCallback(async () => {
    try {
      const [summaryData, registryData, trendData, topData] = await Promise.all([
        getKnowledgeOpsSummary(),
        getKnowledgeOpsTaxonomyRegistry(),
        getKnowledgeOpsTelemetryTrend({ days: 30 }),
        getKnowledgeOpsTelemetryTopEvents({ limit: 15 }),
      ]);
      setSummary(summaryData);
      setRegistry(registryData);
      setTrend(trendData?.series || []);
      setTopEvents(topData?.items || []);
    } catch (err) {
      setSummary(null);
      setError(err.message || "Could not load library knowledge summary.");
    }
  }, []);

  const reloadItems = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const taskName = TASK_FILTERS[tab];
      const data = await listStagedAugmentations({
        status: statusFilter === "all" ? "all" : statusFilter,
        task_name: taskName || undefined,
        limit: 100,
      });
      setItems(data?.items || []);
    } catch (err) {
      setItems([]);
      setError(err.message || "Could not load staged candidates.");
    } finally {
      setLoading(false);
    }
  }, [statusFilter, tab]);

  useEffect(() => {
    reloadSummary();
  }, [reloadSummary]);

  useEffect(() => {
    if (tab === "activity") return;
    reloadItems();
  }, [reloadItems, tab]);

  function overrideFor(id) {
    return overrides[id] || { concept_id: "", canonical_name: "" };
  }

  function patchOverride(id, patch) {
    setOverrides((prev) => ({
      ...prev,
      [id]: { ...overrideFor(id), ...patch },
    }));
  }

  async function handleApprove(item) {
    setBusyId(item.id);
    setFeedback("");
    try {
      const ov = overrideFor(item.id);
      const payload = {};
      if (ov.concept_id.trim()) payload.concept_id = ov.concept_id.trim();
      if (ov.canonical_name.trim()) payload.canonical_name = ov.canonical_name.trim();
      const result = await approveStagedAugmentation(item.id, payload);
      if (result?.acted?.action) {
        setFeedback("Knowledge refresh started.");
      } else if (result?.promoted?.alias) {
        const alias =
          result.promoted.alias ||
          stagedItemDisplayTitle(item) ||
          "name";
        setFeedback(`Saved “${alias}” as a recognized name.`);
      } else {
        setFeedback("Saved mapping.");
      }
      await Promise.all([reloadItems(), reloadSummary()]);
    } catch (err) {
      setError(err.message || "Could not save this mapping.");
    } finally {
      setBusyId(null);
    }
  }

  async function handleReject(item) {
    setBusyId(item.id);
    setFeedback("");
    try {
      await rejectStagedAugmentation(item.id);
      const label = stagedItemDisplayTitle(item) || "item";
      setFeedback(`Rejected “${label}”.`);
      if (selected?.id === item.id) setSelected(null);
      await Promise.all([reloadItems(), reloadSummary()]);
    } catch (err) {
      setError(err.message || "Reject failed.");
    } finally {
      setBusyId(null);
    }
  }

  const topFacets = registry?.top_unresolved_facets || [];

  return (
    <div className="settings-stack knowledge-ops-page" data-testid="admin-taxonomy">
      <SettingsPageHeader title="Library knowledge">
        Save name mappings when genres or tags are unrecognized. Missing synopses and plot details
        usually fill in during idle enrichment — only stuck exceptions need a force refresh here.
      </SettingsPageHeader>

      <SectionHelp label="How library knowledge improves" testId="knowledge-ops-loop-help">
        <p>
          <strong>Name mappings are the human review queue.</strong> Unrecognized genre and tag
          names wait under Name mappings so you can save an overlay for this installation (built-in
          definitions stay unchanged). Requested details and Missing knowledge are titled
          exceptions — idle enrichment fills most gaps; use Refresh synopsis or Reject when
          something is stuck.
        </p>
      </SectionHelp>

      {feedback ? (
        <p className="status status-success" data-testid="taxonomy-feedback">
          {feedback}
        </p>
      ) : null}
      {error ? (
        <p className="error" data-testid="taxonomy-error">
          {error}
        </p>
      ) : null}

      <SummaryStrip summary={summary} loading={!summary && !error} />

      <nav className="knowledge-ops-tabs" aria-label="Library knowledge sections" data-testid="knowledge-ops-tabs">
        {TABS.map((entry) => (
          <button
            key={entry.id}
            type="button"
            className={tab === entry.id ? "is-active" : ""}
            onClick={() => {
              setTab(entry.id);
              setSelected(null);
            }}
            data-testid={`knowledge-ops-tab-${entry.id}`}
          >
            {entry.label}
          </button>
        ))}
      </nav>

      {tab === "taxonomy" ? (
        <>
          <SettingsPanel
            title="Recognized names"
            lead="Built-in genre and tag names, plus the mappings you have saved."
            testId="knowledge-ops-registry-panel"
          >
            <ul className="knowledge-ops-meta-list" data-testid="knowledge-ops-registry-counts">
              <li>Known groups: {registry?.registry?.concept_count ?? "—"}</li>
              <li>Recognized names: {registry?.registry?.alias_count ?? "—"}</li>
              <li>Built-in sets: {registry?.registry?.pack_count ?? "—"}</li>
              <li>Your saved mappings: {registry?.registry?.overlay_alias_count ?? 0}</li>
              <li>
                Saved-name file:{" "}
                {registry?.registry?.overlay_exists
                  ? "ready"
                  : "not created yet"}
              </li>
            </ul>
          </SettingsPanel>
          <SettingsPanel
            title="Names to review"
            lead="Frequently seen genre or tag names that are not recognized yet."
            testId="knowledge-ops-top-facets-panel"
          >
            {topFacets.length === 0 ? (
              <p className="status status-secondary" data-testid="knowledge-ops-top-facets-empty">
                No unrecognized names yet. Saved mappings will keep this list tidy.
              </p>
            ) : (
              <ul className="knowledge-ops-hit-list" data-testid="knowledge-ops-top-facets">
                {topFacets.map((row) => (
                  <li key={row.entity_key}>
                    <strong>{row.entity_key}</strong>
                    <span>{row.hit_count} hits</span>
                    {row.payload?.context_source ? (
                      <small>{row.payload.context_source}</small>
                    ) : null}
                  </li>
                ))}
              </ul>
            )}
          </SettingsPanel>
        </>
      ) : null}

      {tab === "demand" ? (
        <SettingsPanel
          title="Requested title details"
          lead="Exceptions only — idle enrichment usually fills these on its own."
          testId="knowledge-ops-demand-panel"
        >
          <p className="status status-secondary">
            Rows below are titled exceptions that still need a forced lookup. Use{" "}
            <strong>Refresh synopsis</strong> to look again, or Reject to clear the exception
            without changing the title.
          </p>
        </SettingsPanel>
      ) : null}

      {tab === "coverage" ? (
        <SettingsPanel
          title="Missing library knowledge"
          lead="Coverage snapshot plus titled exceptions you can force-refresh or dismiss."
          testId="knowledge-ops-coverage-panel"
        >
          {coverageSummary ? (
            <p data-testid="knowledge-ops-coverage-summary">{coverageSummary}</p>
          ) : null}
          <ul className="knowledge-coverage-grid" data-testid="knowledge-ops-coverage-grid">
            {coverageRows.map((row) => (
              <li key={row.id} className="knowledge-coverage-metric" data-testid={`knowledge-ops-coverage-${row.id}`}>
                <span className="knowledge-coverage-metric-value">{row.pctLabel}</span>
                <span className="knowledge-coverage-metric-label">{row.label}</span>
                {row.detail ? (
                  <span className="knowledge-coverage-metric-detail">{row.detail}</span>
                ) : null}
              </li>
            ))}
          </ul>
        </SettingsPanel>
      ) : null}

      {tab === "activity" ? (
        <>
          <SettingsPanel title="Activity trend (30d)" testId="knowledge-ops-trend-panel">
            <Sparkline series={trend} />
          </SettingsPanel>
          <SettingsPanel title="Most common findings" testId="knowledge-ops-top-events-panel">
            {topEvents.length === 0 ? (
              <p className="status status-secondary">No library-knowledge activity recorded yet.</p>
            ) : (
              <ul className="knowledge-ops-hit-list" data-testid="knowledge-ops-top-events">
                {topEvents.map((row) => (
                  <li key={`${row.event_type}:${row.entity_type}:${row.entity_key}`}>
                    <strong>{knowledgeEventDisplayName(row.event_type)}</strong>
                    <span>
                      {row.entity_type}:{row.entity_key} · {row.hit_count} hits
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </SettingsPanel>
        </>
      ) : null}

      {tab !== "activity" ? (
        <>
          <label className="tag-sort-control">
            <span>Status</span>
            <select
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value)}
              data-testid="taxonomy-status-filter"
            >
              <option value="pending">Pending</option>
              <option value="approved">Approved</option>
              <option value="rejected">Rejected</option>
              <option value="all">All</option>
            </select>
          </label>

          <div className="knowledge-ops-work-layout">
            <SettingsPanel
              title={
                tab === "all"
                  ? "All exceptions"
                  : tab === "taxonomy"
                    ? "Name mappings"
                    : tab === "demand"
                      ? "Requested details"
                      : "Missing knowledge"
              }
              lead={
                tab === "taxonomy"
                  ? "Primary review: match each unrecognized name to a known group, then Save mapping."
                  : tab === "demand"
                    ? "Titled exceptions — Refresh synopsis or Reject. Idle enrichment handles most requests."
                    : tab === "all"
                      ? "Name mappings need review; other rows are titled exceptions for refresh or reject."
                      : "Titled coverage exceptions — Refresh synopsis or Reject; background fill is primary."
              }
              testId="taxonomy-staged-panel"
            >
              {loading ? <p className="status status-secondary">Loading…</p> : null}
              {!loading && items.length === 0 ? (
                <p className="status status-secondary" data-testid="taxonomy-empty">
                  {tab === "taxonomy"
                    ? "No name mappings waiting. Unrecognized genres and tags appear here after they are noticed often enough to merit review."
                    : "No titled exceptions for this filter. Idle enrichment fills most gaps; stuck items appear here for a force refresh or reject."}
                </p>
              ) : null}
              <ul className="media-issues-list" data-testid="taxonomy-staged-list">
                {items.map((item) => (
                  <StagedRow
                    key={item.id}
                    item={item}
                    busyId={busyId}
                    overrides={overrides}
                    onSelect={setSelected}
                    onApprove={handleApprove}
                    onReject={handleReject}
                    patchOverride={patchOverride}
                    overrideFor={overrideFor}
                    selected={selected?.id === item.id}
                  />
                ))}
              </ul>
            </SettingsPanel>
            <ContextPanel item={selected} onClose={() => setSelected(null)} />
          </div>
        </>
      ) : null}
    </div>
  );
}
