/** Taste slider weights are a 0–1 fraction. Legacy rows stored 2.0 (200%). */

export function clampTasteWeight(weight) {
  const n = Number(weight);
  if (!Number.isFinite(n)) return 0;
  return Math.min(1, Math.max(0, n));
}

export function formatTasteWeight(weight) {
  const n = Number(weight);
  if (!Number.isFinite(n)) return "—";
  return `${Math.round(clampTasteWeight(n) * 100)}%`;
}
