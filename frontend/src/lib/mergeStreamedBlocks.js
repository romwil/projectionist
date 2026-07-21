/**
 * Lossless-merge safety net for the streamed chat message.
 *
 * During a live stream the user watches the curator's prose arrive
 * token-by-token (`streamAccumulated`). When the stream finishes, `onDone`
 * swaps the streamed placeholder message for the backend's fully-assembled
 * `blocks`. If a provider only surfaced prose via tokens — or the backend
 * still fell back to the generic "Here are the results I found." placeholder —
 * that swap would visibly erase text the user already read.
 *
 * This helper guarantees no visible loss: when the backend's leading text
 * block is empty or the generic placeholder while the streamed prose is real,
 * we keep the streamed prose as the text block and append the backend's
 * non-text blocks (title_cards, action_prompt/open_viewport, suggested_replies,
 * etc.). When the backend text is real, the backend blocks are used as-is.
 *
 * Pure and side-effect free so it can be unit-tested in isolation.
 *
 * @param {object} message - the backend `done` message ({ blocks, ... }).
 * @param {string} streamAccumulated - prose accumulated from token events.
 * @returns {object} the message to render (possibly a new object).
 */
export const GENERIC_RESULTS_PLACEHOLDER = "Here are the results I found.";

export function mergeStreamedBlocks(message, streamAccumulated) {
  if (!message || typeof message !== "object") return message;

  const streamedProse = typeof streamAccumulated === "string" ? streamAccumulated.trim() : "";
  if (!streamedProse) return message;

  const blocks = Array.isArray(message.blocks) ? message.blocks : [];
  const leadingText = blocks.find((block) => block && block.type === "text");
  const backendText =
    leadingText && typeof leadingText.content === "string" ? leadingText.content.trim() : "";

  const backendTextIsMissingOrPlaceholder =
    !backendText || backendText === GENERIC_RESULTS_PLACEHOLDER;

  if (!backendTextIsMissingOrPlaceholder) {
    return message;
  }

  const nonTextBlocks = blocks.filter((block) => block && block.type !== "text");
  return {
    ...message,
    blocks: [{ type: "text", content: streamedProse }, ...nonTextBlocks],
  };
}
