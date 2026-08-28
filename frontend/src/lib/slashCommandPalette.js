import { SLASH_COMMANDS } from "./slashCommands.js";

export const SLASH_COMMAND_ENTRIES = [
  { command: "help", summary: "Show the slash command list" },
  { command: "stats", summary: "Library item counts and last sync time" },
  { command: "sync", summary: "Start a Plex library index job" },
  { command: "rate", summary: "Rate recent titles or `/rate Title Name`" },
  { command: "purge", summary: "Summarize top drive-space purge candidates" },
  {
    command: "collections",
    summary: "List Plex movie and TV collections",
    requiresPlexCollections: true,
  },
];

function visibleEntries(plexCollectionsEnabled) {
  return SLASH_COMMAND_ENTRIES.filter(
    (entry) => !entry.requiresPlexCollections || plexCollectionsEnabled,
  ).filter((entry) => SLASH_COMMANDS.includes(entry.command));
}

export function filterSlashCommandPalette(input, { plexCollectionsEnabled = false } = {}) {
  const text = String(input || "");
  if (!text.startsWith("/")) return [];
  const body = text.slice(1);
  const spaceIndex = body.indexOf(" ");
  const prefix = (spaceIndex === -1 ? body : body.slice(0, spaceIndex)).toLowerCase();
  const entries = visibleEntries(plexCollectionsEnabled);
  if (spaceIndex >= 0) {
    const exact = entries.find((entry) => entry.command === prefix);
    return exact ? [exact] : [];
  }
  if (!prefix) return entries;
  return entries.filter((entry) => entry.command.startsWith(prefix));
}

export function formatSlashCommandInsert(command, existingArgs = "") {
  const args = String(existingArgs || "").trim();
  return args ? `/${command} ${args}` : `/${command} `;
}

export function shouldShowSlashCommandPalette(input) {
  const text = String(input || "");
  if (!text.startsWith("/")) return false;
  return !String(text.slice(1)).includes(" ");
}
