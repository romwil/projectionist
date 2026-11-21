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
