/**
 * Living-room copy + Admin Live Channels glossary helpers (persona UX Phase 1).
 * Keep Tunarr / operator jargon out of household empty states; Admin may
 * mention Tunarr in help text only.
 */

/** User-facing empty / warming states for `/live`. */
export function liveUserEmptyCopy({ featureOn, featureReady, guideReady } = {}) {
  if (!featureOn) {
    return {
      eyebrow: "Live Channels",
      title: "Not on the air yet",
      body: "Ask the household owner to enable Live Channels in Admin.",
      ctaLabel: "Back to chat",
      ctaTo: "chat",
      testId: "live-empty-disabled",
    };
  }
  if (!featureReady && !guideReady) {
    return {
      eyebrow: "Live Channels",
      title: "Channels are warming up",
      body: "TV isn’t ready yet. Stations appear here once the household owner finishes Setup in Admin.",
      ctaLabel: "Open Admin",
      ctaTo: "admin",
      testId: "live-empty-warming",
    };
  }
  return null;
}

/** Guide panel empty copy — never bare “Tunarr” for members. */
export function liveGuideEmptyCopy(reason) {
  if (reason === "tunarr_unreachable") {
    return {
      title: "Guide is warming up",
      body: "TV isn’t ready yet. The owner can check Setup under Live Channels in Admin.",
    };
  }
  return {
    title: "Guide is warming up",
    body: "No stations yet.",
  };
}

/** Soften HLS / stream errors for the living room. */
export function formatLiveStreamError(data) {
  const detail = String(data?.details || "Stream error");
  const code = data?.response?.code;
  if (code === 401 || code === 403) {
    return "Sign in again to watch Live Channels.";
  }
  if (code === 502 || code === 503 || code === 504) {
    return "Channels are still warming up — try again in a few seconds.";
  }
  if (code && code >= 400) {
    return `Stream unavailable (${detail}, HTTP ${code}).`;
  }
  if (detail === "manifestLoadError" || detail === "levelLoadError") {
    return "Could not load this channel’s stream. Warming may still be in progress — try Watch again.";
  }
  if (detail === "fragLoadError") {
    return "Video segments failed to load. Try another channel or Watch again.";
  }
  return detail;
}

/** Admin glossary: ops label → craft-facing label. */
export const LIVE_ADMIN_GLOSSARY = {
  "Broadcast engine": "TV engine",
  "Filler programming paths": "Between-show breaks",
  "Pad flex max": "Gap fill (minutes)",
  Programming: "Play order",
  Recipe: "Station source",
  "Continuity ready": "Breaks ready",
  "Remounting Tunarr": "Restarting TV engine",
  "Plex Tunarr map": "Plex channel map",
  "Broadcast engine running": "TV engine running",
  "Broadcast engine unreachable": "TV engine unreachable",
  "Broadcast healthy": "TV healthy",
  Installation: "Setup",
};

export function liveAdminLabel(current) {
  const key = String(current || "").trim();
  return LIVE_ADMIN_GLOSSARY[key] || key;
}

/**
 * Compact one-line health status for the Stations strip.
 * @param {object|null|undefined} status
 */
export function liveHealthSentence(status) {
  if (!status) {
    return "Status not loaded yet — hit Refresh after you connect.";
  }
  const engineUp = Boolean(status.broadcast?.sidecar_up);
  const stations = Number(status.channel_count ?? 0);
  const airing = Array.isArray(status.airing) ? status.airing.length : 0;
  const parts = [
    engineUp ? "TV engine running" : "TV engine unreachable",
    `${stations} station${stations === 1 ? "" : "s"}`,
  ];
  if (airing > 0) parts.push(`${airing} airing now`);
  if (status.last_publish_at) {
    parts.push(`Last lineup publish ${status.last_publish_at}`);
  } else {
    parts.push("No lineup published yet");
  }
  return parts.join(" · ");
}

/**
 * Stable Setup step numbers for the pre-launch journey.
 * Connection is unlabeled as a numbered step in the plan (story order 1),
 * then Ready check → engine (if orch) → breaks → create → Plex.
 */
export function liveSetupStepNumbers({ dockerOrchestration = false } = {}) {
  let n = 1;
  const steps = {
    connection: null, // labeled "Connection" without a shifting Step N
    ready: n++,
  };
  if (dockerOrchestration) {
    steps.engine = n++;
  } else {
    steps.engine = null;
  }
  steps.breaks = n++;
  steps.create = n++;
  steps.plex = n++;
  return steps;
}

/** Create-station mode switch ids. */
export const CREATE_STATION_MODES = [
  { id: "custom", label: "Custom" },
  { id: "collection", label: "From collection" },
  { id: "starters", label: "Starter pack" },
];

/**
 * Soft onboarding tip when libraries look healthy but Live isn’t enabled yet.
 */
export function liveOnboardingTip({
  liveEnabled = false,
  libraryMapped = false,
  syncHealthy = false,
} = {}) {
  if (liveEnabled) return null;
  if (!libraryMapped && !syncHealthy) return null;
  return {
    title: "Put your library on the air",
    body: "Live Channels turns titles you already own into stations for Plex Live TV and Projectionist Watch.",
    ctaLabel: "Open Live Channels",
    ctaTo: "/admin/live-channels",
    testId: "live-onboarding-tip",
  };
}
