/**
 * Pure utility functions for the Owner Dashboard charts.
 * Extracted so they can be imported by both DashboardPage.jsx and Node tests.
 */

const RUNTIME_BUCKET_ORDER = ["Short (<90m)", "Medium (90–120m)", "Long (120–150m)", "Epic (150m+)"];

const RUNTIME_LABEL_MAP = {
  short: "Short (<90m)",
  medium: "Medium (90–120m)",
  long: "Long (120–150m)",
  epic: "Epic (150m+)",
};

function bucketRuntime(minutes) {
  if (minutes < 90) return "Short (<90m)";
  if (minutes < 120) return "Medium (90–120m)";
  if (minutes < 150) return "Long (120–150m)";
  return "Epic (150m+)";
}

/**
 * Groups aggregate runtime entries into canonical duration buckets,
 * returned in display order (Short → Epic).
 */
export function buildRuntimeBuckets(runtimeData) {
  if (!runtimeData?.length) return [];
  const buckets = {};
  for (const entry of runtimeData) {
    const raw = entry.label || entry.group || "";
    const key = RUNTIME_LABEL_MAP[raw.toLowerCase()] || raw || bucketRuntime(entry.avg_runtime ?? entry.value ?? 0);
    buckets[key] = (buckets[key] || 0) + (entry.count ?? entry.value ?? 1);
  }
  return RUNTIME_BUCKET_ORDER.filter((k) => buckets[k]).map((k) => ({ label: k, value: buckets[k] }));
}

/**
 * Sort purge candidates by any key, ascending or descending.
 * Returns a new array (does not mutate the original).
 */
export function sortPurgeCandidates(candidates, sortKey, sortDir) {
  if (!candidates?.length) return [];
  const copy = [...candidates];
  copy.sort((a, b) => {
    let av = a[sortKey], bv = b[sortKey];
    if (typeof av === "string") av = av.toLowerCase();
    if (typeof bv === "string") bv = bv.toLowerCase();
    if (av < bv) return sortDir === "asc" ? -1 : 1;
    if (av > bv) return sortDir === "asc" ? 1 : -1;
    return 0;
  });
  return copy;
}
