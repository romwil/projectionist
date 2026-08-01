/**
 * Phase D household social helpers — watch-party recommend flourishes,
 * saved-page share polish, Companion callback deep-links.
 */

export const RECOMMEND_INTENTS = Object.freeze(["recommend", "watch_party"]);

export const WATCH_PARTY_NOTE_CHIPS = Object.freeze([
  "Watch together tonight?",
  "Couch pick — join me?",
  "Thought this would be fun as a household watch",
]);

export function normalizeRecommendIntent(raw) {
  const value = String(raw || "").trim().toLowerCase();
  if (value === "watch_party" || value === "watch-party" || value === "watch together") {
    return "watch_party";
  }
  return "recommend";
}

export function recommendationIntent(item) {
  if (!item || typeof item !== "object") return "recommend";
  const fromPayload = item.payload?.intent ?? item.payload?.recommend_intent;
  if (fromPayload) return normalizeRecommendIntent(fromPayload);
  return normalizeRecommendIntent(item.intent);
}

export function isWatchPartyRecommendation(item) {
  return recommendationIntent(item) === "watch_party";
}

export function defaultWatchPartyNote(title) {
  const clean = String(title || "").trim();
  return clean ? `Watch together tonight? ${clean}` : WATCH_PARTY_NOTE_CHIPS[0];
}

export function recommendModalCopy(intent) {
  if (normalizeRecommendIntent(intent) === "watch_party") {
    return {
      eyebrow: "Watch together",
      sendLabel: "Invite to watch",
      sendingLabel: "Inviting…",
      notePlaceholder: "Tonight on the couch…",
      noteHint: "Optional invite note",
    };
  }
  return {
    eyebrow: "Recommend to…",
    sendLabel: "Send recommendation",
    sendingLabel: "Sending…",
    notePlaceholder: "Thought you'd love this…",
    noteHint: "Optional note",
  };
}

export function digInRecommendCtaLabel(intent = "recommend") {
  return normalizeRecommendIntent(intent) === "watch_party" ? "Watch together" : "Recommend";
}

/**
 * Build dig-in path + Chat about this seed fields from callback memory metadata.
 * Returns null when no title identity is present.
 */
export function callbackTitleDeepLink(note) {
  const meta = note?.metadata && typeof note.metadata === "object" ? note.metadata : note || {};
  const title = String(meta.title || note?.title || "").trim();
  if (!title && meta.tmdb_id == null && !meta.rating_key && !meta.plex_rating_key) {
    return null;
  }
  const mediaType = meta.media_type === "show" ? "show" : "movie";
  const ratingKey = String(meta.rating_key || meta.plex_rating_key || "").trim();
  const tmdbId = meta.tmdb_id != null && Number.isFinite(Number(meta.tmdb_id)) ? Number(meta.tmdb_id) : null;
  const tvdbId = meta.tvdb_id != null && Number.isFinite(Number(meta.tvdb_id)) ? Number(meta.tvdb_id) : null;
  const year = meta.year != null && Number.isFinite(Number(meta.year)) ? Number(meta.year) : null;
  const item = {
    title: title || "this title",
    media_type: mediaType,
    tmdb_id: tmdbId,
    tvdb_id: tvdbId,
    rating_key: ratingKey || undefined,
    plex_rating_key: ratingKey || undefined,
    year,
    in_library: Boolean(ratingKey || meta.in_library),
    poster_url: meta.poster_url || "",
  };
  return item;
}

export function libraryShareFlash(action) {
  if (action === "copy") return "Private household library link copied.";
  if (action === "save") return "Saved to your private library.";
  if (action === "share-household") return "Shared with household.";
  if (action === "more") return "Shared.";
  if (action === "pdf") return "Print view opened.";
  if (String(action || "").startsWith("export:")) return "Export opened.";
  return "";
}

export function librarySharePrivacyNote() {
  return "Links stay on your Projectionist account — household members only, never a public page.";
}
