const MAX_RESULT_ITEMS = 100;

const GAP_HEADING_RE =
  /\b(gaps?|missing|not\s+in\s+(the\s+)?library|not\s+owned|not\s+here\s+yet|absent\s+from)\b/i;

function cleanText(value, max = 120) {
  return String(value || "").replace(/\s+/g, " ").trim().slice(0, max);
}

function stableResultItems(items) {
  return (Array.isArray(items) ? items : [])
    .filter((item) => item && (Number(item.tmdb_id) > 0 || Number(item.tvdb_id) > 0))
    .slice(0, MAX_RESULT_ITEMS);
}

export function lastMarkdownHeading(content) {
  const matches = [...String(content || "").matchAll(/^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$/gm)];
  return cleanText(matches.at(-1)?.[1] || "");
}

/** True when a result-list heading describes gaps / missing / not-owned titles. */
export function isGapResultHeading(heading = "") {
  return GAP_HEADING_RE.test(String(heading || ""));
}

/**
 * Harvest set for rail/grid icons.
 * Gap headings only keep cards that are not already in the library; if none remain,
 * returns an empty list so the UI can disable the control.
 */
export function harvestResultListItems(heading = "", items = []) {
  const source = Array.isArray(items) ? items : [];
  if (!isGapResultHeading(heading)) return source;
  return source.filter((item) => item && item.in_library !== true);
}

export function buildAgentRailPrompt({ heading = "", items = [] } = {}) {
  const rows = stableResultItems(items).map((item) => {
    const title = cleanText(item.title, 160);
    const year = Number(item.year) > 0 ? ` (${Number(item.year)})` : "";
    const ids = [
      Number(item.tmdb_id) > 0 ? `tmdb_id=${Number(item.tmdb_id)}` : "",
      Number(item.tvdb_id) > 0 ? `tvdb_id=${Number(item.tvdb_id)}` : "",
      item.media_type ? `media_type=${cleanText(item.media_type, 16)}` : "",
    ].filter(Boolean);
    return `- ${title}${year} [${ids.join(", ")}]`;
  });
  const label = cleanText(heading) || "these results";
  return [
    `Turn “${label}” into a curated list rail using the exact titles below.`,
    "Ask me for a name if you need one, then use the existing list tools to create the list and add these identities without substituting different matches:",
    ...rows,
  ].join("\n");
}

export async function materializeAgentResultList({
  heading = "",
  items = [],
  createList,
  addItem,
  now = new Date(),
} = {}) {
  const stableItems = stableResultItems(items);
  if (!stableItems.length) {
    throw new Error("These results do not have stable media identities to open as a grid.");
  }
  const label = cleanText(heading) || "Agent results";
  const timestamp = now.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
  });
  const list = await createList({
    name: `${label} · ${timestamp}`,
    description: "Saved from an agent result set for full library-grid browsing.",
    list_kind: "list",
  });
  for (const item of stableItems) {
    await addItem(list.id, {
      title: cleanText(item.title, 240) || "Untitled",
      media_type: item.media_type === "show" ? "show" : "movie",
      tmdb_id: Number(item.tmdb_id) > 0 ? Number(item.tmdb_id) : undefined,
      tvdb_id: Number(item.tvdb_id) > 0 ? Number(item.tvdb_id) : undefined,
      library_item_id: Number(item.library_item_id) > 0 ? Number(item.library_item_id) : undefined,
    });
  }
  return {
    list,
    added: stableItems.length,
    skipped: Math.max(0, (Array.isArray(items) ? items.length : 0) - stableItems.length),
  };
}

export function pageAgentListItems(items, { limit = 48, offset = 0 } = {}) {
  const source = Array.isArray(items) ? items : [];
  const start = Math.max(0, Number(offset) || 0);
  const pageSize = String(limit).toLowerCase() === "all"
    ? Math.max(1, source.length)
    : Math.max(1, Number(limit) || 48);
  return {
    items: source.slice(start, start + pageSize),
    total: source.length,
    hasPrevious: start > 0,
    hasNext: start + pageSize < source.length,
  };
}
