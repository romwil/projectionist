/**
 * Chat-from-rail seed helpers: compact URL payloads, sessionStorage posters,
 * and merging curated library cards into the assistant turn.
 */

export const RAIL_SEED_STORAGE_KEY = "curatorx:chat_rail_seed";
export const CHAT_FROM_RAIL_PACK_PARAM = "rail_pack";
export const CHAT_FROM_RAIL_ID_PARAM = "rail_id";

const MAX_RAIL_ITEMS = 8;
const MAX_WHY_CHARS = 160;

/** @param {unknown} value */
function trimStr(value, max = 200) {
  return String(value || "")
    .trim()
    .slice(0, max);
}

/**
 * Compact identity + why for URL transport (no poster URLs).
 * @param {Record<string, unknown>} item
 */
export function compactRailItem(item) {
  if (!item || typeof item !== "object") return null;
  const title = trimStr(item.title, 120);
  if (!title) return null;
  const why = trimStr(item.why || item.recommendation_reason, MAX_WHY_CHARS);
  const mediaType = trimStr(item.media_type, 16).toLowerCase();
  const out = { t: title };
  if (item.id != null && Number.isFinite(Number(item.id))) out.id = Number(item.id);
  const rk = trimStr(item.rating_key || item.plex_rating_key, 64);
  if (rk) out.rk = rk;
  if (item.year != null && Number.isFinite(Number(item.year))) out.y = Number(item.year);
  if (mediaType === "movie" || mediaType === "show") out.m = mediaType;
  if (why) out.w = why;
  if (item.tmdb_id != null && Number.isFinite(Number(item.tmdb_id))) out.tm = Number(item.tmdb_id);
  if (item.tvdb_id != null && Number.isFinite(Number(item.tvdb_id))) out.tv = Number(item.tvdb_id);
  return out;
}

/** Expand a compact rail pack entry back to a card-ish shape. */
export function expandRailItem(compact) {
  if (!compact || typeof compact !== "object") return null;
  const title = trimStr(compact.t || compact.title, 120);
  if (!title) return null;
  const why = trimStr(compact.w || compact.why || compact.recommendation_reason, MAX_WHY_CHARS);
  const ratingKey = trimStr(compact.rk || compact.rating_key || compact.plex_rating_key, 64);
  const mediaType = trimStr(compact.m || compact.media_type, 16).toLowerCase() || "movie";
  const id = compact.id != null && Number.isFinite(Number(compact.id)) ? Number(compact.id) : undefined;
  return {
    id,
    title,
    year: compact.y ?? compact.year ?? undefined,
    media_type: mediaType === "show" ? "show" : "movie",
    rating_key: ratingKey || undefined,
    tmdb_id: compact.tm ?? compact.tmdb_id ?? undefined,
    tvdb_id: compact.tv ?? compact.tvdb_id ?? undefined,
    why: why || undefined,
    recommendation_reason: why || undefined,
    poster_url: compact.poster_url || "",
    in_library: Boolean(compact.in_library ?? (Boolean(ratingKey) || id != null)),
  };
}

/** @param {unknown[]} items */
export function compactRailItems(items) {
  return (Array.isArray(items) ? items : [])
    .map((item) => compactRailItem(item))
    .filter(Boolean)
    .slice(0, MAX_RAIL_ITEMS);
}

export function encodeRailPack(items) {
  const compact = compactRailItems(items);
  if (!compact.length) return "";
  try {
    const json = JSON.stringify(compact);
    if (typeof btoa === "function") {
      return btoa(unescape(encodeURIComponent(json)))
        .replace(/\+/g, "-")
        .replace(/\//g, "_")
        .replace(/=+$/g, "");
    }
    return encodeURIComponent(json);
  } catch {
    return "";
  }
}

export function decodeRailPack(raw) {
  const value = String(raw || "").trim();
  if (!value) return [];
  try {
    let json = value;
    if (!value.startsWith("[") && !value.startsWith("%5B")) {
      const padded = value.replace(/-/g, "+").replace(/_/g, "/");
      const pad = padded.length % 4 === 0 ? "" : "=".repeat(4 - (padded.length % 4));
      if (typeof atob === "function") {
        json = decodeURIComponent(escape(atob(padded + pad)));
      }
    } else {
      json = decodeURIComponent(value);
    }
    const parsed = JSON.parse(json);
    if (!Array.isArray(parsed)) return [];
    return parsed.map((entry) => expandRailItem(entry)).filter(Boolean);
  } catch {
    return [];
  }
}

/**
 * Stash full rail items (including posters) for the next chat-from-rail turn.
 * @param {{ railTitle?: string, railId?: string, items?: unknown[] }} rail
 */
export function stashRailSeed(rail) {
  if (typeof sessionStorage === "undefined") return;
  try {
    const items = (Array.isArray(rail?.items) ? rail.items : [])
      .slice(0, MAX_RAIL_ITEMS)
      .map((item) => {
        const base = expandRailItem({
          ...compactRailItem(item),
          poster_url: item?.poster_url || item?.thumb || "",
          in_library: item?.in_library,
        });
        return base
          ? {
              ...base,
              poster_url: String(item?.poster_url || item?.thumb || base.poster_url || ""),
              genres: Array.isArray(item?.genres) ? item.genres : [],
              backdrop_url: item?.backdrop_url || item?.art || "",
            }
          : null;
      })
      .filter(Boolean);
    if (!items.length) return;
    sessionStorage.setItem(
      RAIL_SEED_STORAGE_KEY,
      JSON.stringify({
        railTitle: trimStr(rail?.railTitle || rail?.title, 120),
        railId: trimStr(rail?.railId || rail?.id, 64),
        items,
        stashedAt: Date.now(),
      }),
    );
  } catch {
    // Ignore quota / private-mode failures — URL pack still carries identities.
  }
}

/** Read and clear the stashed rail seed (if fresh). */
export function takeRailSeed({ maxAgeMs = 5 * 60 * 1000 } = {}) {
  if (typeof sessionStorage === "undefined") return null;
  try {
    const raw = sessionStorage.getItem(RAIL_SEED_STORAGE_KEY);
    if (!raw) return null;
    sessionStorage.removeItem(RAIL_SEED_STORAGE_KEY);
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return null;
    const age = Date.now() - Number(parsed.stashedAt || 0);
    if (!Number.isFinite(age) || age < 0 || age > maxAgeMs) return null;
    const items = Array.isArray(parsed.items)
      ? parsed.items.map((item) => expandRailItem(item)).filter(Boolean)
      : [];
    if (!items.length) return null;
    return {
      railTitle: trimStr(parsed.railTitle, 120),
      railId: trimStr(parsed.railId, 64),
      items,
    };
  } catch {
    return null;
  }
}

/** Map curated rail items to TitleCard-ready objects. */
export function railItemsToTitleCards(items) {
  return (Array.isArray(items) ? items : [])
    .map((item) => {
      const card = expandRailItem(item);
      if (!card) return null;
      const why = trimStr(item?.why || item?.recommendation_reason || card.why, 280);
      return {
        ...item,
        ...card,
        why: why || undefined,
        recommendation_reason: why || card.recommendation_reason || "",
        in_library: true,
        poster_url: item?.poster_url || card.poster_url || "",
      };
    })
    .filter(Boolean);
}

/**
 * Prefer curated in-library rail posters over agent TMDB / Add cards.
 * @param {Record<string, unknown> | null | undefined} message
 * @param {unknown[]} seedItems
 */
export function mergeRailSeedCards(message, seedItems) {
  const cards = railItemsToTitleCards(seedItems);
  if (!cards.length) return message;
  const blocks = Array.isArray(message?.blocks) ? message.blocks.map((b) => ({ ...b })) : [];
  const titleCardsBlock = { type: "title_cards", items: cards };
  const existingIdx = blocks.findIndex((block) => block?.type === "title_cards");
  if (existingIdx >= 0) {
    const existing = Array.isArray(blocks[existingIdx].items) ? blocks[existingIdx].items : [];
    const mostlyExternal =
      existing.length === 0 ||
      existing.filter((card) => card?.in_library).length < Math.ceil(existing.length / 2);
    if (mostlyExternal) {
      blocks[existingIdx] = titleCardsBlock;
    } else {
      // Keep agent library cards but ensure seed reasons land on matching titles.
      const byKey = new Map();
      for (const card of cards) {
        const key =
          card.rating_key ||
          (card.id != null ? `id:${card.id}` : null) ||
          `${card.media_type}:${String(card.title || "").toLowerCase()}:${card.year || ""}`;
        byKey.set(key, card);
      }
      blocks[existingIdx] = {
        type: "title_cards",
        items: existing.map((card) => {
          const key =
            card?.rating_key ||
            (card?.id != null ? `id:${card.id}` : null) ||
            `${card?.media_type}:${String(card?.title || "").toLowerCase()}:${card?.year || ""}`;
          const seed = byKey.get(key);
          if (!seed) return card;
          return {
            ...card,
            recommendation_reason: seed.recommendation_reason || card.recommendation_reason,
            why: seed.why || card.why,
            in_library: true,
          };
        }),
      };
    }
  } else {
    const textIdx = blocks.findIndex((block) => block?.type === "text");
    if (textIdx >= 0) blocks.splice(textIdx + 1, 0, titleCardsBlock);
    else blocks.push(titleCardsBlock);
  }
  return { ...(message || {}), role: message?.role || "assistant", blocks };
}

/**
 * Build the agent-facing prompt body listing stable ids + why per title.
 * @param {{ railTitle: string, items: ReturnType<typeof expandRailItem>[], focusTitle?: string, focusWhy?: string }} opts
 */
export function buildRailChatPrompt({ railTitle, items, focusTitle = "", focusWhy = "" } = {}) {
  const title = trimStr(railTitle, 120) || "this rail";
  const focus = trimStr(focusTitle, 120);
  const list = (Array.isArray(items) ? items : []).filter((item) => item?.title);

  if (focus) {
    const match =
      list.find((item) => String(item.title).toLowerCase() === focus.toLowerCase()) || null;
    const why = trimStr(focusWhy || match?.why || match?.recommendation_reason, 280);
    const idBits = [];
    if (match?.id != null) idBits.push(`library_id=${match.id}`);
    if (match?.rating_key) idBits.push(`rating_key=${match.rating_key}`);
    if (match?.year) idBits.push(String(match.year));
    if (match?.media_type) idBits.push(String(match.media_type));
    const idBit = idBits.length ? ` (${idBits.join(", ")})` : "";
    const whyBit = why ? ` The curator said: "${why}"` : "";
    return (
      `Let's talk about "${focus}"${idBit} from my "${title}" picks.${whyBit} ` +
      `This title is already in my library — look it up with search_library / query_library ` +
      `using the library id or rating_key (or exact title + year). Do not search TMDB or show Add/Radarr cards for it. ` +
      `Use the curator why as recommendation_reason. What should I know, and what else fits that vibe in my library?`
    );
  }

  const lines = list.map((item, index) => {
    const bits = [];
    if (item.id != null) bits.push(`library_id=${item.id}`);
    if (item.rating_key) bits.push(`rating_key=${item.rating_key}`);
    if (item.year) bits.push(String(item.year));
    if (item.media_type) bits.push(String(item.media_type));
    const why = trimStr(item.why || item.recommendation_reason, MAX_WHY_CHARS);
    const whyBit = why ? ` — why: ${why}` : "";
    const idBit = bits.length ? ` (${bits.join(", ")})` : "";
    return `${index + 1}. "${item.title}"${idBit}${whyBit}`;
  });
  const listBlock = lines.length ? `\nPicks:\n${lines.join("\n")}\n` : " ";
  return (
    `I want to chat about my "${title}" picks.${listBlock}` +
    `These are curated titles already in my library. Use search_library or query_library with each ` +
    `library_id / rating_key / exact title+year. Present these same titles as title cards and set ` +
    `recommendation_reason from each why. Do NOT search TMDB or invent Add/Radarr replacements for these picks. ` +
    `Help me choose what to watch and expand on those reasons.`
  );
}
