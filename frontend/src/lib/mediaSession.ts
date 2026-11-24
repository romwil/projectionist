type MediaArtwork = { src: string; sizes?: string; type?: string };

type SessionControls = {
  title?: string;
  artist?: string;
  artwork?: string;
  paused?: boolean;
  duration?: number;
  position?: number;
  onPlay?: () => void;
  onPause?: () => void;
  onSeek?: (seconds: number) => void;
  onSkip?: (deltaSeconds: number) => void;
};

type SessionTarget = {
  metadata: MediaMetadata | null;
  playbackState: "none" | "paused" | "playing";
  setActionHandler: (
    name: string,
    handler: ((details?: { seekTime?: number; seekOffset?: number }) => void) | null,
  ) => void;
  setPositionState?: (state: {
    duration?: number;
    position?: number;
    playbackRate?: number;
  }) => void;
};

const ACTIONS = ["play", "pause", "seekto", "seekbackward", "seekforward"] as const;

/** Absolute artwork URL, or empty when the title has no poster. */
export function mediaSessionArtwork(posterUrl: string, origin = ""): string {
  const raw = String(posterUrl || "").trim();
  if (!raw || raw.length > 2000) return "";
  if (/^https?:\/\//i.test(raw)) return raw;
  if (raw.startsWith("/") && origin) return `${origin.replace(/\/$/, "")}${raw}`;
  return "";
}

export function mediaSessionMetadata(input: SessionControls, origin = "") {
  const title = String(input.title || "Projectionist").slice(0, 180);
  const artist = String(input.artist || "Projectionist").slice(0, 120);
  const src = mediaSessionArtwork(String(input.artwork || ""), origin);
  const artwork: MediaArtwork[] = src ? [{ src, sizes: "512x512" }] : [];
  return { title, artist, album: "Projectionist", artwork };
}

/**
 * Publish the current film to the platform media session.
 * Missing `navigator.mediaSession` is a no-op. Handlers stay off when unused.
 */
export function syncPlaybackMediaSession(
  target: SessionTarget | null | undefined,
  input: SessionControls,
  origin = "",
) {
  if (!target || typeof MediaMetadata === "undefined") return;
  const meta = mediaSessionMetadata(input, origin);
  target.metadata = new MediaMetadata(meta);
  target.playbackState = input.paused ? "paused" : "playing";
  const duration = Number(input.duration);
  const position = Number(input.position);
  if (
    typeof target.setPositionState === "function" &&
    Number.isFinite(duration) &&
    duration > 0 &&
    Number.isFinite(position) &&
    position >= 0 &&
    position <= duration
  ) {
    try {
      target.setPositionState({
        duration,
        position,
        playbackRate: input.paused ? 0 : 1,
      });
    } catch {
      // A browser may reject a position that moved past the last report.
    }
  }
  const handlers: Record<
    (typeof ACTIONS)[number],
    ((details?: { seekTime?: number; seekOffset?: number }) => void) | null
  > = {
    play: input.onPlay ? () => input.onPlay?.() : null,
    pause: input.onPause ? () => input.onPause?.() : null,
    seekto: input.onSeek
      ? (details) => {
          const next = Number(details?.seekTime);
          if (Number.isFinite(next)) input.onSeek?.(next);
        }
      : null,
    seekbackward: input.onSkip ? () => input.onSkip?.(-10) : null,
    seekforward: input.onSkip ? () => input.onSkip?.(10) : null,
  };
  for (const name of ACTIONS) {
    try {
      target.setActionHandler(name, handlers[name]);
    } catch {
      // This browser does not offer that action.
    }
  }
}

export function clearPlaybackMediaSession(target: SessionTarget | null | undefined) {
  if (!target) return;
  target.metadata = null;
  target.playbackState = "none";
  for (const name of ACTIONS) {
    try {
      target.setActionHandler(name, null);
    } catch {
      // Ignore unsupported actions.
    }
  }
}
