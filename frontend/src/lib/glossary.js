/**
 * Shared living-room glossary for Admin SectionHelp + HELP copy.
 * Labels stay in lockstep with `liveChannelsCopy.LIVE_ADMIN_GLOSSARY`.
 */

import { LIVE_ADMIN_GLOSSARY, liveAdminLabel } from "./liveChannelsCopy.js";

/** Craft-facing term → short help blurb (shown in SectionHelp popovers). */
export const GLOSSARY_HELP = {
  Broadcast: "The part of Projectionist that keeps your channels on the air.",
  "Between-show breaks": "Short clips that fill gaps between programs on every channel.",
  "Gap fill (minutes)": "How long the broadcast may stretch a break to cover a scheduling gap.",
  "Play order": "Shuffle mixes the pool; Sequential walks titles in list order.",
  "Station source": "Where a channel’s titles come from — a show, a collection, a mood, or suggestions.",
  "Breaks ready": "Between-show breaks are ready and attached to your channels.",
  "Restarting the broadcast": "The broadcast is restarting — Live sessions may briefly drop.",
  "Plex channel map": "How Projectionist channels appear as Plex Live TV channels.",
  Setup: "Connection, breaks, and Plex — the path before channels go on the air.",
};

/** Shown in SectionHelp when a known term has a label but no dedicated blurb. */
export const GLOSSARY_FALLBACK_HELP = "More about this setting.";

/**
 * Resolve a glossary entry from an ops key or craft label.
 * @param {string} keyOrLabel
 * @returns {{ key: string, label: string, help: string|null, known: boolean }}
 */
export function glossaryEntry(keyOrLabel) {
  const raw = String(keyOrLabel || "").trim();
  if (!raw) return { key: "", label: "", help: null, known: false };
  const mapped = Object.prototype.hasOwnProperty.call(LIVE_ADMIN_GLOSSARY, raw)
    ? LIVE_ADMIN_GLOSSARY[raw]
    : null;
  const label = mapped || liveAdminLabel(raw);
  const help = GLOSSARY_HELP[label] || GLOSSARY_HELP[raw] || null;
  const known =
    mapped != null ||
    Object.values(LIVE_ADMIN_GLOSSARY).includes(raw) ||
    Object.prototype.hasOwnProperty.call(GLOSSARY_HELP, raw) ||
    Object.prototype.hasOwnProperty.call(GLOSSARY_HELP, label);
  return { key: raw, label: known ? label : "", help, known };
}

/**
 * Plain-text body for SectionHelp when using glossaryKey (no children override).
 * Known label-only entries get {@link GLOSSARY_FALLBACK_HELP}; unknown keys → null.
 * @param {string|null|undefined} glossaryKey
 * @returns {string|null}
 */
export function sectionHelpPlainBody(glossaryKey) {
  if (!glossaryKey) return null;
  const entry = glossaryEntry(glossaryKey);
  if (!entry.known) return null;
  return entry.help || GLOSSARY_FALLBACK_HELP;
}

/** All craft labels currently documented (for tests / HELP sync checks). */
export function glossaryLabels() {
  const fromMap = Object.values(LIVE_ADMIN_GLOSSARY);
  const fromHelp = Object.keys(GLOSSARY_HELP);
  return [...new Set([...fromMap, ...fromHelp])].sort();
}
