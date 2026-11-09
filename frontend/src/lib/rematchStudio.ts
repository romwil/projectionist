import type {JsonObject, JsParam} from "../api/types";
/** Copy helpers for Admin → Libraries Rematch studio and Repair the miss (v1.36.2). */

export const INVESTIGATORS_NOTE =
  "FileBot, Plex Match, and Gracenote are not investigators. Compare Plex GUID, Radarr TMDB, and the folder.";

export const GOOD_NEWS_NOT_DOWNLOAD = "Good News is a watchlist or gap arrival — never “download complete.”";

export const PATH_CONFLICT_HINT =
  "Path conflicts: use Repair the miss below — Open Rematch studio scrolls to Rematch studio; fix identity in Plex or Radarr, then Retry. Retry alone won’t clear a path conflict.";

export function tmdbMovieUrl(id: unknown) {
  const n = Number(id);
  if (!Number.isFinite(n) || n <= 0) return "";
  return `https://www.themoviedb.org/movie/${Math.trunc(n)}`;
}

export function radarrRegisterHasPathConflicts(job: JsParam) {
  const items = Array.isArray(job?.items) ? job.items : [];
  return items.some((row: JsParam) => String(row?.outcome || "").toLowerCase() === "path_conflict");
}

export function looksLikeJsonDump(text: string) {
  const cleaned = String(text || "").trim();
  if (!cleaned) return false;
  if (cleaned.includes("formattedMessagePlaceholderValues") || cleaned.includes('"errorCode"')) {
    return true;
  }
  if (cleaned.startsWith("{") || cleaned.startsWith("[")) return true;
  if (cleaned.toLowerCase().startsWith("http ") && cleaned.includes("{")) return true;
  return false;
}

export function humanizeMiss(text: string) {
  const cleaned = String(text || "").trim();
  if (!cleaned) return "This title did not land. Rematch, skip, or retry.";
  if (looksLikeJsonDump(cleaned)) {
    return "Radarr rejected this title — the folder or identity does not match.";
  }
  const first = cleaned.split("\n", 1)[0].trim();
  return first.length > 240 ? `${first.slice(0, 237)}...` : first;
}

export function identityKindLabel(kind: string, sameTitle: JsParam) {
  const key = String(kind || "").toLowerCase();
  if (key === "path_conflict") {
    return sameTitle ? "Same title, path conflict" : "Path conflict";
  }
  if (key === "title_collision") return "Same title, different identity";
  if (key === "needs_plex_id") return "Needs a Plex rematch";
  if (key === "already") return "Already in Radarr";
  return "Needs attention";
}

export function plexColumnCopy(row: JsParam) {
  const plex = row?.plex || {};
  const title = plex.title || row?.title || "Plex";
  if (plex.tmdb_id) return `${title} · tmdb ${plex.tmdb_id}`;
  return `${title} · no TMDB id`;
}

export function radarrColumnCopy(row: JsParam) {
  const radarr = row?.radarr;
  if (!radarr) return "Not in Radarr";
  const title = radarr.title || "Radarr";
  if (radarr.tmdb_id) return `${title} · tmdb ${radarr.tmdb_id}`;
  return title;
}

export function folderColumnCopy(row: JsParam) {
  return String(row?.folder || row?.radarr?.folder_path || "").trim() || "Folder unknown";
}

export function repairActionsFor(kind: string, mediaType: string = "movie") {
  const key = String(kind || "").toLowerCase();
  const media = String(mediaType || "movie").toLowerCase();
  if (key === "needs_plex_id") return ["rematch", "skip"];
  if (key === "path_conflict" || key === "title_collision") return ["rematch", "skip", "retry"];
  if (media === "show" || media === "episode" || media === "tv") return ["retry", "investigate", "skip"];
  return ["retry", "skip", "rematch"];
}

export function collectRepairItems(radarrRegister: JsParam, sonarrMissing: JsParam) {
  const items: JsParam[] = [];
  for (const raw of Array.isArray(radarrRegister?.items) ? radarrRegister.items : []) {
    const status = String(raw.status || "").toLowerCase();
    const outcome = String(raw.outcome || "").toLowerCase();
    if (status !== "failed" && outcome !== "path_conflict" && outcome !== "failed") continue;
    const kind = outcome === "path_conflict" ? "path_conflict" : "failed";
    const plexTmdb = raw.plex_tmdb_id ?? raw.tmdb_id;
    const radarrTmdb = raw.radarr_tmdb_id;
    const folderPath = String(raw.folder_path || raw.folder || "").trim();
    items.push({
      id: raw.id,
      source: "radarr_register",
      title: raw.title || raw.name || "This title",
      year: raw.year,
      kind,
      message: humanizeMiss(raw.error || raw.message || ""),
      mediaType: "movie",
      tmdbId: plexTmdb,
      plexTmdbId: plexTmdb,
      radarrTmdbId: radarrTmdb,
      folderPath: folderPath || undefined,
      actions: repairActionsFor(kind, "movie"),
    });
  }
  const execution = sonarrMissing?.execution || {};
  const lastError = String(execution.last_error || sonarrMissing?.error || "").trim();
  const failedCount = Number(execution.failed) || 0;
  if (lastError || failedCount) {
    const current = execution.current || sonarrMissing?.current;
    items.push({
      id: "sonarr-miss",
      source: "sonarr_missing",
      title: current?.name || current?.message || "Sonarr search",
      kind: "failed",
      message: humanizeMiss(lastError || "A Sonarr search command failed."),
      mediaType: "show",
      actions: repairActionsFor("failed", "show"),
    });
  }
  return items;
}
