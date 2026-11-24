/** Rooms, Play in…, and the live-channel remote. The room list is names only. */

export type RoomRow = {
  id: string;
  name: string;
  kind: string;
};

export type SessionClock = {
  position_ms: number;
  server_time_ms: number;
  state: string;
};

export function capabilityOn(payload: unknown, name: string) {
  const bag = (payload as { capabilities?: Record<string, unknown> } | null)?.capabilities;
  const raw = bag?.[name];
  const value = typeof raw === "number" ? raw : Number(raw || 0);
  return Number.isFinite(value) && value >= 1;
}

/** The household list is the screen's name. Playback fields are dropped. */
export function roomRows(payload: { rooms?: unknown } | null | undefined): RoomRow[] {
  const rows = Array.isArray(payload?.rooms) ? payload.rooms : [];
  const rooms: RoomRow[] = [];
  for (const row of rows) {
    if (!row || typeof row !== "object") continue;
    const item = row as Record<string, unknown>;
    const id = String(item.id || "").trim();
    const name = String(item.name || "").trim();
    if (!id || !name) continue;
    rooms.push({ id, name, kind: String(item.kind || "tv") });
  }
  return rooms;
}

export function joinSentence(status: string) {
  if (status === "pending") return "Waiting for a yes. Nothing about the film is shown yet.";
  if (status === "declined") return "Not now.";
  return "";
}

export function estimatePlayhead(
  positionMs: number,
  serverTimeMs: number,
  nowMs: number,
  state: string,
) {
  if (String(state || "") !== "playing") return Math.max(0, Math.floor(positionMs));
  const elapsed = Math.max(0, Math.floor(nowMs) - Math.floor(serverTimeMs));
  return Math.max(0, Math.floor(positionMs) + elapsed);
}

export function formatPlayhead(ms: number) {
  const total = Math.max(0, Math.floor(Number(ms) / 1000));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = total % 60;
  const ss = String(seconds).padStart(2, "0");
  if (hours > 0) return `${hours}:${String(minutes).padStart(2, "0")}:${ss}`;
  return `${minutes}:${ss}`;
}

export function playheadNow(clock: SessionClock | null, nowMs = Date.now()) {
  if (!clock) return 0;
  return estimatePlayhead(clock.position_ms, clock.server_time_ms, nowMs, clock.state);
}

export function openSessionBody(screenId: string, ratingKey: string) {
  return {
    screen_id: String(screenId || "").trim(),
    rating_key: String(ratingKey || "").trim(),
    level: "off",
  };
}

export type RemoteRole = "owner" | "guest" | "screen";

export function remoteRole(
  session: { owner_id?: unknown; guests?: unknown } | null | undefined,
  userId: string,
): RemoteRole {
  const id = String(userId || "");
  if (id && id === String(session?.owner_id || "")) return "owner";
  const guests = Array.isArray(session?.guests) ? session.guests.map(String) : [];
  if (id && guests.includes(id)) return "guest";
  return "screen";
}

/** Guests use the remote only after the starter allows it. */
export function mayUseRemote(role: RemoteRole, guestsMayRemote: boolean) {
  if (role === "guest") return Boolean(guestsMayRemote);
  return true;
}

export function transportCommand(command: "play" | "pause" | "skip" | "end", seconds = 0) {
  if (command === "skip") return { command, s: Math.trunc(seconds) };
  return { command };
}

export function sessionLiveUrl(sessionId: string, pageUrl = "http://127.0.0.1/") {
  const page = new URL(pageUrl);
  const protocol = page.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${page.host}/api/sessions/${encodeURIComponent(sessionId)}/live`;
}
