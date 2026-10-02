/**
 * Rotational queue padding — "up to X" titles in the rotation.
 *
 * What's playing fills slots first; any spare slots (X minus what's playing)
 * are filled from Recently added or Recently released, played after the
 * playing block so the rotation does not snap back to the start. Mirrors
 * `projectionist/live_channels/queue_padding.py`; the server is the source of
 * truth, this is only for the setup copy and the request payload.
 */

export const QUEUE_PAD_UP_TO = [1, 2, 3, 4, 5];

export const QUEUE_PAD_FEEDS = [
  { id: "recently_added", label: "Recently added" },
  { id: "recently_released", label: "Recently released" },
];

export const DEFAULT_QUEUE_PAD_DRAFT = { queue_up_to: 5, queue_feed: "recently_added" };

function clampUpTo(value) {
  const n = Math.trunc(Number(value));
  if (!Number.isFinite(n) || n <= 0) return 0;
  return Math.min(5, Math.max(1, n));
}

export function normalizeQueueFeed(value) {
  const id = String(value || "").trim().toLowerCase();
  return QUEUE_PAD_FEEDS.some((feed) => feed.id === id) ? id : "recently_added";
}

/** 0 = padding off. Missing fields fall back to the product default (5, Recently added). */
export function queuePadDraft(source) {
  const hasUpTo = source && source.queue_up_to !== undefined && source.queue_up_to !== "";
  return {
    queue_up_to: hasUpTo ? clampUpTo(source.queue_up_to) : DEFAULT_QUEUE_PAD_DRAFT.queue_up_to,
    queue_feed: normalizeQueueFeed(source?.queue_feed),
  };
}

/** Draft from a saved station (`queue_pad` absent/empty = padding off). */
export function queuePadDraftFromStation(station) {
  const pad = station?.queue_pad;
  if (!pad || !pad.up_to) {
    return { queue_up_to: 0, queue_feed: "recently_added" };
  }
  return { queue_up_to: clampUpTo(pad.up_to), queue_feed: normalizeQueueFeed(pad.feed) };
}

/** Request body value: `{}` clears padding, otherwise `{ up_to, feed }`. */
export function queuePadPayload(draft) {
  const { queue_up_to: upTo, queue_feed: feed } = queuePadDraft(draft);
  return upTo > 0 ? { up_to: upTo, feed } : {};
}

/** Spare slots = max(0, up_to − playing). */
export function queuePadSlots(upTo, playing) {
  const cap = clampUpTo(upTo);
  const count = Math.max(0, Math.trunc(Number(playing)) || 0);
  return Math.max(0, cap - count);
}

export function queuePadSummary(draft, playing = null) {
  const { queue_up_to: upTo, queue_feed: feed } = queuePadDraft(draft);
  if (upTo <= 0) {
    return "No padding — the channel loops back as soon as what’s playing ends.";
  }
  const feedLabel = QUEUE_PAD_FEEDS.find((row) => row.id === feed)?.label.toLowerCase();
  if (playing == null) {
    return `Keeps up to ${upTo} on rotation. Spare slots after what’s playing are filled from ${feedLabel}.`;
  }
  const spare = queuePadSlots(upTo, playing);
  if (spare === 0) {
    return `${playing} playing already fills up to ${upTo} — nothing to add.`;
  }
  return `${playing} playing + ${spare} from ${feedLabel} (up to ${upTo}).`;
}
