/** Hash targets on /about that should scroll after AppShell authReady. */
export const ABOUT_HASH_IDS = Object.freeze(["license", "release-notes"]);

export function aboutHashTargetId(hash) {
  const id = String(hash || "")
    .replace(/^#/, "")
    .trim();
  return ABOUT_HASH_IDS.includes(id) ? id : "";
}

/**
 * Scroll an About page hash target into view.
 *
 * AppShell withholds children until authReady, so the browser's native
 * `#license` / `#release-notes` jump lands at the top. Call this after
 * the About sections are in the DOM.
 *
 * @param {string} hash location.hash (`#license`)
 * @param {(id: string) => { scrollIntoView?: Function } | null} [getElementById]
 * @returns {boolean} true when a matching node was scrolled
 */
export function scrollAboutHashIntoView(
  hash,
  getElementById = (id) =>
    typeof document !== "undefined" ? document.getElementById(id) : null,
) {
  const id = aboutHashTargetId(hash);
  if (!id) return false;
  const el = typeof getElementById === "function" ? getElementById(id) : null;
  if (!el || typeof el.scrollIntoView !== "function") return false;
  el.scrollIntoView();
  return true;
}
