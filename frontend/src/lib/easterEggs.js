const KONAMI_SEQUENCE = [
  "ArrowUp",
  "ArrowUp",
  "ArrowDown",
  "ArrowDown",
  "ArrowLeft",
  "ArrowRight",
  "ArrowLeft",
  "ArrowRight",
  "b",
  "a",
];

const EASTER_EGG_STORAGE_KEY = "projectionist.easter-egg-fired";

export function easterEggAlreadyFired() {
  try {
    return sessionStorage.getItem(EASTER_EGG_STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

export function markEasterEggFired() {
  try {
    sessionStorage.setItem(EASTER_EGG_STORAGE_KEY, "1");
  } catch {
    // sessionStorage unavailable
  }
}

export function createKonamiTracker(onTrigger) {
  let index = 0;
  return function handleKonamiKey(event) {
    if (easterEggAlreadyFired()) return false;
    const key = event.key.length === 1 ? event.key.toLowerCase() : event.key;
    if (key === KONAMI_SEQUENCE[index]) {
      index += 1;
      if (index >= KONAMI_SEQUENCE.length) {
        index = 0;
        markEasterEggFired();
        onTrigger?.("konami");
        return true;
      }
      return false;
    }
    index = key === KONAMI_SEQUENCE[0] ? 1 : 0;
    return false;
  };
}

export function isReversedCuratorName(text, curatorName) {
  const trimmed = String(text || "").trim();
  const name = String(curatorName || "").trim();
  if (!trimmed || !name || trimmed.length !== name.length) return false;
  const reversed = name.split("").reverse().join("");
  return trimmed.toLowerCase() === reversed.toLowerCase();
}

export function easterEggResponse(kind, curatorName = "Curator") {
  if (kind === "konami") {
    return [
      `**${curatorName}** — you found the secret combo.`,
      "",
      "Cheat code accepted: infinite taste, zero buffer, one perfect pick queued for tonight.",
      "",
      "*(This was a one-time easter egg — back to curating.)*",
    ].join("\n");
  }
  if (kind === "reversed_name") {
    return [
      `**${curatorName}** — speaking backwards now, are we?`,
      "",
      `You typed my name in reverse. I'll still recommend forward.`,
      "",
      "*(One-time mirror mode disengaged.)*",
    ].join("\n");
  }
  return "";
}

export const TITLE_CARD_DRAG_MIME = "application/x-curatorx-title-card";

export function setTitleCardDragData(event, item) {
  if (!event?.dataTransfer || !item) return;
  event.dataTransfer.setData(TITLE_CARD_DRAG_MIME, JSON.stringify(item));
  event.dataTransfer.effectAllowed = "copy";
}

export function readTitleCardDragData(event) {
  const raw = event?.dataTransfer?.getData(TITLE_CARD_DRAG_MIME);
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

export function resolveDockDropTarget(
  item,
  { radarrConnected = false, sonarrConnected = false } = {},
) {
  if (!item || item.in_library) return null;
  if (item.media_type === "movie" && item.tmdb_id && radarrConnected) return "radarr";
  if (item.media_type === "show" && item.tvdb_id && sonarrConnected) return "sonarr";
  return null;
}

export function canDragTitleCardToDock(item, connections) {
  return Boolean(resolveDockDropTarget(item, connections));
}

export function statusDockDropHint({ radarrConnected = false, sonarrConnected = false } = {}) {
  if (radarrConnected && sonarrConnected) {
    return "Drop a movie or show card here to queue in Radarr or Sonarr";
  }
  if (radarrConnected) {
    return "Drop a movie card here to queue in Radarr";
  }
  if (sonarrConnected) {
    return "Drop a show card here to queue in Sonarr";
  }
  return "";
}
