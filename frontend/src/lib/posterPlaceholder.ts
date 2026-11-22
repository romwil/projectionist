/** Deterministic poster placeholder. The same item id always picks the same motif. */

export const POSTER_MOTIFS = ["skyline", "road", "tower", "hills", "dunes"] as const;

export type PosterMotif = (typeof POSTER_MOTIFS)[number];

export function posterSeed(key: string): number {
  const text = String(key || "untitled");
  let hash = 2166136261;
  for (let i = 0; i < text.length; i += 1) {
    hash ^= text.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

export function posterMotif(seed: number): PosterMotif {
  return POSTER_MOTIFS[seed % POSTER_MOTIFS.length];
}

export function posterPalette(seed: number): { a: string; b: string; light: string } {
  const hueA = seed % 360;
  const hueB = (hueA + 28 + (seed % 48)) % 360;
  return {
    a: `hsl(${hueA} 42% 32%)`,
    b: `hsl(${hueB} 36% 14%)`,
    light: `hsl(${(hueA + 18) % 360} 72% 74%)`,
  };
}
