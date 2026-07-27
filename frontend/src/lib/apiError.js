/** User-facing messages for failed API responses (never dump HTML/gateway pages). */

const HTML_BODY_RE = /^\s*<(!DOCTYPE|html|head|body|title|div|style|script)\b/i;
const LOOKS_LIKE_MARKUP_RE = /<\/?[a-z][\s\S]*>/i;

const STATUS_MESSAGES = {
  400: "That request was invalid. Try again.",
  401: "Sign-in required. Please try again.",
  403: "You don’t have permission to do that.",
  404: "That resource was not found.",
  408: "The request timed out. Try again.",
  429: "Too many attempts. Wait a moment and try again.",
  500: "The server hit an internal error. Try again in a moment.",
  502: "The server is temporarily unavailable. Try again in a moment.",
  503: "The server is temporarily unavailable. Try again in a moment.",
  504: "The server took too long to respond. Try again in a moment.",
};

function messageForStatus(status, statusText) {
  const code = Number(status) || 0;
  if (STATUS_MESSAGES[code]) return STATUS_MESSAGES[code];
  if (code >= 500) {
    return "The server is temporarily unavailable. Try again in a moment.";
  }
  if (code >= 400) {
    const hint = String(statusText || "").trim();
    return hint ? `Request failed (${code} ${hint}).` : `Request failed (${code}).`;
  }
  return String(statusText || "").trim() || "Request failed";
}

export function looksLikeHtmlOrMarkup(text) {
  const trimmed = String(text || "").trim();
  if (!trimmed) return false;
  if (HTML_BODY_RE.test(trimmed)) return true;
  // Cloudflare / nginx error pages and other gateway HTML dumps
  if (trimmed.length > 280 && LOOKS_LIKE_MARKUP_RE.test(trimmed)) return true;
  if (/cloudflare|bad gateway|error code|cf-error/i.test(trimmed) && LOOKS_LIKE_MARKUP_RE.test(trimmed)) {
    return true;
  }
  return false;
}

/**
 * Parse an HTTP error body into a short user-facing string.
 * @param {string} text
 * @param {string} [statusText]
 * @param {number} [status]
 */
export function parseApiErrorBody(text, statusText, status) {
  const fallback = messageForStatus(status, statusText);
  if (!text) return fallback;

  try {
    const data = JSON.parse(text);
    if (typeof data.detail === "string" && data.detail.trim()) return data.detail.trim();
    if (Array.isArray(data.detail)) {
      const joined = data.detail
        .map((entry) => entry?.msg || entry?.message || String(entry))
        .filter(Boolean)
        .join("; ");
      if (joined) return joined;
    }
    if (data.error) return String(data.error);
    if (data.message) return String(data.message);
  } catch {
    // Plain-text or HTML error body
  }

  const trimmed = String(text).trim();
  if (looksLikeHtmlOrMarkup(trimmed)) {
    return fallback;
  }
  // Cap runaway plain-text bodies (proxies sometimes return long dumps)
  if (trimmed.length > 280) {
    return fallback;
  }
  return trimmed || fallback;
}

export function formatApiError(error) {
  if (!error) return "Request failed";
  if (error.name === "AbortError") {
    return "Request timed out. Check your LLM provider or try again.";
  }
  return error.message || "Request failed";
}
