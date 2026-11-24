/** A poster image the browser has already decoded, or not. */
export type DecodedPoster = {
  complete: boolean;
  naturalWidth: number;
};

/**
 * The shelf hands the poster a relative art address. The browser's loaded
 * `src` is absolute. Shown means this address, not that resolved URL.
 */
export function posterIsShown(art: string, loadedSrc: string): boolean {
  const trimmed = String(art || "").trim();
  return Boolean(trimmed) && loadedSrc === trimmed;
}

/** Record a successful load against the art prop. */
export function loadedPosterMark(art: string): string {
  return String(art || "").trim();
}

/**
 * An image that is already complete from cache can be shown without another
 * load event. A broken image (`naturalWidth` 0) stays on the placeholder.
 */
export function cachedPosterMark(art: string, img: DecodedPoster | null): string {
  const trimmed = String(art || "").trim();
  if (!trimmed || !img || !img.complete || img.naturalWidth <= 0) return "";
  return trimmed;
}
