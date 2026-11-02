import type { JsParam } from "../api/types";
import { personaChipLabel } from "./personaLabels";

/** Server default for `curator_name`; treated as "the owner has not named the curator". */
export const DEFAULT_CURATOR_NAME = "Curator";
export const GENERIC_CURATOR_NAME = "Your curator";

/**
 * The one name members see for the agent: the owner's curator name when set,
 * else the active voice as the persona picker shows it, else "Your curator".
 */
export function curatorDisplayName(persona?: JsParam | null, activeVoice?: JsParam | null): string {
  const named = String(persona?.curator_name || "").trim();
  if (named && named !== DEFAULT_CURATOR_NAME) return named;
  if (activeVoice && String(activeVoice.nickname || activeVoice.name || "").trim()) {
    return personaChipLabel(activeVoice);
  }
  return GENERIC_CURATOR_NAME;
}

/** Same name for use mid-sentence ("so your curator can't reply"). */
export function curatorNameInSentence(name: string): string {
  return name === GENERIC_CURATOR_NAME ? "your curator" : name;
}

/** Pick the voice a thread speaks in: the selected persona, else the default one. */
export function activeVoice(personas: JsParam[] | null | undefined, activePersonaId?: string | null): JsParam | null {
  const list = Array.isArray(personas) ? personas : [];
  return list.find((p) => p?.id === activePersonaId) || list.find((p) => p?.is_default) || null;
}
