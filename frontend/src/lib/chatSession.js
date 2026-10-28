export const PERFECT_PICK_ACK =
  "\n\n*(You're on a roll with these picks — I'll keep that momentum going.)*";

export const ADD_FEEDBACK_DISMISS_MS = 5000;
export const THREAD_DELETE_UNDO_MS = 6000;

export function isNightOwlHour(now = new Date()) {
  return now.getHours() >= 23;
}

export function appendPerfectPickAck(message) {
  if (!message?.blocks?.length) return message;
  const blocks = message.blocks.map((block, index) => {
    if (index === 0 && block.type === "text") {
      return { ...block, content: `${block.content}${PERFECT_PICK_ACK}` };
    }
    return block;
  });
  return { ...message, blocks };
}

export function arrServiceConnected(setup, features, service) {
  if (setup?.checks?.[service]?.ok) return true;
  return Boolean(features?.arr?.[`${service}_configured`]);
}

export function chatErrorMessage(reason, snark = 0.5) {
  if (snark >= 0.66) {
    return `Well, that didn't work — ${reason}`;
  }
  if (snark <= 0.33) {
    return `Sorry, I couldn't respond just now: ${reason}`;
  }
  return `Curator couldn't respond: ${reason}`;
}

export function pickStoredThreadId(threadList, storedId, loaded) {
  const storedExists = (threadList || []).some((thread) => thread.id === storedId);
  if (!storedExists && !loaded) {
    if (threadList?.length > 0) return { nextId: threadList[0].id, create: false };
    return { nextId: null, create: true };
  }
  return { nextId: storedId, create: false };
}
