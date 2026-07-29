/**
 * Surprising-neighbor presentation: honest "why" copy from real plot scores.
 *
 * Server formula: surprise = cosine × (1 − metadata_overlap).
 * We never invent scores — only restate score / surprise_score / genres.
 */

export const SURPRISE_SECTION_INTRO =
  "Titles that share DNA but sit far from the obvious shelf — close in plot space, distant on genre and credit cards.";

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

function shelfDistanceLabel(overlap) {
  if (overlap == null) return null;
  if (overlap <= 0.15) return "Almost no shared genre, keyword, or credit cards";
  if (overlap <= 0.35) return "Shelf labels barely overlap";
  if (overlap <= 0.55) return "Only partial shelf overlap";
  return "Some shelf overlap — still ranked for plot pull";
}

/**
 * Build showcase copy for one surprising neighbor.
 * @returns {{ headline: string, detail: string, signals: string[] } | null}
 */
export function buildSurpriseWhy(item, { seedGenres } = {}) {
  if (!item || typeof item !== "object") return null;

  const cosine = clampUnit(item.score);
  const surprise = clampUnit(
    item.surprise_score != null ? item.surprise_score : item.match_score,
  );
  const overlap =
    item.metadata_overlap != null
      ? clampUnit(item.metadata_overlap)
      : metadataOverlapFromScores(cosine, surprise);

  const signals = [];
  const plotLabel = plotKinshipLabel(cosine);
  if (plotLabel) signals.push(plotLabel);

  const shelfLabel = shelfDistanceLabel(overlap);
  if (shelfLabel) signals.push(shelfLabel);

  const contrast = genreContrast(seedGenres, item.genres);
  if (contrast.shared.length) {
    signals.push(`Shared genres: ${contrast.shared.slice(0, 3).join(", ")}`);
  }
  if (contrast.neighborOnly.length && (seedGenres || []).length) {
    signals.push(
      `Different shelf: ${contrast.neighborOnly.slice(0, 3).join(", ")}`,
    );
  } else if (contrast.neighborOnly.length && !contrast.shared.length) {
    signals.push(`Genres: ${contrast.neighborOnly.slice(0, 3).join(", ")}`);
  }

  if (!signals.length) return null;

  const headline =
    overlap != null && overlap <= 0.35 && cosine != null && cosine >= 0.55
      ? "Plot twin on a different shelf"
      : overlap != null && overlap <= 0.55 && cosine != null && cosine >= 0.4
        ? "Narrative neighbor, unexpected company"
        : "Surprising plot neighbor";

  const detail = signals.join(" · ");
  return { headline, detail, signals };
}

export function visibleSurpriseItems(items, { expanded = false, initial = SURPRISE_SHOWCASE_INITIAL } = {}) {
  const list = Array.isArray(items) ? items : [];
  if (expanded || list.length <= initial) return list;
  return list.slice(0, initial);
}
