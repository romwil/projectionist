/** Persona-voiced “What’s on tonight” habit copy (no extra LLM round). */

/**
 * @param {{
 *   curatorName?: string,
 *   presetId?: string|null,
 *   channels?: Array<{ nowTitle?: string, name?: string, number?: number|null }>,
 *   isYouth?: boolean,
 *   ready?: boolean,
 * }} opts
 * @returns {string}
 */
export function tonightOneLiner({
  curatorName = "Curator",
  presetId = null,
  channels = [],
  isYouth = false,
  ready = false,
} = {}) {
  const name = String(curatorName || "Curator").trim() || "Curator";
  const preset = String(presetId || "").trim().toLowerCase();
  const airing = (Array.isArray(channels) ? channels : []).filter((c) =>
    String(c?.nowTitle || "").trim(),
  );
  const sample = String(airing[0]?.nowTitle || "").trim();
  const count = airing.length;

  if (isYouth) {
    if (!ready || count === 0) {
      return `${name} is waiting for something age-friendly to start on Live.`;
    }
    if (sample) {
      return `${name} spotted “${sample}” on now — tap in when you’re ready.`;
    }
    return `${name} found ${count} station${count === 1 ? "" : "s"} you can watch tonight.`;
  }

  if (!ready || count === 0) {
    if (preset.includes("enthusiast") || preset.includes("scout")) {
      return `${name} is warming the dial — stations will light up once something’s on.`;
    }
    if (preset.includes("companion") || preset.includes("night")) {
      return `${name} is holding the couch open — nothing’s airing yet.`;
    }
    return `${name} says Live is on, but the guide is quiet right now.`;
  }

  if (preset.includes("enthusiast") || preset.includes("scout")) {
    return sample
      ? `${name} would tune “${sample}” first — ${count} station${count === 1 ? "" : "s"} humming.`
      : `${name} sees ${count} station${count === 1 ? "" : "s"} live tonight.`;
  }
  if (preset.includes("scholar") || preset.includes("critic")) {
    return sample
      ? `${name} notes “${sample}” is on the air — dig in or skim the rest.`
      : `${name} has ${count} live station${count === 1 ? "" : "s"} worth a glance.`;
  }
  if (preset.includes("archivist") || preset.includes("librarian")) {
    return `${name}: ${count} on now${sample ? ` — lead with “${sample}”` : ""}.`;
  }
  if (preset.includes("companion") || preset.includes("night")) {
    return sample
      ? `${name} thinks “${sample}” is an easy tonight pick — Watch here or Plex.`
      : `${name} lined up ${count} live option${count === 1 ? "" : "s"} for tonight.`;
  }
  // Default film-buff / custom
  return sample
    ? `${name} has “${sample}” on now — and ${count} station${count === 1 ? "" : "s"} total.`
    : `${name} found ${count} station${count === 1 ? "" : "s"} on the air tonight.`;
}

/**
 * Habit surface chrome copy — youth-safe wording when needed.
 * @param {{ isYouth?: boolean }} [opts]
 */
export function tonightHabitChrome({ isYouth = false } = {}) {
  if (isYouth) {
    return {
      eyebrow: "Live for you",
      title: "What’s on for you tonight",
      meta: "Age-friendly stations only — Watch here or ask an adult for Plex Live TV.",
      empty: "Nothing age-friendly is airing yet. Check back later, or Ask for a Pick for me.",
      digInHint: "Open a station to Watch here.",
    };
  }
  return {
    eyebrow: "Tonight",
    title: "What’s on tonight",
    meta: "Persona-sized glance at Live — dig in for Watch here or Also in Plex.",
    empty: "Live is on, but nothing is airing yet. Once something’s on, it’ll show up here.",
    digInHint: "Pick a station to dig in — Watch here or Also in Plex.",
  };
}

/**
 * Soft ready spotlight copy when Live just became ready.
 * @param {{ isYouth?: boolean, channelCount?: number, curatorName?: string }} [opts]
 */
export function tonightReadySpotlight({
  isYouth = false,
  channelCount = 0,
  curatorName = "Curator",
} = {}) {
  const name = String(curatorName || "Curator").trim() || "Curator";
  const n = Number(channelCount) || 0;
  if (isYouth) {
    return {
      title: "Live stations are ready",
      body: n
        ? `${name} can show age-friendly channels when something’s on (${n} station${n === 1 ? "" : "s"} total).`
        : `${name} will surface age-friendly Live picks when something’s on.`,
    };
  }
  return {
    title: "Live Channels is ready",
    body: n
      ? `${name} says your household stations are on the air (${n}). Dig into What’s on tonight — Watch here or Plex.`
      : `${name} says Live is ready — dig into What’s on tonight when something’s airing.`,
  };
}
