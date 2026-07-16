/** Resolve avatar_url for <img src>, adding a cache-buster when needed. */
export function resolveAvatarSrc(avatarUrl, bust) {
  const raw = String(avatarUrl || "").trim();
  if (!raw) return "";
  if (raw.startsWith("http://") || raw.startsWith("https://") || raw.startsWith("data:")) {
    return bust ? `${raw}${raw.includes("?") ? "&" : "?"}v=${encodeURIComponent(bust)}` : raw;
  }
  // Local API paths like /api/auth/avatar/{id}
  const path = raw.startsWith("/") ? raw : `/${raw}`;
  return bust ? `${path}${path.includes("?") ? "&" : "?"}v=${encodeURIComponent(bust)}` : path;
}
