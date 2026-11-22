/** Web player gate for Play through Projectionist (ENG-007). */

export type WebPlaybackProfile = {
  id: string;
  containers: string[];
  video: { codec: string; max_level: string; bit_depth?: number; hdr?: string[] }[];
  audio: string[];
  captions: string[];
  max_channels: number;
};

type CanPlay = (mimeType: string) => boolean;

type VideoProbe = { codec: string; max_level: string; bit_depth?: number; type: string };

// Each row is one runtime answer. The level and bit depth come from the row that passes,
// not from a fixed Safari or Chrome list.
const VIDEO_PROBES: VideoProbe[] = [
  { codec: "hevc", max_level: "5.1", bit_depth: 10, type: 'video/mp4; codecs="hvc1.2.4.L153.B0"' },
  { codec: "hevc", max_level: "5.0", bit_depth: 10, type: 'video/mp4; codecs="hvc1.2.4.L150.B0"' },
  { codec: "hevc", max_level: "4.0", bit_depth: 10, type: 'video/mp4; codecs="hvc1.2.4.L120.90"' },
  { codec: "hevc", max_level: "3.1", bit_depth: 10, type: 'video/mp4; codecs="hvc1.2.4.L93.B0"' },
  { codec: "hevc", max_level: "5.1", bit_depth: 8, type: 'video/mp4; codecs="hvc1.1.6.L153.B0"' },
  { codec: "hevc", max_level: "5.1", bit_depth: 8, type: 'video/mp4; codecs="hev1.1.6.L153.B0"' },
  // A bare hvc1 / hev1 yes does not name a level or a bit depth. Recording it
  // as Main 5.1 would remux a file this check never proved.
  { codec: "hevc", max_level: "4.0", bit_depth: 8, type: 'video/mp4; codecs="hvc1.1.6.L120.90"' },
  { codec: "hevc", max_level: "3.1", bit_depth: 8, type: 'video/mp4; codecs="hvc1.1.6.L93.B0"' },
  { codec: "hevc", max_level: "3.1", bit_depth: 8, type: 'video/mp4; codecs="hev1.1.6.L93.B0"' },
  { codec: "av1", max_level: "5.1", bit_depth: 10, type: 'video/mp4; codecs="av01.0.13M.10"' },
  { codec: "av1", max_level: "5.1", bit_depth: 8, type: 'video/mp4; codecs="av01.0.13M.08"' },
  { codec: "av1", max_level: "4.0", bit_depth: 8, type: 'video/mp4; codecs="av01.0.08M.08"' },
  { codec: "h264", max_level: "5.2", type: 'video/mp4; codecs="avc1.640034"' },
  { codec: "h264", max_level: "4.0", type: 'video/mp4; codecs="avc1.640028"' },
  { codec: "h264", max_level: "3.0", type: 'video/mp4; codecs="avc1.42E01E"' },
];

// Each row is one mp4 codec string. FLAC, Opus, and ALAC have no level.
// A yes on audio/flac or audio/ogg is the container, not this remux, so it
// is not a probe — the same way a bare hvc1 yes is not a level.
const AUDIO_PROBES: { codec: string; type: string }[] = [
  { codec: "ac3", type: 'audio/mp4; codecs="ac-3"' },
  { codec: "eac3", type: 'audio/mp4; codecs="ec-3"' },
  { codec: "flac", type: 'audio/mp4; codecs="flac"' },
  { codec: "opus", type: 'audio/mp4; codecs="opus"' },
  { codec: "alac", type: 'audio/mp4; codecs="alac"' },
];

function levelValue(level: string) {
  const number = Number(level);
  return Number.isFinite(number) ? number : 0;
}

function checkedTypes() {
  return [
    ...new Set([
      ...VIDEO_PROBES.map((probe) => probe.type),
      ...AUDIO_PROBES.map((probe) => probe.type),
    ]),
  ];
}

/** Safari reports HDR when the display is in high dynamic range. Chrome's user agent also contains "Safari". */
export function isSafariUserAgent(userAgent: string): boolean {
  const text = String(userAgent || "");
  if (!/safari/i.test(text)) return false;
  return !/chrome|chromium|crios|edg|android|headless/i.test(text);
}

/** The server tries HDR10 only when this is true and the codec probe found HEVC. */
export function safariReportsHdr(highDynamicRange: boolean, safari: boolean): boolean {
  return Boolean(highDynamicRange && safari);
}

/** One row per codec and bit depth. A 10-bit yes must not hide an 8-bit yes. */
export function browserPlaybackProfile(
  canPlay: CanPlay,
  maxChannels = 2,
  options: { hdr?: boolean } = {},
): WebPlaybackProfile {
  const supported = VIDEO_PROBES.filter((probe) => canPlay(probe.type));
  const video: WebPlaybackProfile["video"] = [];
  for (const codec of ["hevc", "av1", "h264"]) {
    const rows = supported.filter((probe) => probe.codec === codec);
    if (!rows.length) continue;
    const depths: number[] = [];
    for (const row of rows) {
      const depth = row.bit_depth ?? 0;
      if (!depths.includes(depth)) depths.push(depth);
    }
    for (const depth of depths) {
      const atBits = rows.filter((row) => (row.bit_depth ?? 0) === depth);
      const maxLevel = atBits.reduce(
        (best, row) => (levelValue(row.max_level) > levelValue(best) ? row.max_level : best),
        atBits[0].max_level,
      );
      const entry: WebPlaybackProfile["video"][number] = { codec, max_level: maxLevel };
      if (codec !== "h264" && depth) entry.bit_depth = depth;
      if (options.hdr && codec === "hevc") entry.hdr = ["hdr10"];
      video.push(entry);
    }
  }
  if (!video.length) video.push({ codec: "h264", max_level: "5.2" });
  const audio = ["aac"];
  for (const probe of AUDIO_PROBES) {
    if (canPlay(probe.type) && !audio.includes(probe.codec)) audio.push(probe.codec);
  }
  return {
    id: "web",
    containers: ["mp4", "hls-fmp4"],
    video,
    audio,
    captions: ["webvtt"],
    max_channels: Number(maxChannels) >= 6 ? 6 : 2,
  };
}

export type CodecRuntime = {
  canPlayType?: (type: string) => string;
  isTypeSupported?: (type: string) => boolean;
  decodingInfo?: (
    type: string,
    options?: { channels?: string },
  ) => Promise<{ supported?: boolean } | null | undefined>;
};

/**
 * One profile from canPlayType, MediaSource.isTypeSupported, and
 * MediaCapabilities.decodingInfo. Any yes is a yes. A no from one check
 * does not cancel a yes from another, so Safari can report HEVC through
 * canPlayType when Media Source does not list it.
 */
export async function browserPlaybackProfileFromRuntime(
  runtime: CodecRuntime,
  options: { hdr?: boolean } = {},
): Promise<WebPlaybackProfile> {
  const decoding = new Map<string, boolean>();
  if (runtime.decodingInfo) {
    await Promise.all(
      checkedTypes().map(async (type) => {
        try {
          const info = await runtime.decodingInfo!(type);
          decoding.set(type, Boolean(info?.supported));
        } catch {
          decoding.set(type, false);
        }
      }),
    );
  }
  let maxChannels = 2;
  if (runtime.decodingInfo) {
    try {
      const surround = await runtime.decodingInfo('audio/mp4; codecs="mp4a.40.2"', {
        channels: "6",
      });
      if (surround?.supported) maxChannels = 6;
    } catch {
      maxChannels = 2;
    }
  }
  return browserPlaybackProfile((type) => {
    const played = String(runtime.canPlayType?.(type) || "");
    if (played === "probably" || played === "maybe") return true;
    try {
      if (runtime.isTypeSupported?.(type)) return true;
    } catch {
      // This browser has no Media Source answer for the type.
    }
    return decoding.get(type) === true;
  }, maxChannels, options);
}

/** Ask this browser, at play time, and send that profile with the session. */
export function detectBrowserPlaybackProfile(): Promise<WebPlaybackProfile> {
  let highDynamicRange = false;
  try {
    highDynamicRange = Boolean(
      typeof window !== "undefined" && window.matchMedia?.("(dynamic-range: high)")?.matches,
    );
  } catch {
    highDynamicRange = false;
  }
  const safari = safariReportsHdr(
    highDynamicRange,
    isSafariUserAgent(typeof navigator !== "undefined" ? navigator.userAgent : ""),
  );
  const video = typeof document !== "undefined" ? document.createElement("video") : null;
  const mediaSource = typeof MediaSource !== "undefined" ? MediaSource : null;
  const capabilities = typeof navigator !== "undefined" ? navigator.mediaCapabilities : undefined;
  return browserPlaybackProfileFromRuntime({
    canPlayType: (type) => {
      try {
        return video?.canPlayType?.(type) || "";
      } catch {
        return "";
      }
    },
    isTypeSupported: (type) => {
      try {
        return Boolean(mediaSource?.isTypeSupported?.(type));
      } catch {
        return false;
      }
    },
    decodingInfo: capabilities?.decodingInfo
      ? async (type, options) => {
          const videoConfig = type.startsWith("video/")
            ? { contentType: type, width: 1920, height: 1080, bitrate: 8_000_000, framerate: 24 }
            : undefined;
          const audioConfig = type.startsWith("audio/")
            ? {
                contentType: type,
                channels: options?.channels || "2",
                bitrate: 384000,
                samplerate: 48000,
              }
            : undefined;
          for (const kind of ["file", "media-source"] as const) {
            try {
              const info = await capabilities.decodingInfo({
                type: kind,
                ...(videoConfig ? { video: videoConfig } : {}),
                ...(audioConfig ? { audio: audioConfig } : {}),
              });
              if (info?.supported) return { supported: true };
            } catch {
              // Try the other playback kind. A throw is not a yes.
            }
          }
          return { supported: false };
        }
      : undefined,
  }, { hdr: safari });
}

export function playThroughProjectionist(features: any) {
  return Boolean(features?.features?.play_through_projectionist);
}

export function engineSessionForPlayer(session: any) {
  if (!session?.playable || !session.master_url) return null;
  if (
    session.plan !== "remux" &&
    session.plan !== "direct" &&
    session.plan !== "audio" &&
    session.plan !== "try"
  ) {
    return null;
  }
  return { ...session, engine: true, stream_url: session.master_url };
}

/**
 * When the household switch is on, try an engine session. A playable remux,
 * direct, audio-only, or try plan uses that playlist. A plan the engine cannot
 * play, including source-transcode and the caption fallback, returns to the
 * Plex start. When the switch is off, the Plex start is the only call.
 */
/** How long an engine playlist may sit with no picture before the library path is tried. */
export const ENGINE_FIRST_FRAME_TIMEOUT_MS = 8000;

/**
 * Empty when the engine picture is already on screen, or when it is too early
 * to give up. A fatal player error before that picture, or a wait past the
 * timeout with no decoded frame, is the reason the library path should start.
 */
export function engineFirstFrameReason({
  elapsedMs = 0,
  videoWidth = 0,
  readyState = 0,
  fatalError = "",
  timeoutMs = ENGINE_FIRST_FRAME_TIMEOUT_MS,
}: {
  elapsedMs?: number;
  videoWidth?: number;
  readyState?: number;
  fatalError?: string;
  timeoutMs?: number;
} = {}): string {
  const width = Number(videoWidth);
  const ready = Number(readyState);
  if (Number.isFinite(width) && width > 0 && Number.isFinite(ready) && ready >= 2) return "";
  const fatal = String(fatalError || "").trim();
  if (fatal) return `Engine session failed before the first frame: ${fatal}`;
  const elapsed = Number(elapsedMs);
  const timeout = Number(timeoutMs);
  const limit = Number.isFinite(timeout) && timeout > 0 ? timeout : ENGINE_FIRST_FRAME_TIMEOUT_MS;
  if (Number.isFinite(elapsed) && elapsed >= limit) {
    const seconds = Math.max(1, Math.round(limit / 1000));
    return `Engine session had no first frame within ${seconds} seconds`;
  }
  return "";
}

/**
 * One library retry for an engine session that never shows a picture.
 * A second call with `retried` set does not stop or start anything again.
 */
export async function settleEngineFirstFrame({
  elapsedMs = 0,
  videoWidth = 0,
  readyState = 0,
  fatalError = "",
  retried = false,
  timeoutMs = ENGINE_FIRST_FRAME_TIMEOUT_MS,
  startLibrary,
  stopEngine,
  log = (reason: string) => {
    console.warn(reason);
  },
}: {
  elapsedMs?: number;
  videoWidth?: number;
  readyState?: number;
  fatalError?: string;
  retried?: boolean;
  timeoutMs?: number;
  startLibrary: () => Promise<any>;
  stopEngine: () => Promise<unknown>;
  log?: (reason: string) => void;
}): Promise<{ retried: boolean; session: any | null; reason: string }> {
  if (retried) return { retried: true, session: null, reason: "" };
  const reason = engineFirstFrameReason({
    elapsedMs,
    videoWidth,
    readyState,
    fatalError,
    timeoutMs,
  });
  if (!reason) return { retried: false, session: null, reason: "" };
  log(reason);
  try {
    await stopEngine();
  } catch {
    // The library session is the one retry. Stopping the engine is best-effort.
  }
  try {
    const session = await startLibrary();
    return { retried: true, session, reason };
  } catch (error) {
    const message = error instanceof Error ? error.message : "the library session did not start";
    log(`Engine first-frame fallback could not start the library session: ${message}`);
    return { retried: true, session: null, reason };
  }
}

export async function chooseWebPlayback({
  features,
  openEngine,
  startPlex,
}: {
  features: any;
  openEngine: () => Promise<any>;
  startPlex: () => Promise<any>;
}): Promise<any> {
  if (!playThroughProjectionist(features)) return startPlex();
  try {
    const engine = engineSessionForPlayer(await openEngine());
    if (engine) return engine;
  } catch {
    // The engine could not open a session. The Plex path still plays.
  }
  return startPlex();
}
