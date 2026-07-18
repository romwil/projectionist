/** Normalize GET /api/library/quick-pick into UI state (never silent). */

export const QUICK_PICK_EMPTY_MESSAGE = "No unwatched titles match the criteria.";
export const QUICK_PICK_ERROR_FALLBACK = "Couldn't pick a title right now.";

/**
 * Coerce API genres (array or JSON string) so TitleCard never crashes on `.join`.
 * @param {unknown} genres
 * @returns {string[]}
 */
export function normalizeQuickPickGenres(genres) {
  if (Array.isArray(genres)) {
    return genres.map((g) => String(g));
  }
  if (typeof genres === "string" && genres.trim()) {
    try {
      const parsed = JSON.parse(genres);
      return Array.isArray(parsed) ? parsed.map((g) => String(g)) : [];
    } catch {
      return [];
    }
  }
  return [];
}

/**
 * @param {unknown} result
 * @returns {{ item: object | null, why: string | null, status: "ready" | "empty", message: string | null }}
 */
export function normalizeQuickPickResult(result) {
  const item = result && typeof result === "object" ? result.item : null;
  const why =
    result && typeof result === "object" && typeof result.why === "string" ? result.why : null;

  if (item && typeof item === "object") {
    const overview =
      (typeof item.overview === "string" && item.overview.trim()) ||
      (typeof item.summary === "string" ? item.summary : "") ||
      "";
    return {
      item: {
        ...item,
        genres: normalizeQuickPickGenres(item.genres),
        overview,
        in_library: true,
      },
      why,
      status: "ready",
      message: null,
    };
  }

  return {
    item: null,
    why: null,
    status: "empty",
    message: why || QUICK_PICK_EMPTY_MESSAGE,
  };
}

/**
 * @param {unknown} error
 * @param {(err: unknown) => string} [formatError]
 */
export function normalizeQuickPickError(error, formatError) {
  const formatted =
    typeof formatError === "function" ? formatError(error) : error?.message || "";
  const message = String(formatted || "").trim() || QUICK_PICK_ERROR_FALLBACK;
  return {
    item: null,
    why: null,
    status: "error",
    message,
  };
}
