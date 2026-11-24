/** When a start is still quiet, the warm-up screen takes over. */

export const WARMUP_AFTER_MS = 800;
export const LINE_HOLD_MS = 4_000;
export const ART_HOLD_MS = 8_000;
export const CHOICE_AFTER_MS = 45_000;
export const PREROLL_PRELOAD_LEAD_S = 5;

const STEP_STATUS: Record<string, string> = {
  waking_disk: "Waking the disk",
  probing: "Reading the film",
  remuxing: "Packing the picture",
  encoding_audio: "Preparing the sound for your speakers",
  preparing_captions: "Preparing the captions",
  falling_back: "Switching to the other projector",
  waiting_on_plex: "Waiting on the library",
  buffering: "Catching up",
};

export type WarmupHumor = "on" | "dry" | "off";

export type WarmupLines = {
  version?: number;
  general?: string[];
  steps?: Record<string, string[]>;
};

export function honestStatus(step: string, elapsedMs: number): string {
  const label = STEP_STATUS[step] || "Starting";
  const seconds = Math.max(0, Math.floor(Number(elapsedMs) / 1000));
  return `${label} · ${seconds} s`;
}

/** One unused line from the step, then the general pool. Empty when the bank is spent. */
export function nextWarmupLine(lines: WarmupLines | null, step: string, used: ReadonlySet<string>): string {
  const specific = lines?.steps?.[step] || [];
  const general = lines?.general || [];
  for (const line of [...specific, ...general]) {
    const text = String(line || "").trim();
    if (text && !used.has(text)) return text;
  }
  return "";
}

export function jokeForHumor(humor: WarmupHumor, line: string, choices: boolean): string {
  if (choices || humor === "dry" || humor === "off") return "";
  return line;
}

export function warmupShouldShow({
  elapsedMs,
  hasPicture,
  prerollPlaying,
}: {
  elapsedMs: number;
  hasPicture: boolean;
  prerollPlaying: boolean;
}): boolean {
  if (prerollPlaying || hasPicture) return false;
  return Number(elapsedMs) >= WARMUP_AFTER_MS;
}

export function choicesDue({ elapsedMs, hasPicture }: { elapsedMs: number; hasPicture: boolean }): boolean {
  return !hasPicture && Number(elapsedMs) >= CHOICE_AFTER_MS;
}

export function shouldPreloadDuringPreroll({
  currentTime,
  duration,
  filmReady,
}: {
  currentTime: number;
  duration: number;
  filmReady: boolean;
}): boolean {
  if (!filmReady) return false;
  if (!Number.isFinite(duration) || duration <= 0) return false;
  if (!Number.isFinite(currentTime)) return false;
  return duration - currentTime <= PREROLL_PRELOAD_LEAD_S;
}

export function artFace(elapsedMs: number, reducedMotion: boolean): "backdrop" | "poster" {
  if (reducedMotion) return "backdrop";
  const slice = Math.floor(Math.max(0, Number(elapsedMs)) / ART_HOLD_MS);
  return slice % 2 === 0 ? "backdrop" : "poster";
}

export function filmReadyForHandoff(session: { state?: string; plan?: string; engine?: boolean } | null): boolean {
  if (!session) return false;
  if (session.plan === "library") return true;
  if (session.engine === false) return true;
  return session.state === "ready";
}
