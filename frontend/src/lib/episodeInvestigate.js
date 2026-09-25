/** Selection defaults and copy for Admin → Libraries Investigate (v1.36.0). */

export const STILLS_LEAVE_LAN =
  "When vision is on, three stills leave the LAN so the chat LLM can look at them.";

export const SCENE_NAMES_NOT_EVIDENCE =
  "Scene names and SxxEyy in the filename are a claim, not evidence.";

export const FFMPEG_MISSING =
  "This running container cannot find ffmpeg on PATH. The Projectionist image should include it — that is a bad image or PATH, not a host install. Set FFMPEG_PATH and FFPROBE_PATH only to override.";

export function defaultRowSelected(row) {
  if (!row) return false;
  if (row.same_show === false) return false;
  if (typeof row.selected_default === "boolean") return row.selected_default;
  const confidence = String(row.confidence || "").toLowerCase();
  return confidence === "certain" || confidence === "likely";
}

export function selectedFileIds(rows, selected) {
  return (rows || [])
    .filter((row) => selected[row.id] && row.same_show !== false)
    .map((row) => String(row.id));
}

export function selectionMap(rows) {
  const next = {};
  for (const row of rows || []) {
    next[row.id] = defaultRowSelected(row);
  }
  return next;
}

export function confidenceLabel(confidence) {
  const key = String(confidence || "").toLowerCase();
  if (key === "certain") return "Certain";
  if (key === "likely") return "Likely";
  return "Uncertain";
}

export function applyButtonClass(selectedCount) {
  return Number(selectedCount) > 0 ? "primary" : "ghost";
}

export function rowHasStills(row) {
  return Boolean((row?.stills || []).length);
}

export function rowHasIdentify(row) {
  const identify = row?.identify;
  return Boolean(identify && identify.found);
}

export function rowHasVision(row) {
  const vision = row?.vision;
  if (!vision || typeof vision !== "object") return false;
  return Boolean(vision.scope || vision.reason || vision.season != null);
}

export function reviewEvidenceSummary(rows, options = {}) {
  const list = Array.isArray(rows) ? rows : [];
  if (!list.length) return "";
  const ffmpegReady = options.ffmpegReady !== false;
  const visionOn = Boolean(options.visionOn);
  const identifyConfigured = options.identifyConfigured !== false;
  const uncertain = list.filter((row) => confidenceLabel(row.confidence) === "Uncertain").length;
  const noStills = list.filter((row) => !rowHasStills(row)).length;
  const noIdentify = list.filter((row) => !rowHasIdentify(row)).length;
  const noVision = list.filter((row) => !rowHasVision(row)).length;

  if (!ffmpegReady) {
    return (
      `${list.length} file${list.length === 1 ? "" : "s"} finished with no stills, no runtime probe, and no Identify clip because ffmpeg is missing from this container. ` +
      `Vision had nothing to send. Fusion is done — not still running. ` +
      `Set FFMPEG_PATH and FFPROBE_PATH only if you need a different binary.`
    );
  }

  const systematic = uncertain === list.length || noStills === list.length;
  if (!systematic) return "";

  const bits = [];
  if (uncertain === list.length) {
    bits.push(`All ${list.length} rows are Uncertain.`);
  }
  if (noStills === list.length) {
    bits.push("No stills were extracted.");
  }
  if (!visionOn) {
    bits.push("Vision was off.");
  } else if (noVision === list.length) {
    bits.push("Vision had nothing to look at.");
  }
  if (!identifyConfigured) {
    bits.push("Identify is not configured.");
  } else if (noIdentify === list.length) {
    bits.push("Identify did not return a match.");
  }
  bits.push("Fusion is done — not still running.");
  return bits.join(" ");
}
