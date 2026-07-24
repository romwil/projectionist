/** Normalize GET /api/library/quick-pick into UI state (never silent). */

export const QUICK_PICK_EMPTY_MESSAGE = "No unwatched titles match the criteria.";
export const QUICK_PICK_ERROR_FALLBACK = "Couldn't pick a title right now.";

/** One-shot mood chips above Surprise Me (Companion Phase 5). */
export const SURPRISE_MOOD_CHIPS = [
  { id: "cozy", label: "Cozy" },
  { id: "thrill", label: "Thrill" },
  { id: "laugh", label: "Laugh" },
  { id: "think", label: "Think" },
  { id: "escape", label: "Escape" },
];

/**
 * Resolve the mood string sent with a Surprise Me request.
 * Chip clicks pass a string id; the dice button uses the optional selected mood.
 *
 * @param {unknown} moodOverride
 * @param {string} [selectedMood]
 * @returns {string}
 */
export function resolveQuickPickMood(moodOverride, selectedMood = "") {
  if (typeof moodOverride === "string") return moodOverride.trim();
  return String(selectedMood || "").trim();
}

/**
 * @param {string} [mood]
 * @returns {string} Query suffix including `?`, or empty string
 */
export function quickPickMoodQuery(mood) {
  const key = String(mood || "").trim();
  if (!key) return "";
  return `?mood=${encodeURIComponent(key)}`;
}

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

/**
 * Convert a Surprise Me result into the same compact recommendation blocks used
 * by the chat transcript. Keeping the explanation after the card preserves the
 * recommendation → rationale reading order without a bespoke hero treatment.
 */
export function quickPickToAssistantMessage(pick) {
  if (pick?.status === "ready" && pick.item) {
    return {
      role: "assistant",
      blocks: [
        { type: "title_cards", items: [pick.item] },
        {
          type: "text",
          content: pick.why || "A random unwatched pick from your library for tonight.",
        },
      ],
    };
  }
  return {
    role: "assistant",
    blocks: [{ type: "text", content: pick?.message || QUICK_PICK_ERROR_FALLBACK }],
  };
}
