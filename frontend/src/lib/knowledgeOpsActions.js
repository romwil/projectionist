/** Owner-facing action copy for Library knowledge reviews. */

export function actLabelForStagedItem(item) {
  const task = item?.task_name;
  const candidate = item?.candidate || {};
  if (task === "facet_taxonomy_audit" && item?.target_entity_type === "facet") {
    return "Save mapping";
  }
  if (task === "entity_memory_enrichment") {
    return "Refresh details";
  }
  if (task === "coverage_deficit_audit") {
    const kind = candidate.deficit_kind;
    if (kind === "theme_keyword") return "Refresh themes";
    if (kind === "motif") return "Find plot patterns";
    if (kind === "embedding") return "Update plot similarity";
    if (kind === "metadata" || kind === "synopsis") return "Refresh details";
    return "Fill missing knowledge";
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
    return `Refresh trusted title details for “${label}”.`;
  }
  if (task === "coverage_deficit_audit") {
    const kind = candidate.deficit_kind || "gap";
    if (kind === "theme_keyword") {
      return (
        `Refresh themes from the available tags for “${label}”. ` +
        "New name mappings still need separate review."
      );
    }
    if (kind === "motif") {
      return `Find plot patterns in the available summary for “${label}”.`;
    }
    if (kind === "metadata") return `Refresh trusted title details for “${label}”.`;
    if (kind === "synopsis") return `Find a fuller synopsis for “${label}”.`;
    if (kind === "embedding") return `Update plot-similarity data for “${label}”.`;
    return `Fill the available missing knowledge for “${label}”.`;
  }
  return "";
}

export function canActOnStagedItem(item) {
  return Boolean(actLabelForStagedItem(item)) && item?.status === "pending";
}
