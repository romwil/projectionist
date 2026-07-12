export function isAddableToRadarr(item) {
  return Boolean(!item?.in_library && item?.media_type === "movie" && item?.tmdb_id);
}

export function isAddableToSonarr(item) {
  return Boolean(!item?.in_library && item?.media_type === "show" && item?.tvdb_id);
}

export function isRequestableInSeerr(item) {
  return Boolean(
    !item?.in_library &&
      item?.tmdb_id &&
      (item?.media_type === "movie" || item?.media_type === "show"),
  );
}

export function usesSeerrRequestPath(features) {
  return Boolean(features?.features?.seerr_enabled && features?.request_path === "seerr");
}

export function requestPathFromFeatures(features) {
  return usesSeerrRequestPath(features) ? "seerr" : "arr";
}

export function serviceLabelForTarget(target) {
  if (target === "seerr") return "Seerr";
  if (target === "sonarr") return "Sonarr";
  return "Radarr";
}

export function actionForTarget(target) {
  if (target === "seerr") return "request_seerr";
  if (target === "sonarr") return "add_sonarr";
  return "add_radarr";
}

export function buildProposeActionBody(item, target) {
  if (target === "seerr") {
    return {
      action: "request_seerr",
      media_type: item.media_type,
      tmdb_id: item.tmdb_id,
      tvdb_id: item.tvdb_id,
      title: item.title,
    };
  }
  if (target === "sonarr") {
    return { action: "add_sonarr", tvdb_id: item.tvdb_id, title: item.title };
  }
  return { action: "add_radarr", tmdb_id: item.tmdb_id, title: item.title };
}

export function isAlreadyInArr(response) {
  return Boolean(response?.already_exists);
}

export function alreadyInArrMessage(response, { label, service }) {
  return response?.message || `"${label}" is already in ${service}.`;
}

export function groupAddableItems(items = [], { requestPath = "arr" } = {}) {
  if (requestPath === "seerr") {
    const seerr = items.filter(isRequestableInSeerr);
    return { radarr: [], sonarr: [], seerr };
  }
  return {
    radarr: items.filter(isAddableToRadarr),
    sonarr: items.filter(isAddableToSonarr),
    seerr: [],
  };
}

export function collectTitleCardItems(blocks = []) {
  const items = [];
  for (const block of blocks) {
    if (block?.type === "title_cards") {
      items.push(...(block.items || []));
    }
  }
  return items;
}

export function collectAddableFromMessage(message, options = {}) {
  if (!message || message.role !== "assistant") {
    return { radarr: [], sonarr: [], seerr: [] };
  }
  return groupAddableItems(collectTitleCardItems(message.blocks), options);
}

/** True when the latest assistant turn already hosts in-chat bulk confirm UI. */
export function lastAssistantHasTitleCards(messages = []) {
  const last = [...messages].reverse().find((message) => message.role === "assistant");
  return Boolean(last?.blocks?.some((block) => block.type === "title_cards"));
}

export function normalizePendingTokens(pendingTokens) {
  if (!Array.isArray(pendingTokens)) return [];
  return pendingTokens
    .map((entry) => {
      if (typeof entry === "string") {
        return { token: entry, action: "add_radarr" };
      }
      if (entry?.token) {
        return { token: entry.token, action: entry.action || "add_radarr" };
      }
      return null;
    })
    .filter(Boolean);
}

const TOKEN_ACTION_GROUPS = {
  add: new Set(["add_radarr", "add_sonarr", "request_seerr"]),
  remove: new Set(["remove_arr"]),
  plex: new Set(["create_plex_collection", "add_to_plex_collection"]),
};

export function summarizePendingTokenActions(entries = []) {
  const counts = { add: 0, remove: 0, plex: 0, other: 0 };
  for (const entry of entries) {
    const action = entry.action || "add_radarr";
    if (TOKEN_ACTION_GROUPS.add.has(action)) counts.add += 1;
    else if (TOKEN_ACTION_GROUPS.remove.has(action)) counts.remove += 1;
    else if (TOKEN_ACTION_GROUPS.plex.has(action)) counts.plex += 1;
    else counts.other += 1;
  }
  return counts;
}

export function tokenConfirmPrompt(count, entries = []) {
  const summary = summarizePendingTokenActions(entries);
  if (summary.remove > 0 && summary.add === 0 && summary.plex === 0) {
    const noun = summary.remove === 1 ? "removal" : "removals";
    return `Confirm all ${count} proposed ${noun}?`;
  }
  if (summary.add > 0 && summary.remove === 0 && summary.plex === 0) {
    const noun = summary.add === 1 ? "add" : "adds";
    return `Confirm all ${count} proposed ${noun}?`;
  }
  if (summary.plex > 0 && summary.add === 0 && summary.remove === 0) {
    const noun = summary.plex === 1 ? "Plex action" : "Plex actions";
    return `Confirm all ${count} proposed ${noun}?`;
  }
  return `Confirm all ${count} proposed actions?`;
}

export function tokenConfirmButtonLabel(count, entries = []) {
  const summary = summarizePendingTokenActions(entries);
  if (summary.remove > 0 && summary.add === 0 && summary.plex === 0) {
    return `Confirm all ${count} removals`;
  }
  if (summary.add > 0 && summary.remove === 0 && summary.plex === 0) {
    return `Confirm all ${count} adds`;
  }
  if (summary.plex > 0 && summary.add === 0 && summary.remove === 0) {
    return `Confirm all ${count} Plex actions`;
  }
  return `Confirm all ${count}`;
}

export function tokenConfirmSuccessMessage(count, entries = []) {
  const summary = summarizePendingTokenActions(entries);
  if (summary.remove > 0 && summary.add === 0 && summary.plex === 0) {
    return `Confirmed ${count} removal${count === 1 ? "" : "s"}.`;
  }
  if (summary.add > 0 && summary.remove === 0 && summary.plex === 0) {
    return `Confirmed ${count} add${count === 1 ? "" : "s"}.`;
  }
  return `Confirmed ${count} action${count === 1 ? "" : "s"}.`;
}

export function tokenConfirmFailureMessage(entries = []) {
  const summary = summarizePendingTokenActions(entries);
  if (summary.remove > 0 && summary.add === 0) {
    return "Could not confirm proposed removals.";
  }
  if (summary.add > 0 && summary.remove === 0) {
    return "Could not confirm proposed adds.";
  }
  return "Could not confirm proposed actions.";
}
