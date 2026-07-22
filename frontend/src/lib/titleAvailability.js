/**
 * Compact where-to-watch line for title detail + chat cards.
 *
 * v1 scope (locked): in-library + Seerr only — no external Netflix/Max connector.
 *
 * @typedef {"in_library" | "requestable" | "not_here"} AvailabilityStatus
 */

/**
 * @param {Record<string, unknown> | null | undefined} item
 * @param {{ requestPath?: string, seerrEnabled?: boolean }} [options]
 * @returns {{ status: AvailabilityStatus, label: string, shortLabel: string }}
 */
export function titleAvailability(item, { requestPath = "arr", seerrEnabled } = {}) {
  if (item?.in_library) {
    return {
      status: "in_library",
      label: "In your library ✓",
      shortLabel: "In library",
    };
  }

  const seerrPath =
    requestPath === "seerr" || seerrEnabled === true;
  const media = String(item?.media_type || "")
    .trim()
    .toLowerCase();
  const mediaOk = !media || media === "movie" || media === "show" || media === "tv";
  const hasTmdb = Boolean(item?.tmdb_id);

  if (seerrPath && hasTmdb && mediaOk) {
    return {
      status: "requestable",
      label: "Requestable",
      shortLabel: "Requestable",
    };
  }

  return {
    status: "not_here",
    label: "Not here yet",
    shortLabel: "Not here yet",
  };
}

/** CSS modifier for availability chip / line. */
export function titleAvailabilityClassName(status) {
  if (status === "in_library") return "title-availability--in-library";
  if (status === "requestable") return "title-availability--requestable";
  return "title-availability--not-here";
}
