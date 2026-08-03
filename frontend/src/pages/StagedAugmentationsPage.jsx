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
} from "../lib/knowledgeOpsActions.js";

const TABS = [
  { id: "taxonomy", label: "Taxonomy" },
  { id: "demand", label: "Demand" },
  { id: "coverage", label: "Coverage" },
  { id: "activity", label: "Activity" },
  { id: "all", label: "All staged work" },
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
          <span className="dash-stat-label">Pending facet aliases</span>
        </div>
        <div className="dash-stat-card" data-testid="knowledge-ops-stat-all-pending">
          <span className="dash-stat-value">{summary.pending_all_augmentations ?? 0}</span>
          <span className="dash-stat-label">Pending all augmentations</span>
        </div>
        <div className="dash-stat-card" data-testid="knowledge-ops-stat-signals-7d">
          <span className="dash-stat-value">{summary.signals_7d ?? 0}</span>
          <span className="dash-stat-label">Signals (7d)</span>
        </div>
        <div className="dash-stat-card" data-testid="knowledge-ops-stat-signals-30d">
          <span className="dash-stat-value">{summary.signals_30d ?? 0}</span>
          <span className="dash-stat-label">Signals (30d)</span>
        </div>
        <div className="dash-stat-card" data-testid="knowledge-ops-stat-approve-rate">
          <span className="dash-stat-value">{formatRate(summary.approve_rate_30d)}</span>
          <span className="dash-stat-label">Approve rate (30d)</span>
        </div>
        <div className="dash-stat-card" data-testid="knowledge-ops-stat-reject-rate">
          <span className="dash-stat-value">{formatRate(summary.reject_rate_30d)}</span>
          <span className="dash-stat-label">Reject rate (30d)</span>
        </div>
      </div>
      <div className="knowledge-ops-funnel" data-testid="knowledge-ops-funnel">
        <h3 className="knowledge-ops-section-title">Closed-loop funnel</h3>
        <FunnelBar label="observed" value={funnel.observed ?? 0} max={funnel.observed ?? 1} />
        <FunnelBar
          label="at-threshold"
          value={funnel.at_threshold ?? 0}
          max={funnel.observed ?? 1}
        />
        <FunnelBar
          label="staged-pending"
          value={funnel.staged_pending ?? 0}
          max={funnel.observed ?? 1}
        />
        <FunnelBar
          label="approved"
          value={funnel.staged_approved ?? 0}
          max={funnel.observed ?? 1}
          accent="var(--success, #6bcf7f)"
        />
        <FunnelBar
          label="rejected"
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
          <dd>{item.task_name}</dd>
        </div>
        <div>
          <dt>Tier</dt>
          <dd>{item.priority_tier}</dd>
        </div>
        <div>
          <dt>Entity</dt>
          <dd>
            {item.target_entity_type}:{item.target_entity_id}
          </dd>
        </div>
        {candidate.alias ? (
          <div>
            <dt>Alias token</dt>
            <dd>{candidate.alias}</dd>
          </div>
        ) : null}
        {candidate.suggested_concept_id ? (
          <div>
            <dt>Suggested concept</dt>
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
            <dt>Deficit</dt>
            <dd>{candidate.deficit_kind}</dd>
          </div>
        ) : null}
        {candidate.reason ? (
          <div>
            <dt>Why</dt>
            <dd>{candidate.reason}</dd>
          </div>
        ) : null}
        {candidate.name ? (
          <div>
            <dt>Name</dt>
            <dd>{candidate.name}</dd>
          </div>
        ) : null}
        {candidate.overlay_path || candidate.promoted_concept_id ? (
          <div>
            <dt>Overlay</dt>
            <dd>{candidate.overlay_path || candidate.promoted_concept_id || "—"}</dd>
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
            <dd>Reject clears this candidate without side effects.</dd>
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
  const title =
    candidate.alias ||
    candidate.name ||
    candidate.keyword ||
    item.target_entity_id;
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
          {item.task_name}
          {candidate.deficit_kind ? ` · ${candidate.deficit_kind}` : ""}
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
                  <span>Concept id</span>
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
                  <span>Or TMDB name</span>
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
                  Approve → overlay
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
 * Admin → Knowledge Ops: closed-loop telemetry, staged work, facet approve/reject.
 * Route stays `/admin/taxonomy`; approve writes DATA_DIR/taxonomy.json overlay only.
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
      setError(err.message || "Could not load Knowledge Ops summary.");
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
        setFeedback(`Acted: ${result.acted.action}.`);
      } else if (result?.promoted?.alias) {
        const alias = result.promoted.alias || item.candidate?.alias || item.target_entity_id;
        setFeedback(`Approved “${alias}” into the DATA_DIR taxonomy overlay.`);
      } else {
        setFeedback("Approved staged candidate.");
      }
      await Promise.all([reloadItems(), reloadSummary()]);
    } catch (err) {
      setError(err.message || "Approve failed.");
    } finally {
      setBusyId(null);
    }
  }

  async function handleReject(item) {
    setBusyId(item.id);
    setFeedback("");
    try {
      await rejectStagedAugmentation(item.id);
      setFeedback(`Rejected “${item.candidate?.alias || item.target_entity_id}”.`);
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
      <SettingsPageHeader title="Knowledge Operations">
        Closed-loop knowledge: signals accumulate in telemetry, high-confidence gaps stage for
        review, and facet aliases promote into your DATA_DIR overlay — never the packaged seed.
      </SettingsPageHeader>

      <SectionHelp label="How the closed loop works" testId="knowledge-ops-loop-help">
        <p>
          <strong>Signal → stage → owner overlay.</strong> Chat, Explore, and idle tasks emit
          misses and coverage gaps into SQLite telemetry. Audit tasks stage candidates when hit
          counts cross confidence thresholds. You approve facet aliases into{" "}
          <code>$DATA_DIR/taxonomy.json</code>; packaged seed is never auto-mutated. Fail closed.
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

      <nav className="knowledge-ops-tabs" aria-label="Knowledge Ops sections" data-testid="knowledge-ops-tabs">
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
            title="Registry snapshot"
            lead="Packaged concepts/aliases/packs plus your overlay merge at boot."
            testId="knowledge-ops-registry-panel"
          >
            <ul className="knowledge-ops-meta-list" data-testid="knowledge-ops-registry-counts">
              <li>Concepts: {registry?.registry?.concept_count ?? "—"}</li>
              <li>Aliases: {registry?.registry?.alias_count ?? "—"}</li>
              <li>Packs: {registry?.registry?.pack_count ?? "—"}</li>
              <li>Overlay aliases: {registry?.registry?.overlay_alias_count ?? 0}</li>
              <li>
                Overlay:{" "}
                {registry?.registry?.overlay_exists
                  ? registry?.registry?.overlay_path || "present"
                  : "none yet"}
              </li>
            </ul>
          </SettingsPanel>
          <SettingsPanel
            title="Top unresolved facets"
            lead="Highest-hit unmapped facet tokens from closed-loop telemetry."
            testId="knowledge-ops-top-facets-panel"
          >
            {topFacets.length === 0 ? (
              <p className="status status-secondary" data-testid="knowledge-ops-top-facets-empty">
                No unresolved facet signals yet — aliases you approve will shrink this list.
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
          title="Entity memory demand"
          lead="P2 metadata_demand signals staged by entity_memory_enrichment."
          testId="knowledge-ops-demand-panel"
        >
          <p className="status status-secondary">
            Demand rows appear below with task <code>entity_memory_enrichment</code>.
            Use <strong>Run enrichment</strong> to refresh repository-memory research for the
            entity, or Reject to clear without side effects.
          </p>
        </SettingsPanel>
      ) : null}

      {tab === "coverage" ? (
        <SettingsPanel
          title="Library coverage deficits"
          lead="Honest % from idle enrichment; gaps emit coverage_deficit telemetry."
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
          <SettingsPanel title="Signal trend (30d)" testId="knowledge-ops-trend-panel">
            <Sparkline series={trend} />
          </SettingsPanel>
          <SettingsPanel title="Top telemetry events" testId="knowledge-ops-top-events-panel">
            {topEvents.length === 0 ? (
              <p className="status status-secondary">No closed-loop events recorded yet.</p>
            ) : (
              <ul className="knowledge-ops-hit-list" data-testid="knowledge-ops-top-events">
                {topEvents.map((row) => (
                  <li key={`${row.event_type}:${row.entity_type}:${row.entity_key}`}>
                    <strong>{row.event_type}</strong>
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
                  ? "All staged work"
                  : tab === "taxonomy"
                    ? "Staged facet aliases"
                    : tab === "demand"
                      ? "Staged demand"
                      : "Staged coverage gaps"
              }
              lead={
                tab === "taxonomy"
                  ? "Map tokens to concept ids or live TMDB genre names, then approve into overlay."
                  : tab === "demand"
                    ? "Approve runs repository-memory enrichment for the entity — never writes taxonomy overlay."
                    : "Approve runs targeted enrichment for the gap kind — never auto-mutates packaged seed."
              }
              testId="taxonomy-staged-panel"
            >
              {loading ? <p className="status status-secondary">Loading…</p> : null}
              {!loading && items.length === 0 ? (
                <p className="status status-secondary" data-testid="taxonomy-empty">
                  No staged candidates for this filter — empty means signals have not crossed staging
                  thresholds yet.
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
