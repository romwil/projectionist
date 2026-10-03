/** Owner-facing action copy for Library knowledge reviews. */

/** Human row title — never bare target_entity_id. */
export function stagedItemDisplayTitle(item) {
  const candidate = item?.candidate || {};
  const title =
    candidate.title ||
    candidate.alias ||
    candidate.name ||
    candidate.keyword ||
    "";
  return String(title || "").trim();
}

export function actLabelForStagedItem(item) {
  const task = item?.task_name;
  const candidate = item?.candidate || {};
  if (task === "facet_taxonomy_audit" && item?.target_entity_type === "facet") {
    return "Save mapping";
  }
  if (task === "entity_memory_enrichment") {
    return "Refresh synopsis";
  }
  if (task === "coverage_deficit_audit") {
    const kind = candidate.deficit_kind;
    // Automatic lookup already ran and gave up; this is an explicit second try.
    if (candidate.retrieval_exhausted) return "Try again now";
    if (kind === "theme_keyword") return "Refresh themes";
    if (kind === "motif") return "Find plot patterns";
    if (kind === "embedding") return "Update plot similarity";
    return "Refresh synopsis";
  }
  return null;
}

/** One-line reason an automatic lookup gave up, for owner-facing rows. */
export function retrievalFailureSummary(item) {
  const candidate = item?.candidate || {};
  if (!candidate.retrieval_exhausted) return "";
  const tries = Number(candidate.attempts) || 0;
  const triesText = tries > 1 ? `after ${tries} tries` : "";
  const detail = String(candidate.failure_detail || "").trim();
  let reason = "automatic lookup could not fill this in";
  if (candidate.failure === "miss") reason = "nothing found upstream";
  else if (candidate.failure === "hard") reason = detail || "the source rejected this title";
  else if (candidate.failure === "error") reason = detail || "the source kept failing";
  return [reason, triesText].filter(Boolean).join(" ");
}

export function actDescriptionForStagedItem(item) {
  const task = item?.task_name;
  const candidate = item?.candidate || {};
  const label = stagedItemDisplayTitle(item) || "this item";
  if (task === "coverage_deficit_audit" && candidate.retrieval_exhausted) {
    return `Look up “${label}” again right now. Automatic lookup already tried and gave up.`;
  }
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
    return `Refresh synopsis and available details for “${label}”.`;
  }
  return "";
}

export function canActOnStagedItem(item) {
  return Boolean(actLabelForStagedItem(item)) && item?.status === "pending";
}
