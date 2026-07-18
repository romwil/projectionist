/**
 * Title-detail + Plot Lab helpers for plot-layer presentation.
 */

const LAYER_LABELS = {
  motif: "Motif",
  keyword: "Keyword",
  plot_text: "Plot text",
  theme: "Theme",
};

/** Humanize a match_layers token for Why? UI. */
export function formatMatchLayerLabel(layer) {
  const key = String(layer || "").trim().toLowerCase();
  if (!key) return "";
  return LAYER_LABELS[key] || key.replace(/_/g, " ");
}

/** Join layer ids into a display string (e.g. "Motif + Keyword"). */
export function formatMatchLayers(layers) {
  const list = (Array.isArray(layers) ? layers : [])
    .map(formatMatchLayerLabel)
    .filter(Boolean);
  return list.join(" + ");
}

/**
 * Build a compact plot-knowledge model from title detail.
 * Feature-detects synopsis / themes so Phase C can land without UI crashes.
 */
export function buildPlotKnowledgePanel(detail) {
  if (!detail || typeof detail !== "object" || !detail.in_library) return null;
  const pk = detail.plot_knowledge && typeof detail.plot_knowledge === "object"
    ? detail.plot_knowledge
    : {};
  const keywords = Array.isArray(detail.keywords)
    ? detail.keywords.map((k) => String(k || "").trim()).filter(Boolean)
    : [];
  const motifs = Array.isArray(pk.motifs)
    ? pk.motifs.map((m) => String(m || "").trim()).filter(Boolean)
    : [];
  const themes = Array.isArray(pk.themes)
    ? pk.themes.map((t) => String(t || "").trim()).filter(Boolean)
    : [];
  const neighborCount = Number(pk.neighbor_count);
  const layers = [
    { id: "overview", label: "Overview", present: Boolean(pk.has_overview || detail.overview) },
    { id: "tagline", label: "Tagline", present: Boolean(pk.has_tagline) },
    { id: "logline", label: "Logline", present: Boolean(pk.has_logline) },
  ];
  if (pk.synopsis_supported) {
    layers.push({
      id: "synopsis",
      label: "Long synopsis",
      present: Boolean(pk.has_synopsis),
    });
  }
  const hasAnySignal =
    layers.some((l) => l.present) ||
    motifs.length > 0 ||
    keywords.length > 0 ||
    themes.length > 0 ||
    (Number.isFinite(neighborCount) && neighborCount > 0);
  if (!hasAnySignal && !detail.in_library) return null;
  return {
    layers,
    motifs,
    keywords,
    themes,
    neighborCount: Number.isFinite(neighborCount) ? neighborCount : 0,
    empty: !hasAnySignal,
  };
}
