import { useEffect, useState } from "react";
import { parseVtt, SUBTITLE_FETCH_FAILED } from "../../lib/subtitleCues.js";

/**
 * Fetch + parse one proxied subtitle track. Same-origin, cookie-authed — the
 * browser never sees a Plex URL or token.
 * @param {string} url `/api/library/items/:key/subtitles/:id/file` or ""
 * @returns {{ cues: object[], state: "idle"|"loading"|"ready"|"error", error: string }}
 */
export default function useSubtitleCues(url) {
  const [result, setResult] = useState({ url: "", cues: [], state: "idle", error: "" });

  useEffect(() => {
    if (!url) return undefined;
    let cancelled = false;
    const controller = new AbortController();
    (async () => {
      try {
        const response = await fetch(url, { credentials: "include", signal: controller.signal });
        if (!response.ok) {
          let detail = "";
          try {
            detail = JSON.parse(await response.text())?.detail || "";
          } catch {
            // non-JSON error body
          }
          throw new Error(typeof detail === "string" && detail ? detail : SUBTITLE_FETCH_FAILED);
        }
        const cues = parseVtt(await response.text());
        if (cancelled) return;
        if (!cues.length) {
          setResult({ url, cues: [], state: "error", error: "This subtitle track came back empty from Plex." });
          return;
        }
        setResult({ url, cues, state: "ready", error: "" });
      } catch (error) {
        if (cancelled || error?.name === "AbortError") return;
        setResult({ url, cues: [], state: "error", error: error?.message || SUBTITLE_FETCH_FAILED });
      }
    })();
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [url]);

  if (!url) return { cues: [], state: "idle", error: "" };
  if (result.url !== url) return { cues: [], state: "loading", error: "" };
  return { cues: result.cues, state: result.state, error: result.error };
}
