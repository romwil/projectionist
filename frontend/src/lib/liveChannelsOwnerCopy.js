/**
 * Owner-facing Live Channels language (1.37.27 native redesign).
 *
 * Owners think in channels, a lineup, what's on, and going on air — not in the
 * scheduler / guide-feed / container plumbing underneath. Everything here is
 * pure so it can be unit-tested and reused by the Admin Live studio.
 */

const SENTENCE_START = /(^|[.!?]\s+|\n)$/;

function withCase(before, phrase) {
  if (!SENTENCE_START.test(before)) return phrase;
  return phrase.charAt(0).toUpperCase() + phrase.slice(1);
}

// Ordered: specific phrases first so generic ones do not eat them.
const OWNER_TEXT_RULES = [
  [/chrisbenincasa\/tunarr:[\w.-]+/gi, "the broadcast engine"],
  [/Tunarr\s+XMLTV(\s+URL)?/gi, "channel guide$1"],
  [/\bXMLTV\s+guide\b/gi, "channel guide"],
  [/\bXMLTV\b/gi, "guide feed"],
  [/\bTunarr\s+Live\s+TV\b/gi, "Projectionist Live TV"],
  [/\bTunarr\s+tuner\b/gi, "Projectionist tuner"],
  [/\bTunarr\s+URL(\s+or\s+managed\s+Docker)?\b/gi, "broadcast address"],
  [/\bhost\.docker\.internal\b/gi, "the host"],
  [/\bDocker\s+orchestration\b/gi, "Automatic engine start"],
  [/\bDocker\s+(?:container|image|socket)s?\b/gi, "container host"],
  [/\bmanaged\s+Docker\b/gi, "managed start"],
  [/\bDocker\b/g, "container host"],
  [/\b(to|from|on|at|in|into|of) Tunarr\b(?!\s+(?:channels?|lineups?|stations?|Live|XMLTV|URL|tuner))/gi, "$1 the broadcast"],
  [/\bTunarr\s+(channels?|lineups?|stations?)\b/gi, "Projectionist $1"],
  [/\bTunarr(?:'s|’s)?\b/gi, "broadcast engine"],
  [/\bTV engine\b/gi, "broadcast"],
  [/\bStation(s?)\b/g, "Channel$1"],
  [/\bstation(s?)\b/g, "channel$1"],
];

/**
 * Rewrite operator vocabulary in a server-provided string into Projectionist
 * words. Defensive: API messages may still mention the engine underneath.
 */
export function ownerLiveText(value) {
  const text = String(value ?? "");
  if (!text) return "";
  let out = text;
  for (const [pattern, replacement] of OWNER_TEXT_RULES) {
    out = out.replace(pattern, (match, ...args) => {
      const offset = args[args.length - 2];
      const before = typeof offset === "number" ? out.slice(0, offset) : "";
      // Preserve capture groups ($1) used by the replacement templates.
      const groups = args.slice(0, -2).filter((g) => typeof g === "string" || g === undefined);
      const phrase = replacement.replace(/\$(\d)/g, (_, n) => groups[Number(n) - 1] ?? "");
      return withCase(before, phrase);
    });
  }
  return out.replace(/broadcast engine engine/gi, "broadcast engine");
}

/** Operator words that must not appear in owner-facing Live copy. */
export const LIVE_OWNER_JARGON = /tunarr|xmltv|docker|chrisbenincasa|hdhr|\bpms\b|meili/i;

/** The four ways to start a channel — each maps to one publish API. */
export const CHANNEL_KINDS = [
  {
    id: "show",
    title: "A show, nonstop",
    blurb: "Pick a series from your library. Every episode, in order or shuffled.",
  },
  {
    id: "collection",
    title: "A collection or list",
    blurb: "Turn a Plex collection or one of your Projectionist lists into a channel.",
  },
  {
    id: "mood",
    title: "A mood or taste",
    blurb: "Midnight mysteries, 70s action, family night — built from what you already own.",
  },
  {
    id: "suggest",
    title: "Suggest some for me",
    blurb: "Projectionist proposes a few channels from your library. Keep the ones you like.",
  },
];

/** Mood sources, in owner words (API ids stay motif / taste_cluster / youth). */
export const MOOD_SOURCES = [
  { id: "motif", label: "A story mood" },
  { id: "taste_cluster", label: "Your taste" },
  { id: "youth", label: "Family-safe" },
];

export const CREATE_STEPS = [
  { id: "pick", label: "What’s on it" },
  { id: "shape", label: "Make it yours" },
  { id: "launch", label: "Go on air" },
];

/** The creator skips "Make it yours" when Projectionist suggests the lineup. */
export function createStepsFor(kind) {
  if (kind === "suggest") {
    return [CREATE_STEPS[0], CREATE_STEPS[2]];
  }
  return CREATE_STEPS;
}

/** Owner-facing summary line for the review step. */
export function channelSummaryLine({ kind, name, number, programmingMode, mediaScope, pickTitle }) {
  const bits = [];
  if (number) bits.push(`Channel ${number}`);
  bits.push(name || pickTitle || "New channel");
  if (kind !== "suggest") {
    bits.push(programmingMode === "shuffle" ? "shuffled" : "in order");
  }
  if (mediaScope === "tv") bits.push("TV only");
  else if (mediaScope === "movies") bits.push("movies only");
  return bits.join(" · ");
}

/**
 * One honest state for the whole page.
 *
 * keys: off | loading | empty | ready_to_launch | on_air | attention
 * `warming`/`stale` come from the SWR status cache — never claim a problem
 * while the first real probe is still running.
 */
export function liveStationState({
  enabled = false,
  status = null,
  engineProgress = null,
  launching = false,
} = {}) {
  if (!enabled) {
    return { key: "off", tone: "muted", title: "Live is off", detail: "Turn Live on to start building channels." };
  }
  if (launching) {
    return {
      key: "launching",
      tone: "info",
      title: "Going on air…",
      detail: "Starting the broadcast and adding your channels to Plex Live TV.",
    };
  }
  if (!status || status.warming) {
    return {
      key: "loading",
      tone: "info",
      title: "Checking on your channels…",
      detail: "Projectionist is looking at what’s on and whether Plex can see it.",
    };
  }
  const channels = Number(status.channel_count ?? 0);
  const engineUp = Boolean(
    status.broadcast?.sidecar_up || engineProgress?.ready || engineProgress?.http_ready,
  );
  if (channels === 0) {
    return {
      key: "empty",
      tone: "muted",
      title: "No channels yet",
      detail: "Create your first channel — it takes about a minute.",
    };
  }
  if (!engineUp) {
    return {
      key: "ready_to_launch",
      tone: "warn",
      title: `${channels} channel${channels === 1 ? " is" : "s are"} built but off the air`,
      detail: "Start broadcasting to put them back on the lineup.",
    };
  }
  const plex = status.guide_index?.plex_livetv || {};
  const expected = Number(plex.expected);
  const mapped = Number(plex.mapped);
  const plexKnown = Number.isFinite(expected) && expected > 0;
  const plexOk = plex.mapping_ok ?? (plexKnown && mapped >= expected);
  if (status.last_error || (plexKnown && !plexOk)) {
    return {
      key: "attention",
      tone: "warn",
      title: "On the air — Plex needs a nudge",
      detail: plexKnown
        ? `Plex sees ${Number.isFinite(mapped) ? mapped : 0} of ${expected} channels.`
        : "The last update hit a snag.",
    };
  }
  return {
    key: "on_air",
    tone: "ok",
    title: `${channels} channel${channels === 1 ? "" : "s"} on the air`,
    detail: plexKnown
      ? `Plex Live TV sees all ${expected}.`
      : "Watch in Projectionist Live, or in Plex Live TV.",
  };
}

/**
 * Plain-language readiness rows for the launch step, from preflight checks.
 * Hard failures block; soft ones are reminders.
 */
const CHECK_LABELS = {
  plex_reachable: "Plex is connected",
  plex_pass: "Plex Pass (needed for Live TV in Plex)",
  tunarr_url: "Broadcast engine is reachable",
  docker_orchestration: "Projectionist can start the broadcast for you",
  disk_space: "Enough free disk space",
  gpu: "Hardware video acceleration (optional)",
};

export function launchReadinessRows(preflight) {
  const checks = Array.isArray(preflight?.checks) ? preflight.checks : [];
  return checks.map((check) => ({
    id: String(check.id || check.label || ""),
    ok: Boolean(check.ok),
    soft: Boolean(check.soft),
    label: CHECK_LABELS[check.id] || ownerLiveText(check.label),
    message: ownerLiveText(check.message),
  }));
}

export function launchBlockers(preflight) {
  return launchReadinessRows(preflight).filter((row) => !row.ok && !row.soft);
}

/** Ordered phases shown while launching. */
export const LAUNCH_PHASES = [
  { id: "check", label: "Checking your setup" },
  { id: "engine", label: "Warming up the broadcast" },
  { id: "lineup", label: "Building the lineup" },
  { id: "plex", label: "Adding to Plex Live TV" },
];

/** Did a runPublishJob result represent success? */
export function publishSucceeded(result) {
  if (!result) return false;
  if (result.phase === "error") return false;
  if (result.ok === false) return false;
  if (Number(result.count_errors || 0) > 0) return false;
  return true;
}
