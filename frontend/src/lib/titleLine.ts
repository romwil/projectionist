import type {JsonObject, LibraryItem, JsParam} from "../api/types";
/**
 * Shared title + year line for poster/list cards.
 *
 * Year belongs after the title on the same wrapping line
 * (`The Last House on the Left (2009)`), never as its own block.
 * Callers should render {@link titleWithYear} or {@link titleLineParts}
 * inside the heading — not a sibling `<p>`.
 */

const YEAR_SUFFIX_RE = /\(\d{4}\)\s*$/;

/**
 * @param {unknown} value
 * @returns {number | null}
 */
export function mediaYear(value: unknown) {
  if (value == null || value === "") return null;
  const n = Number(value);
  if (!Number.isFinite(n)) return null;
  const year = Math.trunc(n);
  if (year < 1000 || year > 2100) return null;
  return year;
}

/**
 * True when the visible title already ends with `(YYYY)` (any year) or
 * already contains `(<item year>)`, so we must not append a second year.
 *
 * A title that *is* a year (`2012`) is not treated as already labeled.
 *
 * @param {unknown} title
 * @param {number | null} [year]
 */
export function titleAlreadyHasYear(title: string, year: number | null = null) {
  const text = String(title || "").trim();
  if (!text) return false;
  if (YEAR_SUFFIX_RE.test(text)) return true;
  if (year != null && text.includes(`(${year})`)) return true;
  return false;
}

/**
 * @param {{ title?: unknown, year?: unknown } | null | undefined} item
 * @param {{ fallback?: string }} [options]
 * @returns {{ title: string, year: number | null, label: string }}
 */
export function titleLineParts(item: JsParam = null, { fallback = "Untitled" }: JsParam = {}) {
  const raw = String(item?.title ?? "").trim();
  const title = raw || fallback;
  const year = mediaYear(item?.year);
  if (!year || titleAlreadyHasYear(title, year)) {
    return { title, year: null, label: title };
  }
  return { title, year, label: `${title} (${year})` };
}

/**
 * Single-line label: `Title (year)` when year is known and not already in the title.
 *
 * @param {{ title?: unknown, year?: unknown } | null | undefined} item
 * @param {{ fallback?: string }} [options]
 */
export function titleWithYear(item: LibraryItem | JsParam | null | undefined, { fallback = "Untitled" }: JsParam = {}) {
  return titleLineParts(item, { fallback }).label;
}
