/** Display helpers for persona nicknames (builtins) vs plain names (custom). */

/** Dropdown / preset card: "The Professor — Academic Critic", else just name. */
export function personaDropdownLabel(persona) {
  const name = String(persona?.name || "").trim();
  const nickname = String(persona?.nickname || "").trim();
  if (nickname && name) return `${nickname} — ${name}`;
  return nickname || name || "Persona";
}

/** Thread chip / short label: prefer nickname, else name. */
export function personaChipLabel(persona) {
  const nickname = String(persona?.nickname || "").trim();
  if (nickname) return nickname;
  return String(persona?.name || "").trim() || "Persona";
}
