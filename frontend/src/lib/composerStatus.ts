export const COMPOSER_OPENING_LINE = "Opening your library…";
export const COMPOSER_IDLE_PLACEHOLDER = "Describe what you're hunting for…";

/**
 * A11Y-009: what the chat composer says about itself. While it cannot take
 * input yet it never shows the typing invitation, and `statusLine` is the
 * polite live-region text a screen reader hears once.
 */
export function composerStatus({
  ready = true,
  listening = false,
  placeholder = "",
}: { ready?: boolean; listening?: boolean; placeholder?: string | null } = {}) {
  if (!ready) {
    return { placeholder: COMPOSER_OPENING_LINE, statusLine: COMPOSER_OPENING_LINE };
  }
  if (listening) return { placeholder: "Listening…", statusLine: "" };
  return { placeholder: String(placeholder || "").trim() || COMPOSER_IDLE_PLACEHOLDER, statusLine: "" };
}
