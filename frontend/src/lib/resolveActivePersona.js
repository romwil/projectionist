/**
 * Resolve which persona should be active in the chat dropdown.
 *
 * Priority:
 * 1. Current selection if still present in the list
 * 2. Thread-bound persona (persisted on the conversation)
 * 3. Explicit defaultPersonaId
 * 4. Persona marked is_default
 * 5. First available persona
 *
 * @param {{
 *   activePersonaId?: string | null,
 *   threadPersonaId?: string | null,
 *   defaultPersonaId?: string | null,
 *   personas?: Array<{ id: string, is_default?: boolean }>,
 * }} opts
 * @returns {string | null}
 */
export function resolveActivePersonaId({
  activePersonaId = null,
  threadPersonaId = null,
  defaultPersonaId = null,
  personas = [],
} = {}) {
  const ids = new Set(personas.map((p) => p.id).filter(Boolean));
  if (activePersonaId && ids.has(activePersonaId)) return activePersonaId;
  if (threadPersonaId && ids.has(threadPersonaId)) return threadPersonaId;
  if (defaultPersonaId && ids.has(defaultPersonaId)) return defaultPersonaId;
  const markedDefault = personas.find((p) => p.is_default);
  if (markedDefault?.id) return markedDefault.id;
  return personas[0]?.id ?? null;
}
