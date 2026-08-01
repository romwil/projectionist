/** Pure helpers for Projectionist `/live` watch + guide. */

import { ROUTES } from "./backNav.js";

export function liveStreamUrl(channelId) {
  const id = encodeURIComponent(String(channelId || "").trim());
  if (!id) return "";
  return `/api/live-channels/stream/${id}/index.m3u8`;
}

export function liveWatchHref(channelId, { popout = false } = {}) {
  const params = new URLSearchParams();
  const id = String(channelId || "").trim();
  if (id) params.set("channel", id);
  const path = popout ? ROUTES.liveWatch : ROUTES.live;
  const qs = params.toString();
  return qs ? `${path}?${qs}` : path;
}

/** Opener guide URL after pop-out — keeps channel selected without starting HLS. */
export function liveGuideHref(channelId) {
  const params = new URLSearchParams();
  const id = String(channelId || "").trim();
  if (id) params.set("channel", id);
  params.set("mode", "guide");
  return `${ROUTES.live}?${params.toString()}`;
}

/**
 * Single-session pop-out handoff: TV window URL + opener guide URL.
 * Caller must window.open(popoutHref) synchronously, then navigate opener to guideHref
 * so the original LivePlayer unloads before the pop-out tunes.
 */
export function popoutHandoff(channelId) {
  const id = String(channelId || "").trim();
  return {
    popoutHref: liveWatchHref(id, { popout: true }),
    guideHref: liveGuideHref(id),
  };
}

/** True when a click landed on OSD / chrome controls (not the video stage). */
export function isLivePlayerChromeTarget(target) {
  if (!target || typeof target.closest !== "function") return false;
  return Boolean(
    target.closest(
      "button, a, input, select, textarea, [role='button'], .live-osd-actions, .live-cc-picker, .live-chrome",
    ),
  );
}

/**
 * Start playback with muted-first fallback (pop-out / Safari autoplay).
 * @param {HTMLMediaElement|null|undefined} video
 * @returns {Promise<"playing"|"ready"|"idle">}
 */
export async function tryPlayLiveVideo(video) {
  if (!video) return "idle";
  try {
    await video.play();
    return "playing";
  } catch {
    const preferUnmuted = !video.muted;
    try {
      video.muted = true;
      await video.play();
      if (preferUnmuted) {
        video.muted = false;
      }
      return "playing";
    } catch {
      return "ready";
    }
  }
}

/**
 * Toggle pause ↔ play for live HLS. Pause freezes; play resumes (caller may startLoad).
 * @param {HTMLMediaElement|null|undefined} video
 * @returns {Promise<"playing"|"paused"|"ready"|"idle">}
 */
export async function toggleLiveVideoPlayback(video) {
  if (!video) return "idle";
  if (!video.paused) {
    video.pause();
    return "paused";
  }
  return tryPlayLiveVideo(video);
}

export function formatClock(seconds) {
  if (seconds == null || !Number.isFinite(Number(seconds))) return "";
  const total = Math.max(0, Math.round(Number(seconds)));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h > 0) {
    return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  }
  return `${m}:${String(s).padStart(2, "0")}`;
}

export function formatWallTime(epochSeconds) {
  if (epochSeconds == null || !Number.isFinite(Number(epochSeconds))) return "";
  try {
    return new Date(Number(epochSeconds) * 1000).toLocaleTimeString([], {
      hour: "numeric",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}

/**
 * @param {object|null|undefined} channel
 * @param {number} [nowMs]
 */
export function buildOsdModel(channel, nowMs = Date.now()) {
  if (!channel || typeof channel !== "object") return null;
  const now = channel.now && typeof channel.now === "object" ? channel.now : null;
  const next = channel.next && typeof channel.next === "object" ? channel.next : null;
  const nowSec = nowMs / 1000;
  let secondsElapsed = now?.seconds_elapsed ?? null;
  let secondsRemaining = now?.seconds_remaining ?? null;
  let percent = now?.percent ?? null;
  const start = now?.started_at ?? now?.start ?? null;
  const end = now?.ends_at ?? now?.stop ?? null;
  if (start != null && end != null && Number.isFinite(Number(start)) && Number.isFinite(Number(end))) {
    const duration = Math.max(0, Number(end) - Number(start));
    if (duration > 0) {
      secondsElapsed = Math.max(0, Math.min(duration, nowSec - Number(start)));
      secondsRemaining = Math.max(0, Number(end) - nowSec);
      percent = Math.max(0, Math.min(100, (secondsElapsed / duration) * 100));
    }
  }
  const durationSeconds =
    start != null && end != null ? Math.max(0, Number(end) - Number(start)) : null;
  return {
    id: String(channel.id || ""),
    number: channel.number == null ? null : Number(channel.number),
    name: String(channel.name || "Channel").trim() || "Channel",
    iconUrl: String(channel.icon_url || "").trim(),
    title: String(now?.title || "").trim(),
    episode: String(now?.episode_title || "").trim(),
    rating: String(now?.content_rating || "").trim(),
    isFlex: Boolean(now?.is_flex),
    nextTitle: String(next?.title || "").trim(),
    nextStart: next?.started_at ?? next?.start ?? null,
    secondsElapsed,
    secondsRemaining,
    durationSeconds,
    percent,
    isPaused: Boolean(now?.is_paused),
  };
}

/**
 * Normalize guide API into EPG rows with programs.
 * @param {object|null|undefined} snapshot
 */
export function normalizeGuide(snapshot) {
  if (!snapshot || typeof snapshot !== "object" || !snapshot.enabled) return null;
  const generatedAt = Number(snapshot.generated_at) || Date.now() / 1000;
  const windowSeconds = Number(snapshot.window_seconds) || 6 * 3600;
  const channels = (Array.isArray(snapshot.channels) ? snapshot.channels : [])
    .map((channel) => {
      if (!channel || typeof channel !== "object") return null;
      const programs = (Array.isArray(channel.programs) ? channel.programs : [])
        .map((program) => {
          if (!program || typeof program !== "object") return null;
          const title = String(program.title || "").trim();
          if (!title) return null;
          return {
            title,
            episode: String(program.episode_title || "").trim(),
            rating: String(program.content_rating || "").trim(),
            start: program.started_at ?? program.start ?? null,
            stop: program.ends_at ?? program.stop ?? null,
            isFlex: Boolean(program.is_flex),
          };
        })
        .filter(Boolean);
      // Ensure now/next appear even when programs list is thin.
      if (!programs.length && channel.now) {
        const now = channel.now;
        programs.push({
          title: String(now.title || "").trim(),
          episode: String(now.episode_title || "").trim(),
          rating: String(now.content_rating || "").trim(),
          start: now.started_at ?? now.start ?? null,
          stop: now.ends_at ?? now.stop ?? null,
          isFlex: Boolean(now.is_flex),
        });
      }
      return {
        id: String(channel.id || ""),
        name: String(channel.name || "Channel").trim() || "Channel",
        number: channel.number == null ? null : Number(channel.number),
        iconUrl: String(channel.icon_url || "").trim(),
        now: channel.now || null,
        next: channel.next || null,
        programs,
      };
    })
    .filter(Boolean);

  return {
    enabled: true,
    ready: Boolean(snapshot.ready) && channels.length > 0,
    reason: String(snapshot.reason || ""),
    generatedAt,
    windowStart: generatedAt,
    windowEnd: generatedAt + windowSeconds,
    hours: Number(snapshot.hours) || windowSeconds / 3600,
    watchHint: String(snapshot.watch_hint || snapshot.plex_hint || ""),
    channels,
  };
}

/** Pixel layout for a program cell in a horizontal EPG. */
export function programCellStyle(program, windowStart, windowEnd, pxPerHour) {
  const start = Number(program?.start);
  const stop = Number(program?.stop);
  if (!Number.isFinite(start) || !Number.isFinite(stop) || stop <= start) {
    return { display: "none" };
  }
  const clampedStart = Math.max(start, windowStart);
  const clampedStop = Math.min(stop, windowEnd);
  if (clampedStop <= clampedStart) return { display: "none" };
  const leftHours = (clampedStart - windowStart) / 3600;
  const widthHours = (clampedStop - clampedStart) / 3600;
  return {
    left: `${leftHours * pxPerHour}px`,
    width: `${Math.max(48, widthHours * pxPerHour)}px`,
  };
}

export function adjacentChannelId(channels, currentId, delta) {
  const list = Array.isArray(channels) ? channels : [];
  if (!list.length) return "";
  const idx = list.findIndex((c) => c.id === currentId);
  if (idx < 0) return list[0]?.id || "";
  const next = Math.max(0, Math.min(list.length - 1, idx + delta));
  return list[next]?.id || "";
}
