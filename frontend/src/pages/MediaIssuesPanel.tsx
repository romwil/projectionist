import { useCallback, useEffect, useState } from "react";
import { listMediaIssues, repairMediaIssue, updateMediaIssue } from "../api/client";

type MediaIssue = {
  id: string;
  title?: string;
  code?: string;
  note?: string;
  status?: string;
  created_at?: string | number;
  repair_log?: Array<{ message?: string }>;
};

type MediaIssuesState = {
  loading: boolean;
  items: MediaIssue[];
  error: string;
};

/** Media issue queue content — reused by Health tab and legacy redirect. */
export default function MediaIssuesPanel() {
  const [status, setStatus] = useState("open");
  const [state, setState] = useState<MediaIssuesState>({ loading: true, items: [], error: "" });
  const refresh = useCallback(async () => {
    setState((current) => ({ ...current, loading: true, error: "" }));
    try {
      const data = await listMediaIssues({ status });
      const payload = data as { items?: MediaIssue[] } | MediaIssue[];
      const items = Array.isArray(payload) ? payload : payload?.items || [];
      setState({ loading: false, items, error: "" });
    } catch (error: unknown) {
      setState({
        loading: false,
        items: [],
        error: error instanceof Error ? error.message : "Could not load issue reports.",
      });
    }
  }, [status]);
  useEffect(() => {
    refresh();
  }, [refresh]);

  async function resolve(issue: MediaIssue) {
    await updateMediaIssue(issue.id, { status: "resolved" });
    refresh();
  }

  async function repair(issue: MediaIssue) {
    await repairMediaIssue(issue.id);
    refresh();
  }

  return (
    <div className="media-issues-panel" data-testid="media-issues-page">
      <section className="explore-section-hero">
        <p className="person-eyebrow">Owner tools</p>
        <h2>Media issue queue</h2>
        <p className="explore-section-subtitle">
          Reports are reviewable evidence. Repairs are explicit, logged owner actions—not
          member-triggered file changes.
        </p>
      </section>
      <label className="tag-sort-control">
        <span>Status</span>
        <select value={status} onChange={(event) => setStatus(event.target.value)}>
          <option value="">All</option>
          <option value="open">Open</option>
          <option value="approved">Approved</option>
          <option value="repairing">Repairing</option>
          <option value="resolved">Resolved</option>
          <option value="rejected">Rejected</option>
        </select>
      </label>
      {state.loading ? <p className="status status-secondary">Loading…</p> : null}
      {state.error ? <p className="error">{state.error}</p> : null}
      <div className="media-issues-list">
        {state.items.map((issue) => (
          <article key={issue.id} className="review-prompt-card">
            <strong>
              {issue.title || "Untitled"} · {issue.code}
            </strong>
            <p>{issue.note || "No note provided."}</p>
            <small>
              {issue.status} · {issue.created_at ? new Date(issue.created_at).toLocaleString() : ""}
            </small>
            {issue.repair_log?.length ? (
              <p className="status status-secondary">
                Latest repair: {issue.repair_log.at(-1)?.message || "recorded"}
              </p>
            ) : null}
            {issue.status !== "resolved" ? (
              <div className="media-issue-actions">
                <button type="button" className="primary" onClick={() => repair(issue)}>
                  Run repair
                </button>
                <button className="ghost" type="button" onClick={() => resolve(issue)}>
                  Resolve
                </button>
              </div>
            ) : null}
          </article>
        ))}
      </div>
    </div>
  );
}
