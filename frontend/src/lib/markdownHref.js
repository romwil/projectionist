/**
 * Assistant markdown href allowlist (P3-HIGH-03).
 *
 * Allowed: http(s), in-app /title and /library paths, and hash fragments.
 * Other schemes (javascript:, data:, vbscript:, mailto:, …) are not links —
 * MessageText renders those as text.
 */

export function markdownLinkKind(href) {
  const raw = String(href ?? "").trim();
  if (!raw) return "text";
  if (raw.startsWith("#")) return "hash";
  if (/^https?:\/\//i.test(raw)) return "http";
  const path = raw.split(/[?#]/, 1)[0];
  if (path === "/title" || path.startsWith("/title/")) return "title";
  if (path === "/library" || path.startsWith("/library/")) return "library";
  return "text";
}

export function isAllowedMarkdownHref(href) {
  return markdownLinkKind(href) !== "text";
}
