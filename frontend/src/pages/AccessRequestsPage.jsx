import { useCallback, useEffect, useState } from "react";
import {
  approveAccessRequest,
  createInvite,
  denyAccessRequest,
  listAccessRequests,
  listInvites,
  revokeInvite,
} from "../api/client";

const DEFAULT_METHODS = ["plex", "oidc", "local"];

/**
 * Owner inbox for Projectionist-owned request-access queue + invite links (Admin → Access).
 */
export default function AccessRequestsPage() {
  const [items, setItems] = useState([]);
  const [invites, setInvites] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [feedback, setFeedback] = useState("");
  const [busyId, setBusyId] = useState("");
  const [joinLink, setJoinLink] = useState("");

  const [createRole, setCreateRole] = useState("member");
  const [createYouth, setCreateYouth] = useState(false);
  const [createEmail, setCreateEmail] = useState("");
  const [createMethods, setCreateMethods] = useState(DEFAULT_METHODS);
  const [approveOptions, setApproveOptions] = useState({});

  const reload = useCallback(() => {
    setLoading(true);
    Promise.all([listAccessRequests(), listInvites()])
      .then(([requests, inviteData]) => {
        setItems(requests?.items || []);
        setInvites(inviteData?.items || []);
        setError("");
      })
      .catch((err) => setError(err.message || "Could not load access."))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  function optionsFor(id) {
    return (
      approveOptions[id] || {
        role: "member",
        is_youth: false,
        allowed_methods: DEFAULT_METHODS,
      }
    );
  }

  function patchOptions(id, patch) {
    setApproveOptions((prev) => ({
      ...prev,
      [id]: { ...optionsFor(id), ...patch },
    }));
  }

  async function handleApprove(id) {
    setBusyId(id);
    setFeedback("");
    setJoinLink("");
    try {
      const opts = optionsFor(id);
      const result = await approveAccessRequest(id, {
        role: opts.role,
        is_youth: opts.is_youth,
        allowed_methods: opts.allowed_methods,
      });
      const path = result?.join_path || result?.join_url || "";
      if (path) {
        setJoinLink(path.startsWith("http") ? path : `${window.location.origin}${path}`);
      }
      setFeedback(
        result?.emailed
          ? "Approved and emailed the join link."
          : "Approved. Copy the join link below and share it.",
      );
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
      setFeedback("Request denied. Matching identities cannot redeem invites.");
      reload();
    } catch (err) {
      setFeedback(err.message || "Deny failed.");
    } finally {
      setBusyId("");
    }
  }

  async function handleCreateInvite(event) {
    event.preventDefault();
    setBusyId("create");
    setFeedback("");
    setJoinLink("");
    try {
      const result = await createInvite({
        role: createRole,
        is_youth: createYouth,
        email: createEmail.trim() || undefined,
        allowed_methods: createMethods,
      });
      const path = result?.join_path || result?.join_url || "";
      if (path) {
        setJoinLink(path.startsWith("http") ? path : `${window.location.origin}${path}`);
      }
      setFeedback(
        result?.emailed
          ? "Invite created and emailed."
          : "Invite created. Copy the join link below.",
      );
      setCreateEmail("");
      reload();
    } catch (err) {
      setFeedback(err.message || "Could not create invite.");
    } finally {
      setBusyId("");
    }
  }

  async function handleRevoke(id) {
    setBusyId(id);
    setFeedback("");
    try {
      await revokeInvite(id);
      setFeedback("Invite revoked.");
      reload();
    } catch (err) {
      setFeedback(err.message || "Revoke failed.");
    } finally {
      setBusyId("");
    }
  }

  async function copyJoinLink() {
    if (!joinLink) return;
    try {
      await navigator.clipboard.writeText(joinLink);
      setFeedback("Join link copied.");
    } catch {
      setFeedback("Could not copy — select the link manually.");
    }
  }

  function toggleMethod(list, method, checked) {
    const next = new Set(list);
    if (checked) next.add(method);
    else next.delete(method);
    return Array.from(next);
  }

  return (
    <div className="dash-page" data-testid="access-requests-page">
      <header className="dash-hero">
        <p className="eyebrow">Household</p>
        <h1>Access</h1>
        <p>
          Invite people with a one-time <code>/join</code> link. Approving a request creates an invite —
          choose role, Youth mode, and sign-in methods first.
        </p>
      </header>

      {loading ? <p className="status status-secondary">Loading…</p> : null}
      {error ? <p className="error">{error}</p> : null}
      {feedback ? (
        <p className="status status-success" data-testid="access-requests-feedback">
          {feedback}
        </p>
      ) : null}
      {joinLink ? (
        <div className="access-join-link" data-testid="access-join-link">
          <label>
            <span>Join link (copy once)</span>
            <input readOnly value={joinLink} data-testid="access-join-link-input" />
          </label>
          <button type="button" className="primary" data-testid="access-join-link-copy" onClick={copyJoinLink}>
            Copy
          </button>
        </div>
      ) : null}

      <section className="access-create" data-testid="access-create-invite">
        <h2>Create invite</h2>
        <form onSubmit={handleCreateInvite} className="access-create-form">
          <label>
            <span>Role</span>
            <select
              data-testid="invite-create-role"
              value={createRole}
              onChange={(e) => setCreateRole(e.target.value)}
            >
              <option value="member">Member</option>
              <option value="guest">Guest</option>
            </select>
          </label>
          <label className="config-toggle">
            <input
              type="checkbox"
              data-testid="invite-create-youth"
              checked={createYouth}
              onChange={(e) => setCreateYouth(e.target.checked)}
            />
            <span>Youth mode</span>
          </label>
          <label>
            <span>Email (optional — sends link when Mail is configured)</span>
            <input
              type="email"
              data-testid="invite-create-email"
              value={createEmail}
              onChange={(e) => setCreateEmail(e.target.value)}
              placeholder="friend@example.com"
            />
          </label>
          <fieldset className="access-methods">
            <legend>Allowed sign-in methods</legend>
            {DEFAULT_METHODS.map((method) => (
              <label key={method} className="config-toggle">
                <input
                  type="checkbox"
                  data-testid={`invite-create-method-${method}`}
                  checked={createMethods.includes(method)}
                  onChange={(e) =>
                    setCreateMethods(toggleMethod(createMethods, method, e.target.checked))
                  }
                />
                <span>{method}</span>
              </label>
            ))}
          </fieldset>
          <button
            type="submit"
            className="primary"
            data-testid="invite-create-submit"
            disabled={busyId === "create" || createMethods.length === 0}
          >
            {busyId === "create" ? "Creating…" : "Create invite"}
          </button>
        </form>
      </section>

      <section>
        <h2>Pending invites</h2>
        {!loading && !invites.filter((i) => i.status === "pending").length ? (
          <p className="dash-empty" data-testid="invites-empty">
            No pending invites.
          </p>
        ) : null}
        <ul className="access-request-list" data-testid="invite-list">
          {invites
            .filter((i) => i.status === "pending")
            .map((item) => (
              <li key={item.id} className="access-request-row" data-testid={`invite-${item.id}`}>
                <div>
                  <strong>{item.role}</strong>
                  {item.is_youth ? <span className="access-request-email">Youth</span> : null}
                  {item.email ? <span className="access-request-email">{item.email}</span> : null}
                  <p className="status status-secondary">
                    {item.status} · methods: {(item.allowed_methods || []).join(", ")} · expires{" "}
                    {new Date(item.expires_at * 1000).toLocaleString()}
                  </p>
                </div>
                <div className="access-request-actions">
                  <button
                    type="button"
                    className="ghost"
                    disabled={busyId === item.id}
                    data-testid={`invite-revoke-${item.id}`}
                    onClick={() => handleRevoke(item.id)}
                  >
                    Revoke
                  </button>
                </div>
              </li>
            ))}
        </ul>
      </section>

      <section>
        <h2>Access requests</h2>
        {!loading && !items.length ? (
          <p className="dash-empty" data-testid="access-requests-empty">
            No access requests yet.
          </p>
        ) : null}

        <ul className="access-request-list" data-testid="access-request-list">
          {items.map((item) => {
            const opts = optionsFor(item.id);
            return (
              <li key={item.id} className="access-request-row" data-testid={`access-request-${item.id}`}>
                <div>
                  <strong>{item.display_name}</strong>
                  {item.email ? <span className="access-request-email">{item.email}</span> : null}
                  {item.message ? <p className="access-request-message">{item.message}</p> : null}
                  <p className="status status-secondary">
                    {item.status} · {new Date(item.created_at * 1000).toLocaleString()}
                  </p>
                  {item.status === "pending" ? (
                    <div className="access-approve-options">
                      <label>
                        <span>Role</span>
                        <select
                          data-testid={`access-approve-role-${item.id}`}
                          value={opts.role}
                          onChange={(e) => patchOptions(item.id, { role: e.target.value })}
                        >
                          <option value="member">Member</option>
                          <option value="guest">Guest</option>
                        </select>
                      </label>
                      <label className="config-toggle">
                        <input
                          type="checkbox"
                          data-testid={`access-approve-youth-${item.id}`}
                          checked={opts.is_youth}
                          onChange={(e) => patchOptions(item.id, { is_youth: e.target.checked })}
                        />
                        <span>Youth mode</span>
                      </label>
                    </div>
                  ) : null}
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
                      Approve → invite
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
            );
          })}
        </ul>
      </section>
    </div>
  );
}
