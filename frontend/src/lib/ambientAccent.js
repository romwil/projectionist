/** Cinema-dark ambient washes — cool slate + warm undertones; avoid violet brand clash. */
const AMBIENT_ACCENT_MAP = {
  general: "hsl(210 18% 32%)",
  "neo-noir": "hsl(220 22% 28%)",
  documentary: "hsl(150 22% 30%)",
  horror: "hsl(8 28% 28%)",
  comedy: "hsl(38 40% 34%)",
  "sci-fi": "hsl(195 28% 30%)",
  "1970s": "hsl(28 42% 34%)",
  "1980s": "hsl(200 20% 30%)",
  "1990s": "hsl(215 24% 32%)",
  family: "hsl(165 24% 30%)",
};

const NEUTRAL_ACCENT = "hsl(210 12% 24%)";

export function resolveAmbientAccent(contextHash) {
  const key = String(contextHash || "general")
    .trim()
    .toLowerCase()
    .replace(/\s+/g, "-");
  return AMBIENT_ACCENT_MAP[key] || NEUTRAL_ACCENT;
}

export function blendAmbientAccent(contextHash, personaAccent) {
  const contextAccent = resolveAmbientAccent(contextHash);
  if (!personaAccent) return contextAccent;
  return `color-mix(in srgb, ${contextAccent} 72%, ${personaAccent} 28%)`;
}
