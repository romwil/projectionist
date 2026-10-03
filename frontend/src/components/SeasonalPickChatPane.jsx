import { useEffect, useRef, useState } from "react";

import { sendChatStream } from "../api/client";
import { seasonalPickChatSeed } from "../lib/seasonalShelves";

function newSessionId() {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID().replace(/-/g, "");
  }
  return `season_${Date.now().toString(16)}_${Math.random().toString(16).slice(2)}`;
}

/**
 * Docked conversation about one seasonal pick (Explore / Live owner tools).
 * Streams via sendChatStream; does not navigate away from the current page.
 */
export default function SeasonalPickChatPane({
  seasonLabel,
  scopeId = "",
  title,
  onClose,
  testId = "seasonal-pick-chat",
}) {
  const [sessionId] = useState(() => newSessionId());
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState("");
  const abortRef = useRef(null);
  const seededRef = useRef(false);
  const bottomRef = useRef(null);

  const titleKey = title?.id ?? title?.rating_key ?? title?.title;
  const titleLabel = title
    ? `${title.title || "Title"}${title.year ? ` (${title.year})` : ""}`
    : "";

  useEffect(() => {
    bottomRef.current?.scrollIntoView?.({ block: "end" });
  }, [messages, streaming]);

  useEffect(() => {
    return () => {
      abortRef.current?.abort?.();
    };
  }, []);

  useEffect(() => {
    if (!title || seededRef.current) return;
    seededRef.current = true;
    const seed = seasonalPickChatSeed({
      seasonLabel,
      scopeId,
      title: title.title,
      year: title.year,
      curatorNote: title.curator_note || title.why,
      railRole: title.rail_role,
    });
    void runTurn(seed, { asUserVisible: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- seed once per open title
  }, [titleKey, seasonLabel, scopeId]);

  async function runTurn(text, { asUserVisible = true } = {}) {
    const trimmed = String(text || "").trim();
    if (!trimmed || streaming) return;
    setError("");
    if (asUserVisible) {
      setMessages((prev) => [...prev, { role: "user", content: trimmed }]);
    }
    setMessages((prev) => [...prev, { role: "assistant", content: "" }]);
    setStreaming(true);
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      await sendChatStream(trimmed, {
        sessionId,
        signal: controller.signal,
        onToken: ({ token } = {}) => {
          const chunk = String(token || "");
          if (!chunk) return;
          setMessages((prev) => {
            const next = [...prev];
            const last = next[next.length - 1];
            if (!last || last.role !== "assistant") {
              next.push({ role: "assistant", content: chunk });
              return next;
            }
            next[next.length - 1] = { ...last, content: `${last.content}${chunk}` };
            return next;
          });
        },
        onDone: ({ reply } = {}) => {
          const finalText = String(reply || "").trim();
          if (!finalText) return;
          setMessages((prev) => {
            const next = [...prev];
            const last = next[next.length - 1];
            if (last?.role === "assistant" && !String(last.content || "").trim()) {
              next[next.length - 1] = { ...last, content: finalText };
            }
            return next;
          });
        },
        onError: ({ error: err } = {}) => {
          setError(String(err || "Chat failed."));
        },
      });
    } catch (err) {
      if (err?.name !== "AbortError") {
        setError(err?.message || "Chat failed.");
      }
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }
  }

  return (
    <aside
      className="seasonal-pick-chat"
      data-testid={testId}
      aria-label={`Chat about ${titleLabel || "this title"}`}
    >
      <header className="seasonal-pick-chat-head">
        <div>
          <p className="seasonal-pick-chat-kicker">Chat about this</p>
          <h4 className="seasonal-pick-chat-title">{titleLabel || "Seasonal pick"}</h4>
          {seasonLabel ? (
            <p className="seasonal-pick-chat-season">{seasonLabel}</p>
          ) : null}
        </div>
        <button
          type="button"
          className="ghost"
          data-testid={`${testId}-close`}
          onClick={onClose}
        >
          Close
        </button>
      </header>
      <div className="seasonal-pick-chat-messages" data-testid={`${testId}-messages`}>
        {messages.map((message, index) => (
          <div
            key={`${message.role}-${index}`}
            className={`seasonal-pick-chat-bubble seasonal-pick-chat-bubble--${message.role}`}
          >
            {message.content || (message.role === "assistant" && streaming ? "…" : "")}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
      {error ? (
        <p className="status status-error" role="alert">
          {error}
        </p>
      ) : null}
      <form
        className="seasonal-pick-chat-composer"
        onSubmit={(event) => {
          event.preventDefault();
          const next = draft.trim();
          if (!next) return;
          setDraft("");
          void runTurn(next);
        }}
      >
        <label>
          <span className="sr-only">Message</span>
          <textarea
            value={draft}
            rows={2}
            placeholder="Ask about this pick…"
            data-testid={`${testId}-input`}
            disabled={streaming}
            onChange={(event) => setDraft(event.target.value)}
          />
        </label>
        <button
          type="submit"
          className="primary"
          disabled={streaming || !draft.trim()}
          data-testid={`${testId}-send`}
        >
          Send
        </button>
      </form>
    </aside>
  );
}
