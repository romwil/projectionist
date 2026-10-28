import type { JsParam } from "../api/types";
/** Hash targets on /about. Sections paint with the page, then this scrolls. */
export const ABOUT_HASH_IDS = Object.freeze(["license", "release-notes"]);

export function aboutHashTargetId(hash: unknown) {
  const id = String(hash || "")
    .replace(/^#/, "")
    .trim();
  return ABOUT_HASH_IDS.includes(id) ? id : "";
}

/**
 * Scroll an About page hash target into view.
 *
 * Call this once the About sections are in the DOM so `#license` and
 * `#release-notes` land on the section instead of the top of the page.
 *
 * @param {string} hash location.hash (`#license`)
 * @param {(id: string) => { scrollIntoView?: Function } | null} [getElementById]
 * @returns {boolean} true when a matching node was scrolled
 */
export function scrollAboutHashIntoView(
  hash: JsParam,
  getElementById = (id: JsParam) =>
    typeof document !== "undefined" ? document.getElementById(id) : null,
) {
  const id = aboutHashTargetId(hash);
  if (!id) return false;
  const el = typeof getElementById === "function" ? getElementById(id) : null;
  if (!el || typeof el.scrollIntoView !== "function") return false;
  el.scrollIntoView();
  return true;
}
