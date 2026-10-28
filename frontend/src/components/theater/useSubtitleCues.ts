import { useEffect, useState } from "react";
import { parseVtt, SUBTITLE_FETCH_FAILED } from "../../lib/subtitleCues.js";
import type { JsParam } from "../../api/types";

type SubtitleCueState = "idle" | "loading" | "ready" | "error";

type SubtitleCueResult = {
  url: string;
  cues: JsParam[];
  state: SubtitleCueState;
  error: string;
};

export type SubtitleCues = {
  cues: JsParam[];
  state: SubtitleCueState;
  error: string;
};

/**
 * Fetch + parse one proxied subtitle track. Same-origin, cookie-authed — the
 * browser never sees a Plex URL or token.
 * @param url `/api/library/items/:key/subtitles/:id/file` or ""
 */
export default function useSubtitleCues(url: string): SubtitleCues {
  const [result, setResult] = useState<SubtitleCueResult>({
    url: "",
    cues: [],
    state: "idle",
    error: "",
  });

  useEffect(() => {
    if (!url) return undefined;
    let cancelled = false;
    const controller = new AbortController();
    (async () => {
      try {
        const response = await fetch(url, { credentials: "include", signal: controller.signal });
        if (!response.ok) {
          throw new Error(SUBTITLE_FETCH_FAILED);
        }
        const cues = parseVtt(await response.text());
        if (cancelled) return;
        if (!cues.length) {
          setResult({ url, cues: [], state: "error", error: SUBTITLE_FETCH_FAILED });
          return;
        }
        setResult({ url, cues, state: "ready", error: "" });
      } catch (error: unknown) {
        if (cancelled || (error as { name?: string })?.name === "AbortError") return;
        setResult({
          url,
          cues: [],
          state: "error",
          error: (error as { message?: string })?.message || SUBTITLE_FETCH_FAILED,
        });
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
