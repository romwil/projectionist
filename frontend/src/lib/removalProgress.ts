/** Live library-removal session shared by the summary dialog. */

import type {JsonObject, JsParam} from "../api/types";
import {
  LIBRARY_DELETE_MODE_FULL,
  formatRemovalFreedLabel,
  normalizeLibraryDeleteMode,
  normalizeRemovalSummary,
  removalViaLabel,
} from "./bulkLibraryDelete.js";

export const REMOVAL_STOP_REMAINING_NOTE =
  "Stops titles that have not started. Titles already removed stay removed.";

const STATUS_LABEL: Record<string, any> = {
  waiting: "Waiting",
  removing: "Removing",
  removed: "Removed",
  failed: "Failed",
  stopped: "Not started",
};

function blankItem(target: JsParam) {
  return {
    rating_key: String(target?.rating_key || ""),
    title: String(target?.title || "Untitled").trim() || "Untitled",
    status: "waiting",
    files: [],
    folders: [],
    bytes_freed: 0,
    bytes_source: "",
    note: "",
    removed_via: "",
    error: "",
  };
}

export function createRemovalSession({ mode, targets = [] }: JsParam = {}) {
  const items = (Array.isArray(targets) ? targets : []).map(blankItem);
  return {
    live: true,
    phase: "running",
    mode: normalizeLibraryDeleteMode(mode),
    items,
    done: 0,
    total: items.length,
    files: 0,
    folders: 0,
    bytes_freed: 0,
    cancelled: false,
    error: "",
    result: null,
  };
}

export function isLiveRemoval(value: unknown) {
  return Boolean(value && (value as JsParam).live === true && Array.isArray((value as JsParam).items));
}

export function removalStatusLabel(status: unknown, via?: unknown) {
  if (status === "removed") {
    return removalViaLabel({ removed_via: via }) || STATUS_LABEL.removed;
  }
  return STATUS_LABEL[String(status)] || "Waiting";
}

function countsFrom(event: JsParam, session: JsParam) {
  const done = Number(event?.done);
  const files = Number(event?.files_so_far);
  const folders = Number(event?.folders_so_far);
  const bytes = Number(event?.bytes_freed_so_far);
  return {
    done: Number.isFinite(done) ? done : session.done,
    total: Number(event?.total) || session.total,
    files: Number.isFinite(files) ? files : session.files,
    folders: Number.isFinite(folders) ? folders : session.folders,
    bytes_freed: Number.isFinite(bytes) ? bytes : session.bytes_freed,
  };
}

export function sessionToRemovalResult(session: JsParam) {
  const items = Array.isArray(session?.items) ? session.items : [];
  const results = items
    .filter((item: JsParam) => item.status === "removed")
    .map((item: JsParam) => ({
      rating_key: item.rating_key,
      title: item.title,
      media_type: item.media_type || "",
      ok: true,
      index_deleted: true,
      files: item.files || [],
      folders: item.folders || [],
      bytes_freed: Number(item.bytes_freed) || 0,
      bytes_source: item.bytes_source || "unknown",
      note: item.note || "",
      removed_via: item.removed_via || "",
    }));
  const errors = items
    .filter((item: JsParam) => item.status === "failed")
    .map((item: JsParam) => ({
      rating_key: item.rating_key,
      title: item.title,
      error: item.error || "Could not remove this title",
      index_deleted: false,
    }));
  const summary = normalizeRemovalSummary({
    mode: session?.mode,
    deleted: results.length,
    results,
    errors,
  });
  return {
    mode: normalizeLibraryDeleteMode(session?.mode),
    deleted: results.length,
    results,
    errors,
    totals: summary.totals,
    cancelled: Boolean(session?.cancelled),
  };
}

export function finishRemovalSession(session: JsParam, result: JsParam, { stopped = false }: JsParam = {}) {
  if (!session) return session;
  const cancelled = Boolean(stopped || session.cancelled || result?.cancelled);
  const items = session.items.map((item: JsParam) => {
    if (!cancelled) return item;
    if (item.status === "waiting") return { ...item, status: "stopped" };
    return item;
  });
  const payload = result || sessionToRemovalResult({ ...session, items, cancelled });
  const totals = payload?.totals || {};
  return {
    ...session,
    live: true,
    phase: "done",
    items,
    cancelled,
    result: payload,
    done: items.filter((item: JsParam) => item.status !== "waiting" && item.status !== "removing").length,
    total: session.total,
    files: Number(totals.files) || 0,
    folders: Number(totals.folders) || 0,
    bytes_freed: Number(totals.bytes_freed) || 0,
    error: "",
  };
}

export function failRemovalSession(session: JsParam, error: unknown) {
  const message = String((error as JsParam)?.message || "The removal connection dropped.").trim();
  const base = session || createRemovalSession({ mode: "full", targets: [] });
  const items = base.items.map((item: JsParam) => {
    if (item.status === "waiting") return { ...item, status: "stopped" };
    if (item.status === "removing") {
      return {
        ...item,
        status: "failed",
        error: `${message} This title may already have been removed.`,
      };
    }
    return item;
  });
  const next = { ...base, items, cancelled: true, error: message };
  return finishRemovalSession(next, sessionToRemovalResult(next), { stopped: true });
}

export function applyRemovalProgressEvent(session: JsParam, event: JsParam) {
  if (!session || !event || typeof event !== "object") return session;
  if (event.type === "start") {
    const serverItems = Array.isArray(event.items) ? event.items : [];
    const items = serverItems.length ? serverItems.map(blankItem) : session.items;
    return {
      ...session,
      mode: event.mode ? normalizeLibraryDeleteMode(event.mode) : session.mode,
      items,
      total: Number(event.total) || items.length,
      phase: "running",
    };
  }
  if (event.type === "cancelled") {
    const counts = countsFrom(event, session);
    return {
      ...session,
      ...counts,
      cancelled: true,
      items: session.items.map((item: JsParam) =>
        item.status === "waiting" ? { ...item, status: "stopped" } : item,
      ),
    };
  }
  if (event.type === "title") {
    const counts = countsFrom(event, session);
    const items = session.items.map((item: JsParam) => {
      if (item.rating_key !== String(event.rating_key || "")) return item;
      const title = String(event.title || item.title || "Untitled");
      if (event.status === "removing") return { ...item, status: "removing", title };
      if (event.status === "failed") {
        return {
          ...item,
          status: "failed",
          title,
          error: String(event.error || "Could not remove this title"),
        };
      }
      const entry = event.entry && typeof event.entry === "object" ? event.entry : {};
      return {
        ...item,
        status: "removed",
        title: String(entry.title || title),
        files: Array.isArray(entry.files) ? entry.files.map(String) : [],
        folders: Array.isArray(entry.folders) ? entry.folders.map(String) : [],
        bytes_freed: Number(entry.bytes_freed) || 0,
        bytes_source: String(entry.bytes_source || ""),
        note: String(entry.note || ""),
        removed_via: String(entry.removed_via || ""),
        error: "",
      };
    });
    return { ...session, ...counts, items, phase: "running" };
  }
  if (event.type === "complete") {
    return finishRemovalSession(session, event.result || null, {
      stopped: Boolean(event.result?.cancelled),
    });
  }
  return session;
}

/** Visible progress copy. The dialog renders these strings. */
export function removalProgressView(session: JsParam) {
  const live = isLiveRemoval(session);
  const running = live && session.phase !== "done";
  const mode = normalizeLibraryDeleteMode(session?.mode || session?.result?.mode);
  const finished = live ? session.result : session;
  const summary = normalizeRemovalSummary(finished || {});
  const deleted = Number(summary.deleted);
  const titleCount = Number.isFinite(deleted) ? deleted : summary.results.length;
  const titleCountLabel = running ? `${session.done} of ${session.total}` : String(titleCount);
  const full = mode === LIBRARY_DELETE_MODE_FULL;
  let heading = "What was removed";
  if (running) heading = "What is being removed";
  else if (!full) heading = "Removed from library index";
  const freedSource = running
    ? { bytes_freed: session.bytes_freed, bytes_source: "arr", files: session.files, folders: session.folders }
    : summary.totals;
  return {
    running,
    heading,
    titleCountLabel,
    titleCount,
    freedLabel: formatRemovalFreedLabel(freedSource),
    filesLabel: running ? String(session.files || 0) : String(summary.totals.files),
    foldersLabel: running ? String(session.folders || 0) : String(summary.totals.folders),
    items: live ? session.items : summary.results,
  };
}
