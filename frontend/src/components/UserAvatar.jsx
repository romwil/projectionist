import { useState } from "react";
import { resolveAvatarSrc } from "../lib/avatarSrc.js";

function initials(name) {
  const parts = String(name || "U")
    .trim()
    .split(/\s+/)
    .filter(Boolean);
  if (!parts.length) return "U";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0] || ""}${parts[1][0] || ""}`.toUpperCase();
}

/**
 * Avatar image with initials fallback when Plex/remote URLs fail to load.
 */
export default function UserAvatar({
  user,
  className = "user-menu-avatar",
  fallbackClassName = "user-menu-avatar user-menu-avatar-fallback",
  cacheBust,
}) {
  const [failed, setFailed] = useState(false);
  const src = resolveAvatarSrc(user?.avatar_url, cacheBust);

  if (!src || failed) {
    return (
      <span className={fallbackClassName} data-testid="user-avatar-fallback">
        {initials(user?.display_name || user?.preferred_name)}
      </span>
    );
  }

  return (
    <img
      src={src}
      alt=""
      className={className}
      data-testid="user-avatar-image"
      onError={() => setFailed(true)}
    />
  );
}
