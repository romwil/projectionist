/**
 * Browser voice helpers (Web Speech API) — pure enough to unit-test with mocks.
 */

export function stripMarkdownForSpeech(text) {
  if (!text) return "";
  return String(text)
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/!\[[^\]]*\]\([^)]*\)/g, " ")
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/[*_~#>]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

export function extractSpeakableText(message) {
  if (!message?.blocks?.length) return "";
  const parts = [];
  for (const block of message.blocks) {
    if (block?.type === "text" && block.content) {
      const cleaned = stripMarkdownForSpeech(block.content);
      if (cleaned) parts.push(cleaned);
    }
  }
  return parts.join(" ").replace(/\s+/g, " ").trim();
}

/** Join a base composer string with a new transcript chunk. */
export function joinTranscript(base, chunk) {
  const left = (base || "").replace(/\s+$/, "");
  const right = (chunk || "").replace(/^\s+/, "");
  if (!left) return right;
  if (!right) return left;
  const needsSpace = !/[\s([{/]$/.test(left) && !/^[,.;:!?)\]}]/.test(right);
  return needsSpace ? `${left} ${right}` : `${left}${right}`;
}

/**
 * Reduce a SpeechRecognition result list into final + interim strings.
 * @param {ArrayLike<{ isFinal?: boolean, 0?: { transcript?: string }, length?: number }>} results
 * @param {number} [resultIndex]
 */
export function reduceRecognitionResults(results, resultIndex = 0) {
  let finalChunk = "";
  let interimChunk = "";
  if (!results) return { finalChunk, interimChunk };
  const start = Math.max(0, Number(resultIndex) || 0);
  for (let i = start; i < results.length; i += 1) {
    const result = results[i];
    const transcript = result?.[0]?.transcript || "";
    if (!transcript) continue;
    if (result.isFinal) finalChunk += transcript;
    else interimChunk += transcript;
  }
  return { finalChunk, interimChunk };
}

export function shouldSpeakReply({
  prefs,
  support,
  muted = false,
  listening = false,
  text = "",
} = {}) {
  if (muted) return false;
  if (listening) return false;
  if (!prefs?.voice_speak_replies) return false;
  if (!support?.speak) return false;
  return Boolean(String(text || "").trim());
}

export function shouldShowMicButton({ prefs, support } = {}) {
  return Boolean(prefs?.voice_input_enabled && support?.input);
}

export function speakText(text, {
  synthesis = typeof window !== "undefined" ? window.speechSynthesis : null,
  utteranceFactory = (value) => new SpeechSynthesisUtterance(value),
  muted = false,
  onStart,
  onEnd,
  onError,
} = {}) {
  const cleaned = String(text || "").trim();
  if (!cleaned || muted || !synthesis) return null;
  try {
    synthesis.cancel();
  } catch {
    // ignore
  }
  const utterance = utteranceFactory(cleaned);
  if (onStart) utterance.onstart = onStart;
  if (onEnd) utterance.onend = onEnd;
  if (onError) utterance.onerror = onError;
  synthesis.speak(utterance);
  return utterance;
}

export function stopSpeaking(synthesis = typeof window !== "undefined" ? window.speechSynthesis : null) {
  if (!synthesis) return;
  try {
    synthesis.cancel();
  } catch {
    // ignore
  }
}
