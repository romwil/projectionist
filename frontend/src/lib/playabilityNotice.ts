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

type SourceBreakdown =
  | {
      video_transcode?: number;
      codec?: number;
      codecs?: Record<string, number>;
      level?: number | null;
      bit_depth?: number | null;
      resolution?: number;
      hdr?: number | null;
    }
  | null
  | undefined;

const CODEC_LABELS: Record<string, string> = {
  hevc: "HEVC",
  h264: "H.264",
  av1: "AV1",
  vp9: "VP9",
  vc1: "VC-1",
  mpeg2video: "MPEG-2",
  mpeg4: "MPEG-4",
  mpeg1video: "MPEG-1",
  msmpeg4v2: "MS-MPEG-4 v2",
  msmpeg4v3: "MS-MPEG-4 v3",
};

function codecLabel(name: string): string {
  return CODEC_LABELS[name] || name;
}

/** A null measurement was not confirmed. Zero means the files were checked. */
function fact(value: number | null | undefined, label: string): string {
  if (value === null) return `${label} not confirmed yet`;
  return `${label} ${Number(value || 0)}`;
}

/** Why the source-transcode bucket is that size. Resolution and HDR overlap the other reasons. */
export function sourceBreakdownLine(breakdown: SourceBreakdown): string {
  if (!breakdown || !Number(breakdown.video_transcode)) return "";
  const count = Number(breakdown.video_transcode);
  const named = Object.entries(breakdown.codecs || {})
    .map(([name, amount]) => [name, Number(amount)] as const)
    .filter(([, amount]) => amount > 0)
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .map(([name, amount]) => `${codecLabel(name)} ${amount}`);
  const names = named.length ? `${named.join(", ")}. ` : "";
  return (
    `Video transcode ${count}: ${names}` +
    `codec ${Number(breakdown.codec || 0)}, ` +
    `${fact(breakdown.level, "level")}, ` +
    `${fact(breakdown.bit_depth, "bit depth")}. ` +
    `Above 1080p ${Number(breakdown.resolution || 0)}. ` +
    `${fact(breakdown.hdr, "HDR")}.`
  );
}

type GpuDecision = { safari?: number | null; apple_tv?: number | null } | null | undefined;

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
