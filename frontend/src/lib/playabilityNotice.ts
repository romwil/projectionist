type PlayabilityNoticeReport = {
  message?: string;
  complete?: boolean;
  running?: boolean;
  profiles?: unknown[];
} | null;

const EMPTY = "No playability report yet. Refresh to walk the library.";

/**
 * The sentence under Refresh. An empty library still uses its own message.
 * A walk that stopped keeps that sentence even when profile rows are present.
 */
export function playabilityNotice(report: PlayabilityNoticeReport): string {
  if (!report) return "";
  const profiles = report.profiles || [];
  if (profiles.length === 0) return report.message || EMPTY;
  if (report.complete === false && !report.running && report.message) return report.message;
  return "";
}

type SourceBreakdown = {
  video_transcode?: number;
  codec?: number;
  level?: number;
  bit_depth?: number;
  resolution?: number;
  hdr?: number;
} | null;

/** Why the source-transcode bucket is that size. Resolution and HDR overlap the other reasons. */
export function sourceBreakdownLine(breakdown: SourceBreakdown): string {
  if (!breakdown || !Number(breakdown.video_transcode)) return "";
  const count = Number(breakdown.video_transcode);
  return (
    `Video transcode ${count}: codec ${Number(breakdown.codec || 0)}, ` +
    `level ${Number(breakdown.level || 0)}, bit depth ${Number(breakdown.bit_depth || 0)}. ` +
    `Above 1080p ${Number(breakdown.resolution || 0)}. HDR ${Number(breakdown.hdr || 0)}.`
  );
}

type GpuDecision = { safari?: number | null; apple_tv?: number | null } | null;

/** The two counts that decide whether a GPU is worth it. A missing device is omitted. */
export function gpuDecisionLine(gpu: GpuDecision): string {
  if (!gpu) return "";
  const lines: string[] = [];
  if (gpu.safari != null) {
    lines.push(`Safari would need a video transcode for ${Number(gpu.safari)} titles.`);
  }
  if (gpu.apple_tv != null) {
    lines.push(`Apple TV would need a video transcode for ${Number(gpu.apple_tv)} titles.`);
  }
  return lines.join(" ");
}
