/** Normalize Live Channels on-now API payload into a display model. Pure logic. */

/**
 * @param {number|null|undefined} seconds
 * @returns {string}
 */
export function formatRemaining(seconds) {
  if (seconds == null || !Number.isFinite(Number(seconds))) return "";
  const total = Math.max(0, Math.round(Number(seconds)));
  if (total < 60) return `${total}s left`;
  const minutes = Math.round(total / 60);
  if (minutes < 60) return `${minutes}m left`;
  const hours = Math.floor(minutes / 60);
  const rem = minutes % 60;
  return rem ? `${hours}h ${rem}m left` : `${hours}h left`;
}

/**
 * @param {{ percent?: number|null, secondsRemaining?: number|null, isPaused?: boolean }} channel
 * @returns {string}
 */
export function formatProgressHint(channel) {
  if (!channel) return "";
  if (channel.isPaused) return "Paused";
  const parts = [];
  if (channel.percent != null && Number.isFinite(Number(channel.percent))) {
    parts.push(`${Math.round(Number(channel.percent))}%`);
  }
  const remaining = formatRemaining(channel.secondsRemaining);
  if (remaining) parts.push(remaining);
  return parts.join(" · ");
}

/**
 * @param {object|null|undefined} snapshot
 * @returns {null | {
 *   enabled: boolean,
 *   ready: boolean,
 *   reason: string,
 *   plexHint: string,
 *   channels: Array<{
 *     id: string,
 *     name: string,
 *     number: number|null,
 *     nowTitle: string,
 *     nextTitle: string,
 *     nowRating: string,
 *     percent: number|null,
 *     secondsElapsed: number|null,
 *     secondsRemaining: number|null,
 *     startedAt: number|null,
 *     endsAt: number|null,
 *     isPaused: boolean,
 *     progressHint: string,
 *   }>,
 * }}
 */
export function normalizeOnNow(snapshot) {
  if (!snapshot || typeof snapshot !== "object") return null;
  const enabled = Boolean(snapshot.enabled);
  if (!enabled) return null;

  const rawChannels = Array.isArray(snapshot.channels) ? snapshot.channels : [];
  const channels = rawChannels
    .map((channel) => {
      if (!channel || typeof channel !== "object") return null;
      const now = channel.now && typeof channel.now === "object" ? channel.now : null;
      const next = channel.next && typeof channel.next === "object" ? channel.next : null;
      const number =
        channel.number == null || channel.number === ""
          ? null
          : Number.isFinite(Number(channel.number))
            ? Number(channel.number)
            : null;
      const name = String(channel.name || "Channel").trim() || "Channel";
      const percent =
        now?.percent == null || !Number.isFinite(Number(now.percent))
          ? null
          : Math.max(0, Math.min(100, Number(now.percent)));
      const secondsElapsed =
        now?.seconds_elapsed == null || !Number.isFinite(Number(now.seconds_elapsed))
          ? null
          : Math.max(0, Math.round(Number(now.seconds_elapsed)));
      const secondsRemaining =
        now?.seconds_remaining == null || !Number.isFinite(Number(now.seconds_remaining))
          ? null
          : Math.max(0, Math.round(Number(now.seconds_remaining)));
      const startedAt =
        now?.started_at == null || !Number.isFinite(Number(now.started_at))
          ? null
          : Number(now.started_at);
      const endsAt =
        now?.ends_at == null || !Number.isFinite(Number(now.ends_at))
          ? null
          : Number(now.ends_at);
      const isPaused = Boolean(now?.is_paused);
      const row = {
        id: String(channel.id || `${number ?? "x"}-${name}`),
        name,
        number,
        nowTitle: String(now?.title || "").trim(),
        nextTitle: String(next?.title || "").trim(),
        nowRating: String(now?.content_rating || "").trim(),
        percent,
        secondsElapsed,
        secondsRemaining,
        startedAt,
        endsAt,
        isPaused,
      };
      return {
        ...row,
        progressHint: formatProgressHint(row),
      };
    })
    .filter(Boolean);

  return {
    enabled: true,
    ready: Boolean(snapshot.ready) && channels.length > 0,
    reason: String(snapshot.reason || "").trim(),
    plexHint: String(
      snapshot.plex_hint ||
        "Open Plex → Live TV to watch. Projectionist does not play Live Channels.",
    ),
    channels,
  };
}

/** Label like “101 · Chaos Night” or just the channel name. */
export function formatChannelLabel(channel) {
  if (!channel) return "";
  const name = String(channel.name || "Channel").trim() || "Channel";
  if (channel.number == null) return name;
  return `${channel.number} · ${name}`;
}

/** Compact “Now / Next” line for a channel row. */
export function formatOnNowLine(channel) {
  if (!channel) return "";
  if (channel.nowTitle && channel.nextTitle) {
    return `Now: ${channel.nowTitle} · Next: ${channel.nextTitle}`;
  }
  if (channel.nowTitle) return `Now: ${channel.nowTitle}`;
  if (channel.nextTitle) return `Up next: ${channel.nextTitle}`;
  return "Nothing scheduled right now";
}
