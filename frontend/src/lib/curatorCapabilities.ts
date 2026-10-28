/**
 * Owner-facing curator capability summary — product copy maintained in code.
 * Describes what the agent can help with without exposing tool names, schemas,
 * or system-prompt wiring (see Admin → Persona).
 */

/** @typedef {{ id: string, label: string, detail?: string }} CuratorCapability */

/** @type {CuratorCapability[]} */
export const CURATOR_CAPABILITIES = [
  {
    id: "library-search",
    label: "Search and browse your indexed library",
    detail: "Grounded answers from titles you own — not invented catalog entries.",
  },
  {
    id: "recommend",
    label: "Recommend unwatched picks, hidden gems, and shelf gaps",
    detail: "Tonight picks, double features, follow-ups, and taste-aware suggestions.",
  },
  {
    id: "research",
    label: "Research titles, filmmakers, and studios with cited sources",
    detail: "Filmographies, comparisons, and durable household knowledge when you dig deep.",
  },
  {
    id: "memory",
    label: "Remember taste, callbacks, and household notes",
    detail: "Private per-member memory stays scoped — never mixed across accounts.",
  },
  {
    id: "reviews",
    label: "Collect ratings and reviews (half-stars supported)",
    detail: "Batch rate-from-recent flows and optional Plex rating sync when configured.",
  },
  {
    id: "lists",
    label: "Manage watchlist pins and curated lists",
    detail: "Pin, curate, and critique watchlists in chat with your confirmation.",
  },
  {
    id: "acquire",
    label: "Find titles outside your library and walk acquisition paths",
    detail: "Discover via TMDB, then propose Seerr requests or Radarr/Sonarr adds — nothing ships until you confirm.",
  },
  {
    id: "bad-media",
    label: "Replace bad downloads without banning a title",
    detail: "Ask to re-fetch a corrupted file; distinct from permanent removal or import exclusions.",
  },
  {
    id: "village",
    label: "Consult sibling curators for specialty takes",
    detail: "Scholar (depth), Companion (mood), Concierge (find→request), Enthusiast (tonight energy) — quoted handoffs, not silent merges.",
  },
  {
    id: "patterns",
    label: "Analyze watch patterns and TV progress",
    detail: "Episode-level play semantics and continue-watching context from your index.",
  },
  {
    id: "collections",
    label: "Suggest Plex collections and movie-night shelves",
    detail: "Ephemeral collection helpers when Plex collections are enabled — always confirm first.",
  },
  {
    id: "explore",
    label: "Explore tags & genres and plot patterns",
    detail: "Browse rails, engagement stats, and structured library overviews.",
  },
];

/**
 * Plain-language capability lines for Admin Persona (and tests).
 * @returns {string[]}
 */
export function curatorCapabilityLabels() {
  return CURATOR_CAPABILITIES.map((item) => item.label);
}

/**
 * Short intro blurb for the Admin Persona capabilities panel.
 * @returns {string}
 */
export function curatorCapabilitiesIntro() {
  return (
    "Your curator runs against your indexed library with confirmation gates for anything " +
    "that changes Radarr, Sonarr, Seerr, or Plex. Tune voice and tone below — " +
    "capability wiring is maintained by Projectionist, not editable here."
  );
}
