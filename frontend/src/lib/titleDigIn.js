import { titleDetailPath } from "./titleLinks.js";

/**
 * Parse an in-app title detail href into a card-shaped item for TitleDetailLink.
 * @param {string | null | undefined} href
 */
export function titleItemFromHref(href) {
  const raw = String(href || "").trim();
  if (!raw.startsWith("/title/")) return null;
  const [pathPart, query = ""] = raw.split("?");
  const match = /^\/title\/(movie|show)\/(.+)$/.exec(pathPart);
  if (!match) return null;
  const mediaType = match[1];
  let itemId = match[2];
  try {
    itemId = decodeURIComponent(itemId);
  } catch {
    // keep raw
  }
  const idType = new URLSearchParams(query).get("id_type") || "tmdb";
  if (idType === "rating_key") {
    return { media_type: mediaType, rating_key: itemId, in_library: true };
  }
  if (idType === "tvdb") {
    return { media_type: mediaType, tvdb_id: Number(itemId) || itemId };
  }
  const tmdbId = Number(itemId);
  return {
    media_type: mediaType,
    tmdb_id: Number.isFinite(tmdbId) ? tmdbId : itemId,
  };
}

/** True when href should open the in-app title overlay / full page. */
export function isTitleDetailHref(href) {
  return Boolean(titleItemFromHref(href));
}

function escapeRegExp(value) {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * Inject markdown title links for known cards so chat prose can dig in.
 * Prefers **Title** / list-item leads; skips titles already linked.
 *
 * @param {string} content
 * @param {Array<Record<string, unknown>>} titleRefs
 */
export function linkifyKnownTitles(content, titleRefs = []) {
  let out = String(content || "");
  if (!out || !titleRefs?.length) return out;

  const refs = [];
  const seen = new Set();
  for (const ref of titleRefs) {
    const title = String(ref?.title || "").trim();
    const path = titleDetailPath(ref);
    if (!title || title.length < 2 || !path) continue;
    const key = `${title.toLowerCase()}|${path}`;
    if (seen.has(key)) continue;
    seen.add(key);
    refs.push({ title, path, year: ref?.year });
  }
  refs.sort((a, b) => b.title.length - a.title.length);

  for (const { title, path } of refs) {
    if (out.includes(`](${path}`) || out.includes(`](${path.split("?")[0]}`)) {
      continue;
    }
    const bold = `**${title}**`;
    if (out.includes(bold)) {
      out = out.split(bold).join(`**[${title}](${path})**`);
      continue;
    }
    const italic = `*${title}*`;
    if (out.includes(italic) && !out.includes(`**${title}**`)) {
      out = out.split(italic).join(`*[${title}](${path})*`);
      continue;
    }
    const listRe = new RegExp(`(^|\\n)([-*]\\s+)${escapeRegExp(title)}(?=\\b|[\\s([{]|$)`, "g");
    if (listRe.test(out)) {
      listRe.lastIndex = 0;
      out = out.replace(listRe, `$1$2[${title}](${path})`);
    }
  }
  return out;
}

/** Collect linkable title refs from chat message blocks (title_cards, etc.). */
export function titleRefsFromBlocks(blocks = []) {
  const refs = [];
  for (const block of blocks) {
    if (block?.type === "title_cards" && Array.isArray(block.items)) {
      for (const item of block.items) {
        if (item?.title && titleDetailPath(item)) refs.push(item);
      }
    }
    if (block?.type === "double_feature" && block.payload) {
      for (const key of ["title_a", "title_b"]) {
        const item = block.payload[key];
        if (item?.title && titleDetailPath(item)) refs.push(item);
      }
    }
    if (block?.type === "action_prompt" && block.action === "open_viewport") {
      for (const item of block.payload?.items || []) {
        if (item?.title && titleDetailPath(item)) refs.push(item);
      }
    }
  }
  return refs;
}
