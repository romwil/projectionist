/** Helpers for the expandable agent activity log under the thinking indicator. */

export const DETAIL_MAX = 160;
export const LOG_MAX_ENTRIES = 80;

/**
 * @param {unknown} value
 * @param {number} [max]
 * @returns {string}
 */
export function truncateText(value, max = DETAIL_MAX) {
  const text = String(value ?? "").trim();
  if (!text) return "";
  if (text.length <= max) return text;
  return `${text.slice(0, Math.max(0, max - 3))}...`;
}

/**
 * Brief, human-readable tool args for the activity panel.
 * @param {unknown} args
 * @returns {string}
 */
export function formatToolArgs(args) {
  if (args == null || args === "") return "";
  if (typeof args === "string") return truncateText(args);
  if (typeof args !== "object") return truncateText(args);

  try {
    if (!Array.isArray(args)) {
      const entries = Object.entries(args).filter(([, v]) => v != null && v !== "");
      if (entries.length === 0) return "";
      if (entries.length <= 4) {
        return truncateText(
          entries
            .map(([key, value]) => {
              const rendered = typeof value === "string" ? value : JSON.stringify(value);
              return `${key}=${rendered}`;
            })
            .join(", "),
        );
      }
    }
    return truncateText(JSON.stringify(args));
  } catch {
    return truncateText(String(args));
  }
}

/**
 * @param {unknown} result
 * @returns {string}
 */
export function summarizeToolResult(result) {
  if (result == null || result === "") return "";
  if (typeof result === "string") return truncateText(result);
  try {
    return truncateText(JSON.stringify(result));
  } catch {
    return truncateText(String(result));
  }
}

/**
 * @param {{ kind: string, label: string, detail?: string, t?: number }} event
 */
export function createActivityEvent({ kind, label, detail, t = Date.now() }) {
  const entry = { t, kind, label: String(label || "").trim() || "…" };
  const trimmedDetail = detail ? truncateText(detail) : "";
  if (trimmedDetail) entry.detail = trimmedDetail;
  return entry;
}

/**
 * @param {{ name?: string, status?: string, args?: unknown, summary?: unknown }} payload
 */
export function activityEventFromToolCall({ name, status, args, summary } = {}) {
  const toolName = String(name || "tool").replace(/_/g, " ");
  if (status === "start") {
    return createActivityEvent({
      kind: "tool_start",
      label: toolName,
      detail: formatToolArgs(args),
    });
  }
  return createActivityEvent({
    kind: "tool_result",
    label: `${toolName} · done`,
    detail: summarizeToolResult(summary),
  });
}

/**
 * @param {Array<object>} log
 * @param {object|null|undefined} event
 * @param {{ maxEntries?: number }} [options]
 */
export function appendActivityLog(log, event, { maxEntries = LOG_MAX_ENTRIES } = {}) {
  if (!event) return Array.isArray(log) ? log : [];
  const next = [...(Array.isArray(log) ? log : []), event];
  if (next.length > maxEntries) return next.slice(-maxEntries);
  return next;
}

/**
 * Activity panel should collapse when the stream finishes.
 * @param {{ streamDone?: boolean, expanded?: boolean }} state
 * @returns {boolean} next expanded value
 */
export function nextActivityPanelExpanded({ streamDone = false, expanded = false } = {}) {
  if (streamDone) return false;
  return Boolean(expanded);
}
