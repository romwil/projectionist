/**
 * Locked title/media CTA grammar — icons, terms, and order.
 * Source of truth for copy: docs/DESIGN.md “Playback & Title surfaces”.
 */

/** Material Symbols Outlined — one glyph per action across title surfaces. */
export const TITLE_CTA_ICONS = Object.freeze({
  play: "play_circle",
  add: "add_circle",
  trailer: "movie",
  review: "rate_review",
  watched: "visibility",
  unwatched: "visibility_off",
  chat: "forum",
  watchTogether: "groups",
  more: "more_horiz",
  openInPlex: "open_in_new",
  lock: "lock",
  markBadMedia: "report",
  delete: "delete",
});

/**
 * Secondary row order (after the single gold primary).
 * `add` only appears here when Play already owns the primary slot.
 */
export const TITLE_CTA_SECONDARY_ORDER = Object.freeze([
  "trailer",
  "review",
  "watched",
  "chat",
  "watchTogether",
  "add",
]);

/** Canonical visible labels + hover/focus explanations. */
export const TITLE_CTA_COPY = Object.freeze({
  play: { label: "Play", tooltip: "Play in Projectionist" },
  add: { label: "Add", tooltip: "Add or request this title" },
  trailer: { label: "Trailer", tooltip: "Watch trailer" },
  review: { label: "Review", tooltip: "Leave a review" },
  chat: { label: "Chat", tooltip: "Chat about this" },
  watchTogether: { label: "Together", tooltip: "Watch together" },
  openInPlex: { label: "Open in Plex", tooltip: "Open in Plex" },
  more: { label: "More", tooltip: "More actions" },
  markBadMedia: { label: "Mark as bad media", tooltip: "Ask *arr to replace a bad file" },
  delete: { label: "Delete", tooltip: "Remove this title" },
  markWatched: { label: "Watched", tooltip: "Mark as watched" },
  markUnwatched: { label: "Unwatched", tooltip: "Mark as unwatched" },
});

/** Actions that collapse into More at phone / compact density. */
export const TITLE_CTA_PHONE_OVERFLOW = Object.freeze(["chat", "watchTogether", "add"]);

export function watchedCtaPresentation(detail) {
  const watched = Number(detail?.view_count || 0) > 0;
  if (watched) {
    return {
      icon: TITLE_CTA_ICONS.unwatched,
      label: TITLE_CTA_COPY.markUnwatched.label,
      tooltip: TITLE_CTA_COPY.markUnwatched.tooltip,
    };
  }
  return {
    icon: TITLE_CTA_ICONS.watched,
    label: TITLE_CTA_COPY.markWatched.label,
    tooltip: TITLE_CTA_COPY.markWatched.tooltip,
  };
}

/** Place a portaled More menu near its trigger without pushing layout. */
export function placeTitleCtaMoreMenu(anchor, menu, viewport = globalThis) {
  const margin = 8;
  const viewW = Number(viewport?.innerWidth) || 1280;
  const viewH = Number(viewport?.innerHeight) || 800;
  const below = anchor.bottom + margin;
  const above = anchor.top - margin - menu.height;
  const top =
    below + menu.height <= viewH - margin
      ? below
      : Math.max(margin, Math.min(above, viewH - menu.height - margin));
  const left = Math.max(margin, Math.min(anchor.left, viewW - menu.width - margin));
  return { top: `${top}px`, left: `${left}px` };
}
