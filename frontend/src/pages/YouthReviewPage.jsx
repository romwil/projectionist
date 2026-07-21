import { useCallback, useEffect, useState } from "react";
import { getUserMemory, listUsers } from "../api/client";

/**
 * Owner Youth moderation dashboard. Reviews the private memory notes CuratorX
 * keeps for a Youth-flagged account. The server (`GET /api/users/{id}/memory`)
 * is fail-closed: it only returns notes for accounts explicitly in Youth mode,
 * so non-youth accounts cannot be reviewed here by design.
 */
export default function YouthReviewPage() {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState(null);
  const [notes, setNotes] = useState([]);
  const [notesLoading, setNotesLoading] = useState(false);
  const [notesError, setNotesError] = useState("");

  useEffect(() => {
    let cancelled = false;
    listUsers()
      .then((data) => {
        if (cancelled) return;
        const all = data?.items || data || [];
        setUsers(all.filter((u) => u.is_youth));
        setError("");
      })
      .catch((err) => !cancelled && setError(err.message || "Could not load accounts."))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, []);

  const loadNotes = useCallback(async (user) => {
    setSelected(user);
    setNotesLoading(true);
    setNotesError("");
    setNotes([]);
    try {
      const data = await getUserMemory(user.id);
      setNotes(data?.notes || []);
    } catch (err) {
      setNotesError(err.message || "Could not load memory for this account.");
    } finally {
      setNotesLoading(false);
    }
  }, []);

  return (
    <div className="dash-page" data-testid="youth-review-page">
      <header className="dash-header">
        <div>
          <p className="eyebrow">Owner tools</p>
          <h2 className="dash-title">Youth moderation</h2>
        </div>
      </header>

      <p className="youth-review-guard" data-testid="youth-review-guard">
        Review is limited to accounts flagged as <strong>Youth</strong>. CuratorX keeps
        younger members&rsquo; long-term memory fail-closed — you can read what the curator
        remembers for a Youth account here, but adult members&rsquo; private memory is never
        exposed. Set an account to Youth mode from <strong>Household</strong>.
      </p>

      {loading ? (
        <p className="status status-secondary">Loading accounts…</p>
      ) : error ? (
        <p className="dash-panel-error">{error}</p>
      ) : !users.length ? (
        <p className="dash-empty" data-testid="youth-review-empty">
          No Youth-flagged accounts yet. Flag an account as Youth in Household to review its memory here.
        </p>
      ) : (
        <div className="youth-review">
          <nav aria-label="Youth accounts">
            {users.map((user) => (
              <button
                key={user.id}
                type="button"
                className={`youth-review-user ${selected?.id === user.id ? "is-active" : ""}`}
                data-testid={`youth-review-user-${user.id}`}
                onClick={() => loadNotes(user)}
              >
                <strong>{user.display_name || user.preferred_name || user.id}</strong>
              </button>
            ))}
          </nav>
          <section data-testid="youth-review-notes">
            {!selected ? (
              <p className="status status-secondary">Select a Youth account to review its memory.</p>
            ) : notesLoading ? (
              <p className="status status-secondary">Loading memory…</p>
            ) : notesError ? (
              <p className="dash-panel-error">{notesError}</p>
            ) : !notes.length ? (
              <p className="dash-empty">
                No memory notes recorded for {selected.display_name || "this account"} yet.
              </p>
            ) : (
              notes.map((note) => (
                <article key={note.id} className="youth-review-note">
                  <p className="youth-review-note-kind">{note.kind || "note"}</p>
                  <p>{note.text}</p>
                </article>
              ))
            )}
          </section>
        </div>
      )}
    </div>
  );
}
