import { useCallback, useEffect, useRef, useState } from "react";
import { Navigate } from "react-router-dom";
import {
  bindNotificationThread,
  createThread,
  getPersonas,
  getThreadMessages,
  listNotifications,
  markNotificationsRead,
  markNotificationsSeen,
  sendChatStream,
} from "../api/client";
import ChamberEmpty from "../components/ChamberEmpty";
import InboxNote from "../components/InboxNote";
import { useAuthGate } from "../components/UserMenu";
import AppShell from "../layouts/AppShell";
import { ROUTES } from "../lib/backNav.js";
import {
  applyInboxDismiss,
  applyInboxRead,
  defaultInboxPersona,
  inboxAgentOutboundMessage,
  inboxFullMessage,
  inboxKindLabel,
  inboxListParams,
  inboxPageSelection,
  inboxReplyText,
  inboxScanPreview,
  isAgentInboxNote,
} from "../lib/inboxMailbox.js";
import { guestDeepLinkBlocked } from "../lib/memberShell.js";

/**
 * Mailbox. The shell paints immediately; one modest page loads with auth,
 * not before it and not as a full unread scan.
 */
export default function InboxPage() {
  const { authReady, role, multiUserEnabled } = useAuthGate();
  const [query, setQuery] = useState<any>({ status: "all", sort: "newest", kind: "", page: 0 });
  const [state, setState] = useState<any>({
    loading: true,
    items: [] as any[],
    error: "",
    unread: 0,
    total: 0,
    kinds: [] as any[],
  });
  const [openId, setOpenId] = useState<any | null>(null);
  const [selected, setSelected] = useState<Set<string>>(() => new Set());
  const [persona, setPersona] = useState<any | null>(null);
  const [replies, setReplies] = useState<any[]>([]);
  const [streaming, setStreaming] = useState("");
  const [replyError, setReplyError] = useState("");
  const loadGen = useRef(0);
  const localReplyId = useRef(0);

  const loadInbox = useCallback((nextQuery: any) => {
    const gen = ++loadGen.current;
    listNotifications(inboxListParams(nextQuery))
      .then((data) => {
        if (gen !== loadGen.current) return;
        setState({
          loading: false,
          items: data.items || [],
          error: "",
          unread: Number(data.unread_count) || 0,
          total: Number(data.total) || 0,
          kinds: data.kinds || [],
        });
        setSelected(new Set());
      })
      .catch((err) => {
        if (gen !== loadGen.current) return;
        if (err?.status === 401) {
          setState((prev: any) => ({ ...prev, loading: false, error: "" }));
          return;
        }
        setState((prev: any) => ({
          ...prev,
          loading: false,
          error: (err as { message?: string }).message || "Could not load inbox.",
        }));
      });
  }, []);

  useEffect(() => {
    loadInbox(query);
  }, [loadInbox, query]);

  const openItem = state.items.find((item: any) => item.id === openId) || null;
  const agentOpen = Boolean(openItem && isAgentInboxNote(openItem));

  useEffect(() => {
    if (!agentOpen || persona) return undefined;
    let cancelled = false;
    getPersonas()
      .then((data) => {
        if (cancelled) return;
        const picked = defaultInboxPersona(data);
        if (picked) setPersona(picked);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [agentOpen, persona]);

  function updateQuery(patch: any) {
    setOpenId(null);
    setQuery((prev: any) => ({ ...prev, page: 0, ...patch }));
  }

  async function openNote(item: any) {
    setOpenId(item.id);
    setReplies([]);
    setStreaming("");
    setReplyError("");
    const sessionId = item.payload?.chat_session_id;
    if (sessionId && isAgentInboxNote(item)) {
      getThreadMessages(sessionId)
        .then((data) => {
          const stored = (data?.messages || [])
            .map((message: any) => ({
              id: message.id,
              role: message.role,
              text: inboxReplyText(message),
            }))
            .filter((message: any) => message.text);
          setReplies(stored);
        })
        .catch(() => {});
    }
    if (!item.read_at) {
      setState((prev: any) => ({
        ...prev,
        items: applyInboxRead(prev.items, item.id, item.created_at || 1),
        unread: Math.max(0, prev.unread - 1),
      }));
      try {
        await markNotificationsRead({ ids: [item.id] });
      } catch {
        loadInbox(query);
      }
    }
  }

  function dismissIds(ids: any) {
    const drop = ids.filter(Boolean);
    if (!drop.length) return;
    setState((prev: any) => ({
      ...prev,
      items: applyInboxDismiss(prev.items, drop),
      unread: Math.max(0, prev.unread - drop.length),
    }));
    setSelected((prev) => {
      const next = new Set(prev);
      drop.forEach((id: any) => next.delete(id));
      return next;
    });
    if (drop.includes(openId)) setOpenId(null);
    markNotificationsSeen({ ids: drop }).catch(() => loadInbox(query));
  }

  function dismissAll() {
    setState((prev: any) => ({
      ...prev,
      items: prev.items.filter((item: any) => item.read_at),
      unread: 0,
    }));
    setOpenId(null);
    markNotificationsSeen({ all_unread: true }).catch(() => loadInbox(query));
  }

  async function submitReply(text: any) {
    if (!openItem) return;
    setReplyError("");
    try {
      let sessionId = openItem.payload?.chat_session_id || "";
      const first = !sessionId;
      if (!sessionId) {
        const created = await createThread({
          thread_title: openItem.title || "Inbox note",
          persona_id: persona?.id,
        });
        sessionId = created.session_id;
        await bindNotificationThread(openItem.id, sessionId);
        setState((prev: any) => ({
          ...prev,
          items: prev.items.map((item: any) =>
            item.id === openItem.id
              ? { ...item, payload: { ...(item.payload || {}), chat_session_id: sessionId } }
              : item,
          ),
        }));
      }
      const outbound = inboxAgentOutboundMessage(inboxFullMessage(openItem).body, text, { first });
      localReplyId.current += 1;
      const userReplyId = `local-user-${localReplyId.current}`;
      setReplies((prev) => [...prev, { id: userReplyId, role: "user", text }]);
      let assistant = "";
      await sendChatStream(outbound, {
        sessionId,
        personaId: persona?.id,
        onToken: (token: any) => {
          assistant += token?.content || "";
          setStreaming(assistant);
        },
        onDone: () => {
          const textOut = assistant.trim();
          if (textOut) {
            setReplies((prev) => [
              ...prev,
              { id: `local-agent-${userReplyId}`, role: "assistant", text: textOut },
            ]);
          }
          setStreaming("");
        },
        onError: (err: any) => {
          setReplyError(err?.error || "Could not send that reply.");
          setStreaming("");
        },
      });
    } catch (err: any) {
      setReplyError(err?.message || "Could not send that reply.");
      throw err;
    }
  }

  if (authReady && guestDeepLinkBlocked({ role, multiUserEnabled, authReady: true })) {
    return <Navigate to={ROUTES.explore} replace />;
  }

  const selection = inboxPageSelection(state.items, selected);
  const pageCount = Math.max(1, Math.ceil((state.total || 0) / inboxListParams().limit));
  const showKindFilter = state.kinds.length > 1;

  return (
    <AppShell
      className="app-root inbox-page"
      testId="inbox-page"
      title="Inbox"
      inboxUnreadCount={state.unread}
      blockUntilAuth={false}
    >
      <main className="explore-main inbox-main">
        <header className="inbox-toolbar">
          <h2>Inbox</h2>
          <div className="inbox-toolbar-controls">
            <label className="inbox-field">
              <span>Show</span>
              <select
                data-testid="inbox-status"
                value={query.status}
                onChange={(event) => updateQuery({ status: event.target.value })}
              >
                <option value="all">All</option>
                <option value="unread">Unread</option>
                <option value="read">Read</option>
              </select>
            </label>
            <label className="inbox-field">
              <span>Sort</span>
              <select
                data-testid="inbox-sort"
                value={query.sort}
                onChange={(event) => updateQuery({ sort: event.target.value })}
              >
                <option value="newest">Newest</option>
                <option value="oldest">Oldest</option>
              </select>
            </label>
            {showKindFilter ? (
              <label className="inbox-field">
                <span>Type</span>
                <select
                  data-testid="inbox-kind"
                  value={query.kind}
                  onChange={(event) => updateQuery({ kind: event.target.value })}
                >
                  <option value="">All types</option>
                  {state.kinds.map((kind: any) => (
                    <option key={kind} value={kind}>
                      {inboxKindLabel(kind)}
                    </option>
                  ))}
                </select>
              </label>
            ) : null}
          </div>
        </header>

        {state.loading && !state.items.length ? (
          <p className="status status-secondary">Loading inbox…</p>
        ) : null}
        {state.error ? <p className="status status-error">{state.error}</p> : null}

        {openItem ? (
          <InboxNote
            item={openItem}
            personaName={persona?.name || "your curator"}
            replies={replies}
            streaming={streaming}
            replyError={replyError}
            onSubmit={submitReply}
            onBack={() => setOpenId(null)}
            onDismiss={(item) => dismissIds([(item as any).id])}
          />
        ) : null}

        {!openItem && !state.loading && !state.error && !state.items.length ? (
          <section className="explore-section" data-testid="inbox-empty">
            <ChamberEmpty
              title="Nothing waiting"
              body="When someone recommends a title or a request lands, it shows up here."
              ctaLabel="Back to Explore"
              ctaTo={ROUTES.explore}
              testId="inbox-empty-state"
            />
          </section>
        ) : null}

        {!openItem && state.items.length ? (
          <section className="inbox-list" aria-label="Inbox messages" data-testid="inbox-list">
            <div className="inbox-list-actions">
              <label className="inbox-select-all inbox-hit">
                <input
                  type="checkbox"
                  data-testid="inbox-select-all"
                  checked={selection.all}
                  onChange={(event) => {
                    setSelected(event.target.checked ? new Set(selection.ids) : new Set());
                  }}
                />
                Select all
              </label>
              {selected.size ? (
                <button
                  type="button"
                  className="ghost inbox-hit"
                  data-testid="inbox-dismiss-selected"
                  onClick={() => dismissIds([...selected])}
                >
                  Dismiss selected
                </button>
              ) : null}
              {state.unread ? (
                <button type="button" className="ghost inbox-hit" data-testid="inbox-dismiss-all" onClick={dismissAll}>
                  Dismiss all
                </button>
              ) : null}
            </div>
            <ul className="inbox-rows">
              {state.items.map((item: any) => {
                const preview = inboxScanPreview(inboxFullMessage(item).body);
                return (
                  <li key={item.id} className={item.read_at ? "inbox-row is-read" : "inbox-row"} data-testid={`inbox-row-${item.id}`}>
                    <label className="inbox-hit inbox-row-check">
                      <input
                        type="checkbox"
                        aria-label={`Select ${item.title || "note"}`}
                        checked={selected.has(item.id)}
                        onChange={(event) => {
                          setSelected((prev) => {
                            const next = new Set(prev);
                            if (event.target.checked) next.add(item.id);
                            else next.delete(item.id);
                            return next;
                          });
                        }}
                      />
                    </label>
                    <button type="button" className="inbox-row-open" onClick={() => openNote(item)}>
                      <span className="inbox-row-title">{item.title || "Note"}</span>
                      {preview.text ? (
                        <span className="inbox-row-preview">
                          {preview.text}
                          {preview.continues ? " Read the rest." : ""}
                        </span>
                      ) : null}
                    </button>
                    <button type="button" className="ghost inbox-hit" onClick={() => openNote(item)}>
                      Read
                    </button>
                    <button type="button" className="ghost inbox-hit" onClick={() => dismissIds([item.id])}>
                      Dismiss
                    </button>
                  </li>
                );
              })}
            </ul>
            <nav className="inbox-pager" aria-label="Inbox pages">
              <button
                type="button"
                className="ghost inbox-hit"
                data-testid="inbox-page-prev"
                disabled={query.page <= 0}
                onClick={() => setQuery((prev: any) => ({ ...prev, page: Math.max(0, prev.page - 1) }))}
              >
                Previous
              </button>
              <span>
                Page {query.page + 1} of {pageCount}
              </span>
              <button
                type="button"
                className="ghost inbox-hit"
                data-testid="inbox-page-next"
                disabled={query.page + 1 >= pageCount}
                onClick={() => setQuery((prev: any) => ({ ...prev, page: prev.page + 1 }))}
              >
                Next
              </button>
            </nav>
          </section>
        ) : null}
      </main>
    </AppShell>
  );
}
