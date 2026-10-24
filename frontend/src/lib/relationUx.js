export const RELATION_FILTERS = [
  { id: "all", label: "All connections" },
  { id: "collection", label: "Same collection" },
  { id: "shared_crew", label: "Shared cast & crew" },
  { id: "directed_by", label: "Same director" },
  { id: "written_by", label: "Same writer" },
  { id: "neighbor", label: "Similar plot" },
  { id: "surprising", label: "Surprisingly similar" },
];

import { displayRecommendationReason } from "./recommendationReason.js";

/** Absence of shelf labels is not a story connection. */
const ABSENCE_REASON =
  /almost no shared|nothing in common|barely overlap|partial shelf|some shelf overlap|no shared genre|no shared keyword|credit labels|credit cards/i;

export function surprisingPlotLink(why = {}) {
  const link = String(why?.plot_link || "").trim();
  if (!link || ABSENCE_REASON.test(link)) return "";
  return link;
}

export function hasSpecificStoryLink(why = {}) {
  return Boolean(surprisingPlotLink(why));
}

const COSINE_ONLY_REASON = /plot kinship|plot space/i;

export function isSurprisingRelation(edge) {
  if (edge?.relation !== "neighbor") return false;
  const flavor = String(edge?.why?.surprise_flavor || "").trim();
  if (!flavor || ABSENCE_REASON.test(flavor) || COSINE_ONLY_REASON.test(flavor)) return false;
  return hasSpecificStoryLink(edge?.why);
}

export function neighborIdentity(item) {
  const peer = item?.peer && typeof item.peer === "object" ? item.peer : item;
  const ratingKey = String(peer?.rating_key || "").trim();
  if (ratingKey) return `rk:${ratingKey}`;
  if (peer?.tmdb_id) return `tmdb:${peer.tmdb_id}`;
  if (peer?.tvdb_id) return `tvdb:${peer.tvdb_id}`;
  const id = peer?.library_item_id || peer?.neighbor_id || peer?.to_id || peer?.id;
  return id ? `id:${id}` : "";
}

/** Surprising must not serialize the same ordered peer set as Similar. */
export function surprisingPlotNeighbors(plotEdges) {
  const similar = Array.isArray(plotEdges) ? plotEdges : [];
  const surprising = similar.filter((edge) => isSurprisingRelation(edge));
  const similarIds = similar.map((edge) => neighborIdentity(edge)).filter(Boolean);
  const surprisingIds = surprising.map((edge) => neighborIdentity(edge)).filter(Boolean);
  if (similarIds.length && surprisingIds.join("\0") === similarIds.join("\0")) {
    return [];
  }
  return surprising;
}

function relationItemKey(item) {
  if (!item) return "";
  return String(
    item.library_item_id ||
      item.id ||
      item.tmdb_id ||
      item.rating_key ||
      `${item.media_type || ""}:${item.title || ""}`,
  );
}

export function appendRelationBreadcrumb(breadcrumbs, item) {
  if (!item) return Array.isArray(breadcrumbs) ? breadcrumbs : [];
  const current = Array.isArray(breadcrumbs) ? breadcrumbs : [];
  const key = relationItemKey(item);
  const existingIndex = current.findIndex((entry) => relationItemKey(entry) === key);
  if (existingIndex >= 0) return current.slice(0, existingIndex + 1);
  return [...current, item].slice(-3);
}

export function relationWhyCopy(why = {}) {
  const sentence = displayRecommendationReason(why?.explanation?.sentence);
  if (sentence) {
    return { label: sentence, detail: "" };
  }
  const label = displayRecommendationReason(why.label);
  const link = surprisingPlotLink(why);
  const sharedGenres = Array.isArray(why.shared_genres)
    ? why.shared_genres.map((genre) => String(genre).trim()).filter(Boolean)
    : [];
  const sharedKeywords = Array.isArray(why.shared_keywords)
    ? why.shared_keywords.map((keyword) => String(keyword).trim()).filter(Boolean)
    : [];
  if (link) {
    const shelf = String(why.shelf_note || "").trim();
    if (shelf) {
      return {
        label: link,
        detail: shelf.endsWith(".") ? shelf : `${shelf}.`,
      };
    }
    if (sharedKeywords.length) {
      return {
        label: link,
        detail: `Shared keywords: ${sharedKeywords.slice(0, 3).join(", ")}.`,
      };
    }
    return { label: link, detail: "" };
  }
  const surprise = String(why.surprise_flavor || "").trim();
  // Do not turn "no shared labels" into the recommendation.
  if (surprise && !ABSENCE_REASON.test(surprise)) {
    return { label, detail: surprise.endsWith(".") ? surprise : `${surprise}.` };
  }
  let detail = "";
  if (sharedKeywords.length && !label.toLowerCase().includes("keyword")) {
    detail = `Shared keywords: ${sharedKeywords.slice(0, 3).join(", ")}.`;
  } else if (sharedGenres.length && !label.toLowerCase().includes("shared genres")) {
    detail = `Shared genres: ${sharedGenres.slice(0, 3).join(", ")}.`;
  }
  return {
    label,
    detail,
  };
}

export function filterRelationEdges(edges, filter = "all") {
  const list = Array.isArray(edges) ? edges : [];
  if (!filter || filter === "all") return list;
  if (filter === "surprising") {
    return list.filter((edge) => isSurprisingRelation(edge));
  }
  return list.filter((edge) => edge?.relation === filter);
}

export function relationSeedFromItem(item) {
  if (!item) return null;
  const mediaType = item.media_type === "show" ? "show" : "movie";
  if (item.tmdb_id) {
    return { ...item, media_type: mediaType, item_id: String(item.tmdb_id), id_type: "tmdb" };
  }
  const ratingKey = item.rating_key || item.plex_rating_key;
  if (ratingKey) {
    return { ...item, media_type: mediaType, item_id: String(ratingKey), id_type: "rating_key" };
  }
  if (mediaType === "show" && item.tvdb_id) {
    return { ...item, media_type: mediaType, item_id: String(item.tvdb_id), id_type: "tvdb" };
  }
  return null;
}

export function relatedTitlesPath(item) {
  const seed = relationSeedFromItem(item);
  if (!seed) return "/explore/related";
  const params = new URLSearchParams({
    media_type: seed.media_type,
    item_id: seed.item_id,
    id_type: seed.id_type,
  });
  const title = String(seed.title || "").trim();
  if (title) params.set("title", title);
  if (seed.year) params.set("year", String(seed.year));
  return `/explore/related?${params}`;
}

export function relationSeedFromSearchParams(searchParams) {
  const itemId = String(searchParams?.get("item_id") || "").trim();
  if (!itemId) return null;
  return {
    item_id: itemId,
    id_type: String(searchParams.get("id_type") || "tmdb"),
    media_type: searchParams.get("media_type") === "show" ? "show" : "movie",
    title: String(searchParams.get("title") || "Selected title"),
    year: Number(searchParams.get("year")) || null,
  };
}

export function relationPeerSeed(edge) {
  return relationSeedFromItem(edge?.peer || edge);
}
