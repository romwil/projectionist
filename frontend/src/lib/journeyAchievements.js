/**
 * My Journey achievement catalog helpers.
 * Member-facing copy must never say "engagement".
 */

export const JOURNEY_TIERS = ["easy", "mid", "deep"];
export const JOURNEY_CATEGORIES = [
  { id: "watching", label: "Watching", ultimate: "journey-ultimate-watching" },
  { id: "taste", label: "Taste", ultimate: "journey-ultimate-taste" },
  { id: "scholar", label: "Scholar", ultimate: "journey-ultimate-scholar" },
  { id: "companion", label: "Companion", ultimate: "journey-ultimate-companion" },
  { id: "concierge", label: "Concierge", ultimate: "journey-ultimate-concierge" },
  { id: "enthusiast", label: "Enthusiast", ultimate: "journey-ultimate-enthusiast" },
  { id: "collection", label: "Collection craft", ultimate: "journey-ultimate-collection" },
];

/**
 * Static journey catalog — dozens of nodes spanning tiers, persona pathways, and secrets.
 * Runtime progress merges from /api/engagement/summary (internal) + earned badge slugs.
 */
export const JOURNEY_CATALOG = [
  // Watching
  { id: "watch-continue", slug: "watch-continue", name: "Pick up where you left off", description: "Open Continue Watching from Explore.", tier: "easy", category: "watching", hidden: false, youthSafe: true, prerequisites: [], personaId: null, hint: "Explore → Continue Watching" },
  { id: "watch-finish-1", slug: "watch-finish-1", name: "First curtain call", description: "Finish a title you started.", tier: "easy", category: "watching", hidden: false, youthSafe: true, prerequisites: ["watch-continue"], personaId: null },
  { id: "watch-streak-3", slug: "chat-streak-3", name: "Three-day chat streak", description: "Talk with the curator three days in a row.", tier: "mid", category: "watching", hidden: false, youthSafe: true, prerequisites: [], personaId: null },
  { id: "watch-for-you", slug: "watch-for-you", name: "Trust the weekly rail", description: "Open a title from For you this week.", tier: "easy", category: "watching", hidden: false, youthSafe: true, prerequisites: [], personaId: null },
  { id: "journey-ultimate-watching", slug: "journey-ultimate-watching", name: "Screen-side companion", description: "Ultimate Watching pathway badge.", tier: "deep", category: "watching", hidden: false, youthSafe: true, prerequisites: ["watch-continue", "watch-finish-1", "watch-for-you"], personaId: null, ultimate: true },

  // Taste
  { id: "taste-first-review", slug: "first-review", name: "First review", description: "You rated a title — taste starts here.", tier: "easy", category: "taste", hidden: false, youthSafe: true, prerequisites: [], personaId: null },
  { id: "taste-rate-5", slug: "rate-5", name: "Five stars of opinions", description: "Rated five titles. Your lens is sharpening.", tier: "mid", category: "taste", hidden: false, youthSafe: true, prerequisites: ["taste-first-review"], personaId: null },
  { id: "taste-genre", slug: "genre-explorer", name: "Genre explorer", description: "Touched three different genres in reviews.", tier: "mid", category: "taste", hidden: false, youthSafe: true, prerequisites: ["taste-first-review"], personaId: null },
  { id: "taste-weights", slug: "taste-weights", name: "Tune the dials", description: "Visit Settings → Taste and adjust a cluster weight.", tier: "mid", category: "taste", hidden: false, youthSafe: false, prerequisites: ["taste-first-review"], personaId: null },
  { id: "journey-ultimate-taste", slug: "journey-ultimate-taste", name: "House critic", description: "Ultimate Taste pathway badge.", tier: "deep", category: "taste", hidden: false, youthSafe: true, prerequisites: ["taste-first-review", "taste-rate-5", "taste-genre"], personaId: null, ultimate: true },

  // Scholar
  { id: "scholar-explainer", slug: "scholar-explainer", name: "Read the room notes", description: "Open an explainer on My Journey.", tier: "easy", category: "scholar", hidden: false, youthSafe: true, prerequisites: [], personaId: null },
  { id: "scholar-course", slug: "course-starter", name: "Course starter", description: "Began a curated cinema course.", tier: "mid", category: "scholar", hidden: false, youthSafe: true, prerequisites: ["scholar-explainer"], personaId: null },
  { id: "scholar-plot-lab", slug: "scholar-plot-lab", name: "Motif walker", description: "Open Plot Lab and browse a motif wall.", tier: "mid", category: "scholar", hidden: false, youthSafe: true, prerequisites: [], personaId: null },
  { id: "scholar-tags", slug: "scholar-tags", name: "Tag cartographer", description: "Search Tags for a keyword that opens a shelf.", tier: "easy", category: "scholar", hidden: false, youthSafe: true, prerequisites: [], personaId: null },
  { id: "journey-ultimate-scholar", slug: "journey-ultimate-scholar", name: "Cinema scholar", description: "Ultimate Scholar pathway badge.", tier: "deep", category: "scholar", hidden: false, youthSafe: true, prerequisites: ["scholar-explainer", "scholar-course", "scholar-plot-lab"], personaId: null, ultimate: true },

  // Companion (household / social)
  { id: "companion-recommend", slug: "companion-recommend", name: "Pass it on", description: "Recommend a title to someone in the household.", tier: "easy", category: "companion", hidden: false, youthSafe: true, prerequisites: [], personaId: null },
  { id: "companion-inbox", slug: "companion-inbox", name: "You've got mail", description: "Open the Inbox and read a notification.", tier: "easy", category: "companion", hidden: false, youthSafe: true, prerequisites: [], personaId: null },
  { id: "companion-family", slug: "family-picks", name: "Family picks starter", description: "Rated three age-friendly titles.", tier: "mid", category: "companion", hidden: false, youthSafe: true, prerequisites: [], personaId: null },
  { id: "journey-ultimate-companion", slug: "journey-ultimate-companion", name: "Household guide", description: "Ultimate Companion pathway badge.", tier: "deep", category: "companion", hidden: false, youthSafe: true, prerequisites: ["companion-recommend", "companion-inbox"], personaId: null, ultimate: true },

  // Concierge (chat / personas)
  { id: "concierge-ask", slug: "story-explorer", name: "Story explorer", description: "Asked the curator about titles.", tier: "easy", category: "concierge", hidden: false, youthSafe: true, prerequisites: [], personaId: null },
  { id: "concierge-persona-switch", slug: "concierge-persona-switch", name: "Try another voice", description: "Switch the active curator persona in Chat.", tier: "easy", category: "concierge", hidden: false, youthSafe: true, prerequisites: ["concierge-ask"], personaId: null },
  { id: "concierge-night-owl", slug: "concierge-night-owl", name: "Night-owl hour", description: "Chat with a night-leaning persona after dark.", tier: "mid", category: "concierge", hidden: false, youthSafe: false, prerequisites: ["concierge-persona-switch"], personaId: "night-owl" },
  { id: "concierge-warm", slug: "concierge-warm", name: "Warm welcome", description: "Start a conversation with a welcoming persona.", tier: "mid", category: "concierge", hidden: false, youthSafe: true, prerequisites: ["concierge-persona-switch"], personaId: "warm-host" },
  { id: "concierge-critic", slug: "concierge-critic", name: "Critic's corner", description: "Ask a sharper persona for a take on a title.", tier: "mid", category: "concierge", hidden: false, youthSafe: false, prerequisites: ["concierge-persona-switch"], personaId: "critic" },
  { id: "journey-ultimate-concierge", slug: "journey-ultimate-concierge", name: "Persona polyglot", description: "Ultimate Concierge pathway badge.", tier: "deep", category: "concierge", hidden: false, youthSafe: true, prerequisites: ["concierge-ask", "concierge-persona-switch"], personaId: null, ultimate: true },

  // Enthusiast
  { id: "enthusiast-search", slug: "enthusiast-search", name: "Search the shelves", description: "Run a Search query across your collection.", tier: "easy", category: "enthusiast", hidden: false, youthSafe: true, prerequisites: [], personaId: null },
  { id: "enthusiast-beyond", slug: "enthusiast-beyond", name: "Look beyond", description: "Search Beyond your collection for a missing title.", tier: "mid", category: "enthusiast", hidden: false, youthSafe: false, prerequisites: ["enthusiast-search"], personaId: null },
  { id: "enthusiast-watchlist", slug: "enthusiast-watchlist", name: "Pin it for later", description: "Add a title to your Watchlist.", tier: "easy", category: "enthusiast", hidden: false, youthSafe: true, prerequisites: [], personaId: null },
  { id: "enthusiast-surprise", slug: "enthusiast-surprise", name: "Surprise me", description: "Use a surprise / quick-pick flow from Chat.", tier: "mid", category: "enthusiast", hidden: false, youthSafe: true, prerequisites: ["concierge-ask"], personaId: null },
  { id: "journey-ultimate-enthusiast", slug: "journey-ultimate-enthusiast", name: "Shelf explorer", description: "Ultimate Enthusiast pathway badge.", tier: "deep", category: "enthusiast", hidden: false, youthSafe: true, prerequisites: ["enthusiast-search", "enthusiast-watchlist"], personaId: null, ultimate: true },

  // Collection craft
  { id: "collection-library", slug: "collection-library", name: "Save a reply", description: "Save a curator response to your Library.", tier: "easy", category: "collection", hidden: false, youthSafe: true, prerequisites: [], personaId: null },
  { id: "collection-lists", slug: "collection-lists", name: "Shelf builder", description: "Open Lists & playlists.", tier: "easy", category: "collection", hidden: false, youthSafe: true, prerequisites: [], personaId: null },
  { id: "collection-course-finish", slug: "collection-course-finish", name: "Syllabus graduate", description: "Complete a published cinema course.", tier: "deep", category: "collection", hidden: false, youthSafe: true, prerequisites: ["scholar-course"], personaId: null },
  { id: "journey-ultimate-collection", slug: "journey-ultimate-collection", name: "Collection craftmaster", description: "Ultimate Collection craft pathway badge.", tier: "deep", category: "collection", hidden: false, youthSafe: false, prerequisites: ["collection-library", "collection-lists"], personaId: null, ultimate: true },

  // Hidden easter eggs — real names only after unlock
  { id: "secret-konami", slug: "secret-konami", name: "Classic code", description: "A secret for those who know the classic code.", tier: "deep", category: "enthusiast", hidden: true, youthSafe: true, prerequisites: [], personaId: null, teaser: "Some awards stay silent until you earn them." },
  { id: "secret-reverse-name", slug: "secret-reverse-name", name: "Mirror greeting", description: "Say the curator's name backwards in chat.", tier: "mid", category: "concierge", hidden: true, youthSafe: true, prerequisites: [], personaId: null, teaser: "Try a mirror greeting." },
  { id: "secret-night-owl-23", slug: "secret-night-owl-23", name: "After the late show", description: "Visit Chat after 11pm local time.", tier: "mid", category: "watching", hidden: true, youthSafe: false, prerequisites: [], personaId: null, teaser: "The late show has its own badge." },
  { id: "secret-plot-lab-dense", slug: "secret-plot-lab-dense", name: "Wall of light", description: "Open a dense motif wall in Plot Lab.", tier: "deep", category: "scholar", hidden: true, youthSafe: true, prerequisites: ["scholar-plot-lab"], personaId: null, teaser: "When the wall fills in…" },
  { id: "secret-inbox-zero", slug: "secret-inbox-zero", name: "Clear the stack", description: "Clear every Inbox notification in one sitting.", tier: "mid", category: "companion", hidden: true, youthSafe: true, prerequisites: ["companion-inbox"], personaId: null, teaser: "Empty the stack." },
];

/** Guard: member-facing strings must not contain "engagement". */
export function assertNoEngagementCopy(text) {
  const value = String(text || "");
  if (/engagement/i.test(value)) {
    throw new Error(`Member-facing copy must not say engagement: ${value.slice(0, 80)}`);
  }
  return value;
}

export function filterCatalogForYouth(catalog = JOURNEY_CATALOG, isYouth = false) {
  if (!isYouth) return [...catalog];
  return catalog.filter((node) => node.youthSafe !== false);
}

export function earnedSlugSet(summary) {
  const set = new Set();
  for (const badge of summary?.badges || []) {
    if (badge?.slug) set.add(String(badge.slug));
    if (badge?.id) set.add(String(badge.id));
  }
  return set;
}

export function isNodeEarned(node, earned) {
  if (!node) return false;
  return earned.has(node.slug) || earned.has(node.id) || Boolean(node.earned);
}

export function prerequisitesMet(node, earned, catalog = JOURNEY_CATALOG) {
  const prereqs = node.prerequisites || [];
  if (!prereqs.length) return true;
  const byId = Object.fromEntries(catalog.map((n) => [n.id, n]));
  return prereqs.every((id) => {
    const prereq = byId[id];
    if (!prereq) return true;
    return isNodeEarned(prereq, earned);
  });
}

/**
 * Merge catalog with live summary into list rows.
 */
export function buildJourneyNodes(summary, { isYouth = false, catalog = JOURNEY_CATALOG } = {}) {
  const earned = earnedSlugSet(summary);
  const nodes = filterCatalogForYouth(catalog, isYouth).map((node) => {
    const unlocked = isNodeEarned(node, earned);
    const ready = prerequisitesMet(node, earned, catalog);
    const hiddenLocked = node.hidden && !unlocked;
    return {
      ...node,
      earned: unlocked,
      ready,
      locked: !unlocked && (!ready || node.hidden),
      displayName: hiddenLocked ? "???" : node.name,
      displayDescription: hiddenLocked
        ? node.teaser || "Hidden achievement — keep exploring."
        : node.description,
      progress: unlocked ? 1 : ready ? 0.35 : 0,
    };
  });
  return nodes;
}

export function journeyProgressSummary(nodes) {
  const earned = nodes.filter((n) => n.earned).length;
  const inProgress = nodes.filter((n) => !n.earned && n.ready && !n.hidden).length;
  const secretsFound = nodes.filter((n) => n.hidden && n.earned).length;
  const secretsTotal = nodes.filter((n) => n.hidden).length;
  return {
    earned,
    total: nodes.length,
    inProgress,
    secretsFound,
    secretsTotal,
  };
}

export function filterJourneyNodes(nodes, filter = "all") {
  if (filter === "earned") return nodes.filter((n) => n.earned);
  if (filter === "in-progress") return nodes.filter((n) => !n.earned && n.ready && !n.hidden);
  if (filter === "hidden") return nodes.filter((n) => n.hidden && n.earned);
  return nodes;
}

/** Group nodes by category for Civ-style tree columns. */
export function buildJourneyTree(nodes) {
  return JOURNEY_CATEGORIES.map((category) => {
    const column = nodes
      .filter((n) => n.category === category.id)
      .sort((a, b) => {
        const tierOrder = { easy: 0, mid: 1, deep: 2 };
        return (tierOrder[a.tier] || 0) - (tierOrder[b.tier] || 0) || a.name.localeCompare(b.name);
      });
    return { ...category, nodes: column };
  }).filter((col) => col.nodes.length);
}

export function personaPathways(nodes) {
  const byPersona = new Map();
  for (const node of nodes) {
    if (!node.personaId) continue;
    if (!byPersona.has(node.personaId)) byPersona.set(node.personaId, []);
    byPersona.get(node.personaId).push(node);
  }
  return [...byPersona.entries()].map(([personaId, pathwayNodes]) => ({
    personaId,
    nodes: pathwayNodes,
    completed: pathwayNodes.every((n) => n.earned),
  }));
}

export function memberFacingCopyOk(nodes) {
  for (const node of nodes) {
    assertNoEngagementCopy(node.displayName || node.name);
    assertNoEngagementCopy(node.displayDescription || node.description);
    assertNoEngagementCopy(node.teaser || "");
  }
  return true;
}
