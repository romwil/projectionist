export const PERSONA_CONSULT_BACKEND_HARD_DEADLINE_MS = 55_000;
export const PERSONA_CONSULT_FIRST_POLL_MS = 1_200;
export const PERSONA_CONSULT_POLL_MS = 2_000;
const PERSONA_CONSULT_POLL_NETWORK_GRACE_MS = 1_800;
export const PERSONA_CONSULT_POLL_WINDOW_MS =
  PERSONA_CONSULT_BACKEND_HARD_DEADLINE_MS +
  PERSONA_CONSULT_FIRST_POLL_MS +
  PERSONA_CONSULT_POLL_MS +
  PERSONA_CONSULT_POLL_NETWORK_GRACE_MS;

function consultBlocks(messages) {
  return (Array.isArray(messages) ? messages : [])
    .flatMap((message) => (Array.isArray(message?.blocks) ? message.blocks : []))
    .filter((block) => block?.type === "persona_consult" && block.payload);
}

export function hasPendingPersonaConsult(messages) {
  const blocks = consultBlocks(messages);
  const completed = new Set(
    blocks
      .filter((block) => block.payload?.answer)
      .map((block) => String(block.payload?.consult_id || ""))
      .filter(Boolean),
  );
  return blocks.some((block) => {
    const consultId = String(block.payload?.consult_id || "");
    return Boolean(block.payload?.pending && consultId && !completed.has(consultId));
  });
}

function messageTextFingerprint(message) {
  const role = String(message?.role || "");
  const texts = (Array.isArray(message?.blocks) ? message.blocks : [])
    .filter((block) => block?.type === "text")
    .map((block) => String(block.content || "").trim())
    .filter(Boolean);
  if (!role || !texts.length) return "";
  return `${role}::${texts.join("\n")}`;
}

/**
 * Merge a thread poll snapshot into the live transcript.
 *
 * Later user turns keep optimistic client ids until this poll; the snapshot
 * repeats those same bubbles with server ids. Match them in place (role + text)
 * and append only messages the client has not already rendered — typically the
 * delayed consult addendum.
 */
export function mergeThreadMessagesById(current, fetched) {
  const currentList = (Array.isArray(current) ? current : []).filter((message) => message?.id);
  const fetchedList = (Array.isArray(fetched) ? fetched : []).filter((message) => message?.id);
  const fetchedById = new Map(fetchedList.map((message) => [message.id, message]));
  const currentIds = new Set(currentList.map((message) => message.id));

  const unusedByFingerprint = new Map();
  for (const message of currentList) {
    if (fetchedById.has(message.id)) continue;
    const fingerprint = messageTextFingerprint(message);
    if (!fingerprint) continue;
    const bucket = unusedByFingerprint.get(fingerprint) || [];
    bucket.push(message.id);
    unusedByFingerprint.set(fingerprint, bucket);
  }

  const fetchedIdForCurrentId = new Map();
  for (const message of fetchedList) {
    if (currentIds.has(message.id)) continue;
    const fingerprint = messageTextFingerprint(message);
    const matchId = fingerprint ? unusedByFingerprint.get(fingerprint)?.shift() : null;
    if (!matchId) continue;
    fetchedIdForCurrentId.set(matchId, message.id);
  }

  const merged = [];
  const emittedFetchedIds = new Set();
  for (const message of currentList) {
    const snapshot = fetchedById.get(fetchedIdForCurrentId.get(message.id) || message.id);
    if (snapshot) {
      merged.push({ ...message, ...snapshot });
      emittedFetchedIds.add(snapshot.id);
      continue;
    }
    merged.push(message);
  }

  for (const message of fetchedList) {
    if (emittedFetchedIds.has(message.id)) continue;
    merged.push(message);
  }
  return merged;
}

export function shouldSchedulePersonaConsultPoll({ pollStartedAt, deadline }) {
  return pollStartedAt < deadline;
}
