/**
 * A11Y-005: one YouTube embed URL for every trailer dialog. No autoplay, so
 * audio never covers a screen reader reading the dialog name; the dialog
 * focuses the player and one Enter starts it.
 */
export function trailerEmbedUrl(youtubeKey: unknown): string {
  const key = String(youtubeKey || "").trim();
  return `https://www.youtube-nocookie.com/embed/${encodeURIComponent(key)}?rel=0`;
}

/** Stable callback ref: focus the trailer player once when the dialog mounts it. */
export function focusTrailerFrame(node: HTMLIFrameElement | null): void {
  node?.focus();
}
