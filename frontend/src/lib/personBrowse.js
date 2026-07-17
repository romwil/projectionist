/** Person page role filter + library-owned percentage helpers. */

export function creditRoleBucket(item) {
  const job = String(item?.job || "").trim().toLowerCase();
  const department = String(item?.department || "").trim().toLowerCase();
  if (
    job === "director" ||
    department === "directing" ||
    department === "directors"
  ) {
    return "director";
  }
  if (
    department === "acting" ||
    job === "actor" ||
    job === "actress" ||
    String(item?.character || "").trim()
  ) {
    return "cast";
  }
  if (department === "directing" || department.includes("direct")) {
    return "director";
  }
  return "other";
}

export function filterPersonTitles(titles, roleFilter) {
  const list = Array.isArray(titles) ? titles : [];
  const filter = String(roleFilter || "all").toLowerCase();
  if (filter === "all" || !filter) return list;
  return list.filter((item) => creditRoleBucket(item) === filter);
}

/** Human-readable label for a single credit entry (character preferred). */
export function creditLabel(item) {
  const character = String(item?.character || "").trim();
  if (character) return character;
  const job = String(item?.job || "").trim();
  if (job) return job;
  const department = String(item?.department || "").trim();
  return department || "";
}

/** Stable identity for a media piece so multiple credits collapse to one card. */
export function personTitleKey(item) {
  const type = String(item?.media_type || "").trim().toLowerCase();
  if (item?.tmdb_id) return `${type}:tmdb:${item.tmdb_id}`;
  const ratingKey = item?.rating_key ?? item?.plex_rating_key;
  if (ratingKey) return `${type}:rk:${String(ratingKey).trim()}`;
  return `${type}:title:${String(item?.title || "").trim().toLowerCase()}:${item?.year || ""}`;
}

/**
 * Collapse per-credit rows into one entry per media piece, aggregating the
 * distinct credit labels (e.g. "Tugg Speedman", "Director", "Producer").
 * Preserves first-seen order and back-fills poster/year from later rows.
 */
export function groupPersonTitles(titles) {
  const list = Array.isArray(titles) ? titles : [];
  const groups = new Map();
  const order = [];
  for (const item of list) {
    if (!item) continue;
    const key = personTitleKey(item);
    let group = groups.get(key);
    if (!group) {
      group = { ...item, credits: [] };
      groups.set(key, group);
      order.push(key);
    } else {
      if (!group.poster_url && item.poster_url) group.poster_url = item.poster_url;
      if (!group.year && item.year) group.year = item.year;
      if (!group.rating_key && item.rating_key) group.rating_key = item.rating_key;
      if (!group.tmdb_id && item.tmdb_id) group.tmdb_id = item.tmdb_id;
    }
    const label = creditLabel(item);
    if (label && !group.credits.includes(label)) {
      group.credits.push(label);
    }
  }
  return order.map((key) => groups.get(key));
}

export function libraryOwnedPercent(person) {
  const owned = Number(
    person?.in_library_count ??
      (Array.isArray(person?.titles) ? person.titles.length : NaN),
  );
  const total = Number(person?.filmography_total);
  if (!Number.isFinite(owned) || owned < 0) return null;
  if (!Number.isFinite(total) || total <= 0) return null;
  const pct = Math.min(100, Math.round((owned / total) * 100));
  return { owned, total, pct, label: `${pct}% of filmography in library` };
}
