/** Web player gate for Play through Projectionist (ENG-007). */

export type WebPlaybackProfile = {
  id: string;
  containers: string[];
  video: { codec: string; max_level: string }[];
  audio: string[];
  captions: string[];
};

type CanPlay = (mimeType: string) => boolean;

const HEVC = ['video/mp4; codecs="hvc1.1.6.L93.B0"', 'video/mp4; codecs="hev1.1.6.L93.B0"'];
const H264 = ['video/mp4; codecs="avc1.42E01E"', 'video/mp4; codecs="avc1.640028"'];

function anySupported(canPlay: CanPlay, types: string[]) {
  return types.some((type) => canPlay(type));
}

/** Profile from MediaSource.isTypeSupported / canPlayType. Never a user-agent guess. */
export function browserPlaybackProfile(canPlay: CanPlay): WebPlaybackProfile {
  const video: { codec: string; max_level: string }[] = [];
  if (anySupported(canPlay, HEVC)) video.push({ codec: "hevc", max_level: "5.1" });
  if (anySupported(canPlay, H264)) video.push({ codec: "h264", max_level: "5.2" });
  if (!video.length) video.push({ codec: "h264", max_level: "5.2" });
  const audio = ["aac"];
  if (canPlay('audio/mp4; codecs="ac-3"')) audio.push("ac3");
  if (canPlay('audio/mp4; codecs="ec-3"')) audio.push("eac3");
  return {
    id: "web",
    containers: ["mp4", "hls-fmp4"],
    video,
    audio,
    captions: ["webvtt"],
  };
}

export function playThroughProjectionist(features: any) {
  return Boolean(features?.features?.play_through_projectionist);
}

export function engineSessionForPlayer(session: any) {
  if (!session?.playable || !session.master_url) return null;
  if (session.plan !== "remux" && session.plan !== "direct") return null;
  return { ...session, engine: true, stream_url: session.master_url };
}

/**
 * When the household switch is on, try an engine session. A plan the engine
 * cannot play, including the caption fallback, returns to the Plex start.
 * When the switch is off, the Plex start is the only call.
 */
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
