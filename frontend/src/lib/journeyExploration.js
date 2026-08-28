/**
 * My Journey exploration helpers — people rails, insights, chat deep-links.
 */

import {
  exploreCastPath,
  exploreDecadePath,
  exploreDirectorsPath,
  exploreGenrePath,
  personPath,
} from "./browseLinks.js";
import { chatFromRailHref } from "./backNav.js";

export const JOURNEY_EYEBROW = "Your cinema map";
export const JOURNEY_HERO_LEDE =
  "Directors, craft, and threads grounded in your collection — explore who shaped what you watch.";

export const YOUTH_JOURNEY_EYEBROW = "Your cinema shelf";
export const YOUTH_JOURNEY_HERO_LEDE =
  "Curated paths and short notes from your curator — no scores, just stories.";

/** @param {{ name?: string, role?: string, count?: number }} person */
export function personShelfLabel(person) {
  const name = String(person?.name || "").trim();
  const count = Number(person?.count) || 0;
  if (!name) return "";
  if (count > 0) return `${count} in your shelf`;
  return "In your library";
}

/** @param {{ name?: string, role?: string }} person */
export function personExploreHref(person) {
  const name = String(person?.name || "").trim();
  if (!name) return null;
  const role = String(person?.role || "director").toLowerCase();
  if (role === "director") return exploreDirectorsPath(name);
  const tmdbId = person?.tmdb_person_id;
  if (tmdbId != null) return personPath(tmdbId);
  return exploreCastPath(name);
}

/** @param {{ name?: string, role?: string, count?: number }} person */
export function personChatHref(person) {
  const name = String(person?.name || "").trim();
  if (!name) return null;
  const role = String(person?.role || "director");
  const count = Number(person?.count) || 0;
  const shelfNote =
    count > 0
      ? `Explore ${name}'s work in your shelf (${count} title${count === 1 ? "" : "s"}).`
      : `Explore ${name}'s work in your shelf.`;
  return chatFromRailHref(
    { railTitle: `My Journey · ${name}`, railId: `person-${role}-${name.slice(0, 40)}` },
    { title: name, why: shelfNote },
  );
}

/** @param {{ kind?: string, label?: string, count?: number, note?: string }} insight */
export function insightChatHref(insight) {
  const label = String(insight?.label || "").trim();
  if (!label) return null;
  const kind = String(insight?.kind || "thread");
  const note =
    String(insight?.note || "").trim() ||
    `Talk about ${label} threads in your collection.`;
  return chatFromRailHref(
    { railTitle: `My Journey · ${label}`, railId: `insight-${kind}-${label.slice(0, 40)}` },
    { title: label, why: note },
  );
}

/** @param {{ kind?: string, label?: string }} insight */
export function insightBrowseHref(insight) {
  const label = String(insight?.label || "").trim();
  if (!label) return null;
  const kind = String(insight?.kind || "");
  if (kind === "genre") return exploreGenrePath(label);
  if (kind === "era") return exploreDecadePath(label);
  return null;
}

/** @param {Record<string, unknown> | null | undefined} data */
export function hasExplorationContent(data) {
  if (!data) return false;
  const people = data.people || {};
  const rails = ["directors", "cinematographers", "composers"];
  if (rails.some((key) => Array.isArray(people[key]) && people[key].length)) return true;
  if (Array.isArray(data.insights) && data.insights.length) return true;
  if (Array.isArray(data.courses) && data.courses.length) return true;
  if (Array.isArray(data.explainers) && data.explainers.length) return true;
  return false;
}
