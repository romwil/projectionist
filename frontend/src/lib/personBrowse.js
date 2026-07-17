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
