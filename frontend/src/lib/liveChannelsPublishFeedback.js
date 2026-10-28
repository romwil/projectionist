import { craftSoftCapHonestyNote } from "./liveChannelsCopy.js";

export function formatPublishFeedback(result) {
  const published = result?.count_published || 0;
  const skipped = result?.count_skipped || 0;
  const errors = result?.count_errors || 0;
  const updated = result?.count_programming_updated || 0;
  const renamed = result?.count_renamed || 0;
  const matched = result?.matched;
  const matchTotal = result?.match_total;
  const lineup = result?.lineup_programs ?? result?.program_count;
  const plexSync = result?.plex_sync;
  // Only mention skip/error counts when non-zero — "skipped 0" looked like a miss
  // when a name clash quietly refreshed an existing station instead of creating one.
  const parts = [`Published ${published}`];
  if (skipped) parts.push(`skipped ${skipped}`);
  if (errors) parts.push(`errors ${errors}`);
  if (updated) parts.push(`lineups refreshed ${updated}`);
  if (renamed) parts.push(`renamed ${renamed}`);
  if (result?.remapped_number_from != null && result?.remapped_number_to != null) {
    parts.push(`number ${result.remapped_number_from}→${result.remapped_number_to}`);
  }
  if (matchTotal > 0) {
    parts.push(`matched ${matched ?? 0}/${matchTotal}`);
  }
  if (lineup != null && lineup !== "") {
    parts.push(`lineup ${lineup} programs`);
  }
  if (plexSync && plexSync.skipped !== true) {
    const mapped = plexSync.mapped;
    const expected = plexSync.expected;
    if (expected != null && mapped != null) {
      parts.push(`Plex mapped ${mapped}/${expected}`);
    }
  }
  const honesty = craftSoftCapHonestyNote(result || {});
  const noteAlreadyIncludesHonesty = Boolean(result?.note)
    && honesty
    && String(result.note).includes(honesty.slice(0, 24));
  const noteTail = result?.note
    ? noteAlreadyIncludesHonesty
      ? ` ${result.note}`
      : ` ${result.note}${honesty && !String(result.note).includes("soft cap") ? ` ${honesty}` : ""}`
    : honesty
      ? ` ${honesty}`
      : "";
  const summary = `${parts.join(", ")}.${noteTail}`;
  const details = [
    ...(result?.errors || []).map((err) => {
      const label = [err?.number, err?.name].filter((part) => part != null && part !== "").join(" · ");
      return `${label || "Channel"}: ${err?.error || "unknown error"}`;
    }),
    ...(result?.skipped || []).map((row) => {
      const label = [row?.number, row?.name].filter((part) => part != null && part !== "").join(" · ");
      const reason = row?.reason || "skipped";
      const note = row?.note ? ` — ${row.note}` : "";
      return `${label || "Channel"}: ${reason}${note}`;
    }),
  ];
  const plexFailed = result?.plex_sync_failed || plexSync?.ok === false;
  const type = errors > 0 || result?.ok === false || plexFailed ? "error" : "success";
  return { summary, details, type };
}
