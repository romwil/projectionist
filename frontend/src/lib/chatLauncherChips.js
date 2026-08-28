export const CHAT_LAUNCHER_CHIPS = [
  {
    id: "tonight-under-2h",
    label: "Tonight under 2h",
    testId: "chat-chip-tonight-under-2h",
    action: {
      type: "send",
      prompt:
        "Suggest something unwatched from my library under two hours — good for tonight.",
    },
  },
  {
    id: "continue-watching",
    label: "Continue watching",
    testId: "chat-chip-continue-watching",
    action: {
      type: "send",
      prompt:
        "What should I continue watching from my in-progress titles? Prioritize shows and movies I've started but not finished.",
    },
  },
  {
    id: "something-like",
    label: "Something like…",
    testId: "chat-chip-something-like",
    action: { type: "prefill", text: "Something like " },
  },
];

export function resolveChatLauncherChipAction(chip) {
  const action = chip?.action;
  if (!action?.type) return null;
  if (action.type === "send" && String(action.prompt || "").trim()) {
    return { type: "send", prompt: String(action.prompt).trim() };
  }
  if (action.type === "prefill") {
    return { type: "prefill", text: String(action.text ?? "") };
  }
  return null;
}
