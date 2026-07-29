import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getAdminLogs } from "../api/client";

const LEVELS = [
  { value: "", label: "All levels" },
  { value: "DEBUG", label: "DEBUG+" },
  { value: "INFO", label: "INFO+" },
  { value: "WARNING", label: "WARNING+" },
  { value: "ERROR", label: "ERROR+" },
];

const MAX_VISIBLE = 800;
const NEAR_BOTTOM_PX = 80;

function levelClass(level) {
  const normalized = String(level || "").toUpperCase();
  if (normalized === "ERROR" || normalized === "CRITICAL") return "log-level-error";
  if (normalized === "WARNING") return "log-level-warning";
  if (normalized === "DEBUG") return "log-level-debug";
  return "log-level-info";
}

function buildStreamUrl({ afterOffset, level, loggerName, q }) {
  const params = new URLSearchParams();
  if (afterOffset != null) params.set("after_offset", String(afterOffset));
  if (level) params.set("level", level);
  if (loggerName) params.set("logger", loggerName);
  if (q) params.set("q", q);
  const qs = params.toString();
  return `/api/admin/logs/stream${qs ? `?${qs}` : ""}`;
}

export default function LogsPage() {
  const [lines, setLines] = useState([]);
  const [loggers, setLoggers] = useState([]);
  const [path, setPath] = useState("");
  const [warning, setWarning] = useState("");
  const [level, setLevel] = useState("INFO");
  const [loggerName, setLoggerName] = useState("");
  const [loggerDraft, setLoggerDraft] = useState("");
  const [q, setQ] = useState("");
  const [qDraft, setQDraft] = useState("");
  const [follow, setFollow] = useState(true);
  const [streaming, setStreaming] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [nextOffset, setNextOffset] = useState(0);

  const scrollerRef = useRef(null);
  const followRef = useRef(true);
  const nextOffsetRef = useRef(0);
  const seenIdsRef = useRef(new Set());

  useEffect(() => {
    followRef.current = follow;
  }, [follow]);

  const mergeLines = useCallback((incoming) => {
    if (!incoming?.length) return;
    setLines((prev) => {
      const seen = seenIdsRef.current;
      const merged = [...prev];
      for (const line of incoming) {
        const id = line.id ?? `${line.timestamp}|${line.raw}`;
        if (seen.has(id)) continue;
        seen.add(id);
        merged.push(line);
      }
      if (merged.length > MAX_VISIBLE) {
        const dropped = merged.splice(0, merged.length - MAX_VISIBLE);
        for (const row of dropped) {
          seen.delete(row.id ?? `${row.timestamp}|${row.raw}`);
        }
      }
      return merged;
    });
  }, []);

  const scrollToBottom = useCallback(() => {
    const el = scrollerRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, []);

  const loadSnapshot = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await getAdminLogs({
        limit: 400,
        level: level || undefined,
        logger: loggerName.trim() || undefined,
        q: q || undefined,
      });
      seenIdsRef.current = new Set();
      const items = data.lines || [];
      for (const line of items) {
        seenIdsRef.current.add(line.id ?? `${line.timestamp}|${line.raw}`);
      }
      setLines(items);
      setLoggers(data.loggers || []);
      setPath(data.path || "");
      setWarning(data.sensitive_warning || "");
      const offset = typeof data.next_offset === "number" ? data.next_offset : 0;
      setNextOffset(offset);
      nextOffsetRef.current = offset;
      if (!data.exists) {
        setError("Log file not created yet — it appears after the app writes its first line.");
      }
    } catch (err) {
      setError(err.message || "Could not load logs.");
      setLines([]);
    } finally {
      setLoading(false);
    }
  }, [level, loggerName, q]);

  useEffect(() => {
    loadSnapshot();
  }, [loadSnapshot]);

  useEffect(() => {
    if (loading) return undefined;
    const url = buildStreamUrl({
      afterOffset: nextOffsetRef.current,
      level,
      loggerName: loggerName.trim(),
      q,
    });
    let closed = false;
    let source;
    try {
      source = new EventSource(url, { withCredentials: true });
    } catch (err) {
      setError(err.message || "Could not open log stream.");
      return undefined;
    }
    setStreaming(true);

    source.addEventListener("ready", (event) => {
      try {
        const payload = JSON.parse(event.data || "{}");
        if (payload.path) setPath(payload.path);
        if (payload.sensitive_warning) setWarning(payload.sensitive_warning);
        if (typeof payload.next_offset === "number") {
          nextOffsetRef.current = payload.next_offset;
          setNextOffset(payload.next_offset);
        }
      } catch {
        /* ignore malformed ready */
      }
    });

    source.addEventListener("log", (event) => {
      try {
        const line = JSON.parse(event.data || "{}");
        mergeLines([line]);
        if (typeof line.id === "number") {
          const end = line.id + ((line.raw || "").length + 1);
          if (end > nextOffsetRef.current) {
            nextOffsetRef.current = end;
            setNextOffset(end);
          }
        }
      } catch {
        /* ignore malformed line */
      }
    });

    source.addEventListener("error", (event) => {
      if (event?.data) {
        try {
          const payload = JSON.parse(event.data);
          if (payload.error) setError(payload.error);
        } catch {
          /* browser connection error — EventSource will retry */
        }
      }
    });

    source.onerror = () => {
      if (closed) return;
      setStreaming(false);
    };
    source.onopen = () => {
      if (!closed) setStreaming(true);
    };

    return () => {
      closed = true;
      setStreaming(false);
      source.close();
    };
  }, [loading, level, loggerName, q, mergeLines]);

  useEffect(() => {
    if (!follow) return;
    scrollToBottom();
  }, [lines, follow, scrollToBottom]);

  function handleScroll() {
    const el = scrollerRef.current;
    if (!el) return;
    const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
    const nearBottom = distance <= NEAR_BOTTOM_PX;
    if (!nearBottom && followRef.current) {
      setFollow(false);
    } else if (nearBottom && !followRef.current) {
      setFollow(true);
    }
  }

  function applySearch(event) {
    event.preventDefault();
    setQ(qDraft.trim());
  }

  const loggerOptions = useMemo(() => {
    const set = new Set(loggers);
    if (loggerName) set.add(loggerName);
    return Array.from(set);
  }, [loggers, loggerName]);

  return (
    <div className="logs-page" data-testid="logs-page">
      <header className="dash-header">
        <div>
          <p className="eyebrow">Owner tools</p>
          <h2 className="dash-title">Application logs</h2>
          <p className="dash-subtitle">
            Live tail of the durable app log. Filter by level or logger; auto-scroll pauses when you
            scroll up.
          </p>
        </div>
        <div className="logs-header-actions">
          <button
            type="button"
            className="ghost"
            data-testid="logs-refresh"
            onClick={() => loadSnapshot()}
          >
            Refresh
          </button>
          <button
            type="button"
            className={follow ? "primary" : "ghost"}
            data-testid="logs-follow-toggle"
            aria-pressed={follow}
            onClick={() => {
              const next = !follow;
              setFollow(next);
              if (next) scrollToBottom();
            }}
          >
            {follow ? "Following" : "Follow"}
          </button>
        </div>
      </header>

      {warning ? (
        <p className="logs-sensitive-warning" data-testid="logs-sensitive-warning" role="note">
          {warning}
        </p>
      ) : null}

      <div className="logs-toolbar" data-testid="logs-toolbar">
        <label className="logs-filter">
          <span>Level</span>
          <select
            value={level}
            onChange={(event) => setLevel(event.target.value)}
            data-testid="logs-level-filter"
          >
            {LEVELS.map((option) => (
              <option key={option.value || "all"} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <form
          className="logs-filter logs-filter-search"
          onSubmit={(event) => {
            event.preventDefault();
            setLoggerName(loggerDraft.trim());
          }}
        >
          <span>Logger</span>
          <input
            list="logs-logger-options"
            value={loggerDraft}
            onChange={(event) => setLoggerDraft(event.target.value)}
            onBlur={() => setLoggerName(loggerDraft.trim())}
            placeholder="e.g. projectionist.web"
            data-testid="logs-logger-filter"
          />
          <datalist id="logs-logger-options">
            {loggerOptions.map((name) => (
              <option key={name} value={name} />
            ))}
          </datalist>
          <button type="submit" className="ghost" data-testid="logs-logger-apply">
            Apply
          </button>
        </form>
        <form className="logs-filter logs-filter-search" onSubmit={applySearch}>
          <span>Contains</span>
          <input
            value={qDraft}
            onChange={(event) => setQDraft(event.target.value)}
            placeholder="Search message text"
            data-testid="logs-q-filter"
          />
          <button type="submit" className="ghost" data-testid="logs-q-apply">
            Apply
          </button>
        </form>
        <p className="logs-meta" data-testid="logs-meta">
          <span className={streaming ? "logs-live-dot logs-live-dot-on" : "logs-live-dot"} />
          {streaming ? "Live" : "Idle"}
          {path ? (
            <>
              {" · "}
              <code title="On Unraid this is usually under your appdata bind mount as logs/projectionist.log">
                {path}
              </code>
            </>
          ) : null}
          {nextOffset ? ` · offset ${nextOffset}` : null}
        </p>
      </div>

      {error ? (
        <p className="dash-panel-error" data-testid="logs-error">
          {error}
        </p>
      ) : null}

      <section className="logs-panel" aria-label="Log lines">
        {loading && !lines.length ? (
          <p className="status status-secondary">Loading logs…</p>
        ) : (
          <div
            className="logs-scroller"
            ref={scrollerRef}
            onScroll={handleScroll}
            data-testid="logs-scroller"
          >
            {lines.length === 0 ? (
              <p className="dash-empty" data-testid="logs-empty">
                No lines match the current filters.
              </p>
            ) : (
              <ol className="logs-list">
                {lines.map((line) => (
                  <li
                    key={line.id ?? `${line.timestamp}|${line.raw}`}
                    className={`logs-line ${levelClass(line.level)}`}
                    data-testid="logs-line"
                    data-level={line.level}
                  >
                    <span className="logs-line-time">{line.timestamp || "—"}</span>
                    <span className="logs-line-level">{line.level || "INFO"}</span>
                    <span className="logs-line-logger" title={line.logger}>
                      {line.logger || "—"}
                    </span>
                    <span className="logs-line-message">{line.message || line.raw}</span>
                  </li>
                ))}
              </ol>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
