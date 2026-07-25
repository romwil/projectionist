/**
 * Generate a UUID-like id that works outside secure contexts.
 *
 * `crypto.randomUUID` is missing (or throws) on non-HTTPS LAN origins
 * (e.g. http://10.x.x.x). Prefer getRandomValues, then Math.random.
 */
export function createId({ compact = false } = {}) {
  let uuid;
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    try {
      uuid = crypto.randomUUID();
    } catch {
      uuid = undefined;
    }
  }
  if (!uuid && typeof crypto !== "undefined" && typeof crypto.getRandomValues === "function") {
    const bytes = new Uint8Array(16);
    crypto.getRandomValues(bytes);
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
    uuid = `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
  }
  if (!uuid) {
    uuid = "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (ch) => {
      const n = Math.floor(Math.random() * 16);
      const v = ch === "x" ? n : (n & 0x3) | 0x8;
      return v.toString(16);
    });
  }
  return compact ? uuid.replace(/-/g, "") : uuid;
}
