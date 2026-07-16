/** Normalize GET /api/library/quick-pick into UI state (never silent). */

export const QUICK_PICK_EMPTY_MESSAGE = "No unwatched titles match the criteria.";
export const QUICK_PICK_ERROR_FALLBACK = "Couldn't pick a title right now.";

/**
 * @param {unknown} result
 * @returns {{ item: object | null, why: string | null, status: "ready" | "empty", message: string | null }}
 */
export function normalizeQuickPickResult(result) {
  const item = result && typeof result === "object" ? result.item : null;
  const why =
    result && typeof result === "object" && typeof result.why === "string" ? result.why : null;

  if (item && typeof item === "object") {
    return {
      item,
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
