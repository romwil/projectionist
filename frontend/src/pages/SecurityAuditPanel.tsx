import { useEffect, useState } from "react";
import { getSecurityAudit } from "../api/client";
import { auditDetailLine, auditEventLabel } from "../lib/ownerOps.js";

const PAGE_SIZE = 50;

type AuditRow = {
  id: number;
  created_at: number;
  event: string;
  actor_id?: string | null;
  target_id?: string | null;
  outcome: string;
  detail?: Record<string, unknown>;
};

type AuditPage = {
  items: AuditRow[];
  total: number;
  events: string[];
  user_names: Record<string, string>;
};

/** Owner-only trail of sign-ins, passwords, invites, roles, and settings saves. Stored on this server. */
export default function SecurityAuditPanel() {
  const [event, setEvent] = useState("");
  const [userId, setUserId] = useState("");
  const [offset, setOffset] = useState(0);
  const [page, setPage] = useState<AuditPage | null>(null);
  const [error, setError] = useState("");
  const requestKey = `${event}|${userId}|${offset}`;
  const [settledKey, setSettledKey] = useState("");
  const loading = settledKey !== requestKey;

  useEffect(() => {
    let cancelled = false;
    getSecurityAudit({ event, userId, limit: PAGE_SIZE, offset })
      .then((next) => {
        if (cancelled) return;
        setPage(next as AuditPage);
        setError("");
      })
      .catch((err) => {
        if (!cancelled) setError((err as { message?: string })?.message || "Couldn't load the security log.");
      })
      .finally(() => {
        if (!cancelled) setSettledKey(requestKey);
      });
    return () => {
      cancelled = true;
    };
  }, [event, userId, offset, requestKey]);

  const names = page?.user_names || {};
  const nameFor = (id?: string | null) => (id ? names[id] || id : "");
  const total = page?.total || 0;

  return (
    <div className="media-issues-panel" data-testid="security-audit-panel">
      <section className="explore-section-hero">
        <p className="person-eyebrow">Owner tools</p>
        <h2>Security log</h2>
        <p className="explore-section-subtitle">
          Sign-ins, password changes, invites, role changes, and settings saves. Only owners can
          read this. It records who and what changed — never passwords, keys, or setting values —
          and it stays on this server.
        </p>
      </section>
      <div className="config-actions">
        <label className="tag-sort-control">
          <span>Event</span>
          <select
            value={event}
            data-testid="security-audit-event-filter"
            onChange={(e) => {
              setOffset(0);
              setEvent(e.target.value);
            }}
          >
            <option value="">All events</option>
            {(page?.events || []).map((name) => (
              <option key={name} value={name}>
                {auditEventLabel(name)}
              </option>
            ))}
          </select>
        </label>
        <label className="tag-sort-control">
          <span>Person</span>
          <select
            value={userId}
            data-testid="security-audit-user-filter"
            onChange={(e) => {
              setOffset(0);
              setUserId(e.target.value);
            }}
          >
            <option value="">Everyone</option>
            {Object.entries(names).map(([id, name]) => (
              <option key={id} value={id}>
                {name || id}
              </option>
            ))}
          </select>
        </label>
      </div>
      {loading && !page ? <p className="status status-secondary">Loading…</p> : null}
      {error ? <p className="error">{error}</p> : null}
      {page && !page.items.length ? (
        <p className="status status-secondary" data-testid="security-audit-empty">
          Nothing logged for this filter yet.
        </p>
      ) : null}
      {page?.items.length ? (
        <div className="user-management-table-wrap">
          <table className="user-management-table" data-testid="security-audit-table">
            <thead>
              <tr>
                <th>When</th>
                <th>What</th>
                <th>Who</th>
                <th>For</th>
                <th>Detail</th>
              </tr>
            </thead>
            <tbody>
              {page.items.map((row) => (
                <tr key={row.id} data-testid={`security-audit-row-${row.id}`}>
                  <td>{new Date(row.created_at * 1000).toLocaleString()}</td>
                  <td>
                    {auditEventLabel(row.event)}
                    {row.outcome !== "ok" ? ` (${row.outcome})` : ""}
                  </td>
                  <td>{nameFor(row.actor_id) || "—"}</td>
                  <td>{row.target_id && row.target_id !== row.actor_id ? nameFor(row.target_id) : "—"}</td>
                  <td>{auditDetailLine(row) || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {total > PAGE_SIZE ? (
        <div className="config-actions">
          <button
            type="button"
            className="ghost"
            disabled={offset === 0 || loading}
            onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
          >
            Newer
          </button>
          <span className="status status-secondary">
            {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} of {total}
          </span>
          <button
            type="button"
            className="ghost"
            disabled={offset + PAGE_SIZE >= total || loading}
            onClick={() => setOffset(offset + PAGE_SIZE)}
          >
            Older
          </button>
        </div>
      ) : null}
    </div>
  );
}
