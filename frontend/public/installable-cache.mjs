/**
 * What the installable app may store.
 * API, art, and media always stay on the network. A cross-origin URL does too.
 */

const STATIC_EXTENSIONS = [".js", ".css", ".woff2", ".svg", ".ico"];

const MEDIA_EXTENSIONS = [".m3u8", ".mpd", ".m4s", ".ts", ".mp4", ".webm", ".mkv", ".vtt"];

function safePath(rawUrl) {
  let parsed;
  try {
    parsed = new URL(String(rawUrl || ""), "http://household.local");
  } catch {
    return null;
  }
  let path = parsed.pathname || "/";
  try {
    path = decodeURIComponent(path);
  } catch {
    return null;
  }
  if (path.includes("\0")) return null;
  return { parsed, path: path.toLowerCase() };
}

/**
 * @param {string} rawUrl
 * @param {string} [method]
 * @param {string} [pageOrigin] When set, another origin is never cached.
 * @returns {"bypass" | "static"}
 */
export function installableCacheDecision(rawUrl, method = "GET", pageOrigin = "") {
  const verb = String(method || "GET").toUpperCase();
  if (verb !== "GET" && verb !== "HEAD") return "bypass";
  const raw = String(rawUrl || "");
  const relative = raw.startsWith("/") && !raw.startsWith("//");
  const located = safePath(rawUrl);
  if (!located) return "bypass";
  const { parsed, path } = located;
  if (pageOrigin && !relative && parsed.origin !== pageOrigin) return "bypass";
  if (path === "/api" || path.startsWith("/api/")) return "bypass";
  if (path.includes("/art/") || path.endsWith("/art")) return "bypass";
  if (path.startsWith("/playback/") || path.startsWith("/watch")) return "bypass";
  const file = `${path}${parsed.search}`.toLowerCase();
  if (MEDIA_EXTENSIONS.some((ext) => file.includes(ext))) return "bypass";
  if (
    path.startsWith("/assets/")
    || path === "/offline.html"
    || path === "/manifest.webmanifest"
    || path === "/favicon.svg"
    || path === "/icon-192.png"
    || path === "/icon-512.png"
    || STATIC_EXTENSIONS.some((ext) => path.endsWith(ext))
  ) {
    return "static";
  }
  return "bypass";
}
