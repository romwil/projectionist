/**
 * Prefer a warm/friendly persona id for Youth-mode accounts.
 * @param {Array<{ id?: string, name?: string, visibility?: string }>} personas
 * @param {string | null} [fallbackId]
 */
export function preferYouthFriendlyPersona(personas = [], fallbackId = null) {
  const list = Array.isArray(personas) ? personas : [];
  const scored = list.map((persona) => {
    const name = String(persona?.name || "").toLowerCase();
    let score = 0;
    if (name.includes("companion")) score += 5;
    if (name.includes("youth") || name.includes("family") || name.includes("kid")) score += 4;
    if (name.includes("friendly") || name.includes("warm")) score += 2;
    if (persona?.visibility === "builtin") score += 1;
    return { id: persona?.id, score };
  });
  scored.sort((a, b) => b.score - a.score);
  if (scored[0]?.score > 0 && scored[0].id) return scored[0].id;
  return fallbackId;
}
