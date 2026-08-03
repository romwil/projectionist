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

export function mergeThreadMessagesById(current, fetched) {
  const nextById = new Map(
    (Array.isArray(current) ? current : []).map((message) => [message.id, message]),
  );
  for (const message of Array.isArray(fetched) ? fetched : []) {
    if (!message?.id) continue;
    nextById.set(message.id, { ...nextById.get(message.id), ...message });
  }
  return [...nextById.values()];
}

export function shouldSchedulePersonaConsultPoll({ pollStartedAt, deadline }) {
  return pollStartedAt < deadline;
}
