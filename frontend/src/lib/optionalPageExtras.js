/**
 * Secondary blocks under chat home and search.
 * They stay available, but the disclosure starts closed.
 * Native <details> does not persist — same as other in-page disclosures.
 */

export const HOME_OPTIONAL_SUMMARY = "More from home";
export const SEARCH_OPTIONAL_SUMMARY = "Beyond your collection";

/** Chat home only. A thread in progress is not this group. */
export function chatHomeOptionalGroup(options) {
  return {
    show: options?.showWelcome === true,
    startOpen: false,
  };
}

/**
 * Search route only. Library browse keeps the beyond block inline.
 * Shown when an outside-the-library search can run, or when that search
 * is known to be unavailable (the note lives in the same group).
 */
export function searchOptionalGroup(options) {
  const show =
    options?.isSearchRoute === true &&
    (options?.showBeyond === true || options?.beyondUnavailable === true);
  return { show, startOpen: false };
}
