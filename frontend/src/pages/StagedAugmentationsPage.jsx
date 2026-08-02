import { useCallback, useEffect, useState } from "react";
import {
  approveStagedAugmentation,
  listStagedAugmentations,
  rejectStagedAugmentation,
} from "../api/client";
import SettingsPageHeader from "../components/settings/SettingsPageHeader";
import SettingsPanel from "../components/settings/SettingsPanel";

/**
 * Admin → Taxonomy: review staged facet alias candidates.
 * Approve writes DATA_DIR/taxonomy.json overlay only (never the packaged seed).
 */
export default function StagedAugmentationsPage() {
  const [statusFilter, setStatusFilter] = useState("pending");
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [feedback, setFeedback] = useState("");
  const [busyId, setBusyId] = useState(null);
  const [overrides, setOverrides] = useState({});

  const reload = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await listStagedAugmentations({
        status: statusFilter === "all" ? "all" : statusFilter,
        task_name: "facet_taxonomy_audit",
      });
      setItems(data?.items || []);
    } catch (err) {
      setItems([]);
      setError(err.message || "Could not load staged facet candidates.");
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    reload();
  }, [reload]);

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
      const alias = result?.promoted?.alias || item.candidate?.alias || item.target_entity_id;
      setFeedback(`Approved “${alias}” into the DATA_DIR taxonomy overlay.`);
      await reload();
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
      await reload();
    } catch (err) {
      setError(err.message || "Reject failed.");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="settings-stack" data-testid="admin-taxonomy">
      <SettingsPageHeader title="Taxonomy">
        Review unmapped facet tokens the household hit in chat or Explore. Approving writes an
        alias into your DATA_DIR overlay so it survives upgrades — never into the packaged seed.
      </SettingsPageHeader>

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

      <SettingsPanel
        title="Staged facet aliases"
        lead="Candidates come from the facet_taxonomy_audit idle task. Map a token to an existing concept id (preferred) or a live TMDB genre name."
        testId="taxonomy-staged-panel"
      >
        {loading ? <p className="status status-secondary">Loading…</p> : null}
        {!loading && items.length === 0 ? (
          <p className="status status-secondary" data-testid="taxonomy-empty">
            No staged facet candidates for this filter.
          </p>
        ) : null}
        <ul className="media-issues-list" data-testid="taxonomy-staged-list">
          {items.map((item) => {
            const candidate = item.candidate || {};
            const suggested =
              candidate.suggested_concept_id ||
              candidate.suggested_canonical_name ||
              "";
            const pending = item.status === "pending";
            return (
              <li key={item.id}>
                <article
                  className="review-prompt-card"
                  data-testid={`taxonomy-row-${item.id}`}
                >
                  <strong>
                    {candidate.alias || item.target_entity_id}
                    {candidate.hit_count != null ? ` · ${candidate.hit_count} hits` : ""}
                  </strong>
                  <p>
                    Confidence {(Number(item.confidence_score) || 0).toFixed(2)}
                    {suggested ? ` · suggested ${suggested}` : " · needs a mapping"}
                  </p>
                  <small>
                    {item.status}
                    {candidate.context_source ? ` · ${candidate.context_source}` : ""}
                    {item.created_at ? ` · ${new Date(item.created_at).toLocaleString()}` : ""}
                  </small>
                  {pending ? (
                    <div className="media-issue-actions" style={{ flexWrap: "wrap", gap: "0.5rem" }}>
                      <label className="tag-sort-control">
                        <span>Concept id</span>
                        <input
                          type="text"
                          placeholder={candidate.suggested_concept_id || "science_fiction"}
                          value={overrideFor(item.id).concept_id}
                          onChange={(event) =>
                            patchOverride(item.id, { concept_id: event.target.value })
                          }
                          data-testid={`taxonomy-concept-${item.id}`}
                        />
                      </label>
                      <label className="tag-sort-control">
                        <span>Or TMDB name</span>
                        <input
                          type="text"
                          placeholder={
                            candidate.suggested_canonical_name || "Science Fiction"
                          }
                          value={overrideFor(item.id).canonical_name}
                          onChange={(event) =>
                            patchOverride(item.id, { canonical_name: event.target.value })
                          }
                          data-testid={`taxonomy-canonical-${item.id}`}
                        />
                      </label>
                      <button
                        type="button"
                        disabled={busyId === item.id}
                        onClick={() => handleApprove(item)}
                        data-testid={`taxonomy-approve-${item.id}`}
                      >
                        Approve → overlay
                      </button>
                      <button
                        type="button"
                        className="ghost"
                        disabled={busyId === item.id}
                        onClick={() => handleReject(item)}
                        data-testid={`taxonomy-reject-${item.id}`}
                      >
                        Reject
                      </button>
                    </div>
                  ) : null}
                </article>
              </li>
            );
          })}
        </ul>
      </SettingsPanel>
    </div>
  );
}
