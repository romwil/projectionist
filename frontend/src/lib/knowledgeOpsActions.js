/** Owner act button labels for Knowledge Ops staged rows (mirrors backend promote paths). */

export function actLabelForStagedItem(item) {
  const task = item?.task_name;
  const candidate = item?.candidate || {};
  if (task === "facet_taxonomy_audit" && item?.target_entity_type === "facet") {
    return "Approve → overlay";
  }
  if (task === "entity_memory_enrichment") {
    return "Run enrichment";
  }
  if (task === "coverage_deficit_audit") {
    const kind = candidate.deficit_kind;
    if (kind === "theme_keyword") return "Run theme tagging";
    if (kind === "motif" || kind === "metadata" || kind === "synopsis" || kind === "embedding") {
      return "Run enrichment";
    }
    return "Act on gap";
  }
  return null;
}

export function actDescriptionForStagedItem(item) {
  const task = item?.task_name;
  const candidate = item?.candidate || {};
  const label =
    candidate.name ||
    candidate.keyword ||
    candidate.title ||
    item?.target_entity_id ||
    "this item";
  if (task === "entity_memory_enrichment") {
    return `Refresh repository-memory research for “${label}” via official APIs.`;
  }
  if (task === "coverage_deficit_audit") {
    const kind = candidate.deficit_kind || "gap";
    if (kind === "theme_keyword") {
      return (
        `Queue a keyword/theme tagging pass for “${label}”. ` +
        "Does not auto-map keywords — review mapping separately."
      );
    }
    if (kind === "motif") return `Extract motif facets from plot text for “${label}”.`;
    if (kind === "metadata") return `Fetch TMDB metadata for “${label}”.`;
    if (kind === "synopsis") return `Fetch long synopsis for “${label}” (Wikipedia/OMDb per settings).`;
    if (kind === "embedding") return `Generate semantic embedding for “${label}”.`;
    return `Run the best available enrichment for this ${kind} gap.`;
  }
  return "";
}

export function canActOnStagedItem(item) {
  return Boolean(actLabelForStagedItem(item)) && item?.status === "pending";
}
