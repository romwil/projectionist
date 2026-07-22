import { useCallback, useEffect, useState } from "react";
import {
  approveAccessRequest,
  denyAccessRequest,
  listAccessRequests,
} from "../api/client";

/**
 * Owner inbox for CuratorX-owned request-access queue (Admin → Access).
 */
export default function AccessRequestsPage() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [feedback, setFeedback] = useState("");
  const [busyId, setBusyId] = useState("");

  const reload = useCallback(() => {
    setLoading(true);
    listAccessRequests()
      .then((data) => {
        setItems(data?.items || []);
        setError("");
      })
      .catch((err) => setError(err.message || "Could not load access requests."))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  async function handleApprove(id) {
    setBusyId(id);
    setFeedback("");
    try {
      const result = await approveAccessRequest(id);
      const hint = result?.temporary_password
        ? ` Approved. Temporary password: ${result.temporary_password}`
        : ` ${result?.sign_in_hint || "Approved."}`;
      setFeedback(hint.trim());
      reload();
    } catch (err) {
      setFeedback(err.message || "Approve failed.");
    } finally {
      setBusyId("");
    }
  }

  async function handleDeny(id) {
    setBusyId(id);
    setFeedback("");
    try {
      await denyAccessRequest(id);
      setFeedback("Request denied.");
      reload();
    } catch (err) {
      setFeedback(err.message || "Deny failed.");
    } finally {
      setBusyId("");
    }
  }

  return (
    <div className="dash-page" data-testid="access-requests-page">
      <header className="dash-hero">
        <p className="eyebrow">Household</p>
        <h1>Access requests</h1>
        <p>
          Guests can ask to join without a Seerr account. Approving creates a member invite when local
          login is on; otherwise ask them to sign in with Plex or SSO.
        </p>
      </header>

      {loading ? <p className="status status-secondary">Loading…</p> : null}
      {error ? <p className="error">{error}</p> : null}
      {feedback ? (
        <p className="status status-success" data-testid="access-requests-feedback">
          {feedback}
        </p>
      ) : null}

      {!loading && !items.length ? (
        <p className="dash-empty" data-testid="access-requests-empty">
          No access requests yet.
        </p>
      ) : null}

      <ul className="access-request-list" data-testid="access-request-list">
        {items.map((item) => (
          <li key={item.id} className="access-request-row" data-testid={`access-request-${item.id}`}>
            <div>
              <strong>{item.display_name}</strong>
              {item.email ? <span className="access-request-email">{item.email}</span> : null}
              {item.message ? <p className="access-request-message">{item.message}</p> : null}
              <p className="status status-secondary">
                {item.status} · {new Date(item.created_at * 1000).toLocaleString()}
              </p>
            </div>
            {item.status === "pending" ? (
              <div className="access-request-actions">
                <button
                  type="button"
                  className="primary"
                  disabled={busyId === item.id}
                  data-testid={`access-approve-${item.id}`}
                  onClick={() => handleApprove(item.id)}
                >
                  Approve
                </button>
                <button
                  type="button"
                  className="ghost"
                  disabled={busyId === item.id}
                  data-testid={`access-deny-${item.id}`}
                  onClick={() => handleDeny(item.id)}
                >
                  Deny
                </button>
              </div>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
}
