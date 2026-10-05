/**
 * Surprising-neighbor presentation.
 *
 * A neighbor is surprising only when the server names a plot link (`plot_link`).
 * Low shelf overlap can follow that sentence. It is not a reason by itself.
 */

export const SURPRISE_SECTION_INTRO =
  "A story kinship the shelf would not suggest — included only when we can say what the plots share.";

export const SURPRISE_SHOWCASE_INITIAL = 6;

export function clampUnit(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return null;
  if (n <= 0) return 0;
  if (n >= 1) return 1;
  return n;
}

/** Recover Jaccard-style overlap from cached cosine + surprise (exact inverse). */
export function metadataOverlapFromScores(score, surpriseScore) {
  const cosine = clampUnit(score);
  const surprise = clampUnit(surpriseScore);
  if (cosine == null || surprise == null || cosine <= 0) return null;
  return clampUnit(1 - surprise / cosine);
}

function normalizeGenreList(genres) {
  if (!Array.isArray(genres)) return [];
  const seen = new Set();
  const out = [];
  for (const raw of genres) {
    const label = String(raw || "").trim();
    if (!label) continue;
    const key = label.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(label);
  }
  return out;
}

export function genreContrast(seedGenres, neighborGenres) {
  const seed = normalizeGenreList(seedGenres);
  const neighbor = normalizeGenreList(neighborGenres);
  if (!seed.length || !neighbor.length) {
    return { shared: [], seedOnly: seed, neighborOnly: neighbor };
  }
  const seedKeys = new Set(seed.map((g) => g.toLowerCase()));
  const neighborKeys = new Set(neighbor.map((g) => g.toLowerCase()));
  return {
    shared: seed.filter((g) => neighborKeys.has(g.toLowerCase())),
    seedOnly: seed.filter((g) => !neighborKeys.has(g.toLowerCase())),
    neighborOnly: neighbor.filter((g) => !seedKeys.has(g.toLowerCase())),
  };
}

function plotKinshipLabel(cosine) {
  if (cosine == null) return null;
  if (cosine >= 0.85) return "Very close in plot space";
  if (cosine >= 0.7) return "Strong plot kinship";
  if (cosine >= 0.55) return "Solid plot kinship";
  if (cosine >= 0.4) return "Mild plot kinship";
  return "Loose plot kinship";
}

const ABSENCE_REASON =
  /almost no shared|nothing in common|barely overlap|partial shelf|some shelf overlap|no shared genre|credit labels|credit cards/i;

/**
 * Build showcase copy for one surprising neighbor.
 * A title with no named plot link is not surprising — low shelf overlap is not a reason.
 * @returns {{ headline: string, detail: string, signals: string[] } | null}
 */
export function buildSurpriseWhy(item, { seedGenres } = {}) {
  if (!item || typeof item !== "object") return null;
  const link = String(item.plot_link || "").trim();
  if (!link || ABSENCE_REASON.test(link)) return null;

  const cosine = clampUnit(item.score);
  const surprise = clampUnit(
    item.surprise_score != null ? item.surprise_score : item.match_score,
  );
  const overlap =
    item.metadata_overlap != null
      ? clampUnit(item.metadata_overlap)
      : metadataOverlapFromScores(cosine, surprise);

  const signals = [link];
  const plotLabel = plotKinshipLabel(cosine);
  if (plotLabel) signals.push(plotLabel);
  if (overlap != null && overlap <= 0.35) {
    signals.push("Shelf labels barely overlap");
  }

  const contrast = genreContrast(seedGenres, item.genres);
  if (contrast.neighborOnly.length && (seedGenres || []).length) {
    signals.push(
      `Different shelf: ${contrast.neighborOnly.slice(0, 3).join(", ")}`,
    );
  }

  return { headline: link, detail: signals.join(" · "), signals };
}

export function visibleSurpriseItems(items, { expanded = false, initial = SURPRISE_SHOWCASE_INITIAL } = {}) {
  const list = Array.isArray(items) ? items : [];
  if (expanded || list.length <= initial) return list;
  return list.slice(0, initial);
}
