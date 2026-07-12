/**
 * Slack-style composer Enter handling:
 * - Enter submits when the message can be sent
 * - Shift+Enter inserts a newline (default textarea behavior)
 * - Ignore Enter during IME composition
 */
export function shouldSubmitComposerOnEnter(event, { canSubmit = false } = {}) {
  if (event.key !== "Enter" || event.shiftKey) return false;
  if (event.isComposing || event.keyCode === 229) return false;
  return Boolean(canSubmit);
}
