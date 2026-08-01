/** Ephemeral “tonight’s queue” shelf — session-scoped, not persisted to the server. */

const STORAGE_KEY = "projectionist_tonight_queue_v1";
const MAX_ITEMS = 8;

/**
 * @returns {Array<{ id: string, title: string, channelId?: string, addedAt: number }>}
 */
export function loadTonightQueue() {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((item) => item && typeof item === "object" && item.title)
      .slice(0, MAX_ITEMS)
      .map((item) => ({
        id: String(item.id || item.title),
        title: String(item.title).trim(),
        channelId: item.channelId ? String(item.channelId) : "",
        addedAt: Number(item.addedAt) || Date.now(),
      }));
  } catch {
    return [];
  }
}

/**
 * @param {Array<{ id: string, title: string, channelId?: string, addedAt: number }>} items
 */
export function saveTonightQueue(items) {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify((items || []).slice(0, MAX_ITEMS)));
  } catch {
    // sessionStorage unavailable
  }
}

/**
 * @param {{ title: string, channelId?: string, id?: string }} item
 * @param {Array} [current]
 */
export function addToTonightQueue(item, current) {
  const list = Array.isArray(current) ? [...current] : loadTonightQueue();
  const title = String(item?.title || "").trim();
  if (!title) return list;
  const id = String(item.id || `${item.channelId || "x"}:${title}`);
  const next = [
    {
      id,
      title,
      channelId: item.channelId ? String(item.channelId) : "",
      addedAt: Date.now(),
    },
    ...list.filter((row) => row.id !== id),
  ].slice(0, MAX_ITEMS);
  saveTonightQueue(next);
  return next;
}

/**
 * @param {string} id
 * @param {Array} [current]
 */
export function removeFromTonightQueue(id, current) {
  const list = Array.isArray(current) ? current : loadTonightQueue();
  const next = list.filter((row) => row.id !== String(id));
  saveTonightQueue(next);
  return next;
}

export function clearTonightQueue() {
  saveTonightQueue([]);
  return [];
}

export const TONIGHT_QUEUE_KEY = STORAGE_KEY;
