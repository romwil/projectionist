import { useCallback, useRef, useState } from "react";
import { cancelLibraryRemoval } from "../api/client.js";
import type {ApiError, JsonObject, JsParam} from "../api/types";
import { createId } from "../lib/id.js";
import {
  applyRemovalProgressEvent,
  createRemovalSession,
  failRemovalSession,
  finishRemovalSession,
} from "../lib/removalProgress.js";

/**
 * Opens the removal summary as soon as a delete starts and fills it per title.
 * Cancel asks the server to skip titles that have not started.
 */
export function useRemovalProgressSession() {
  const [summary, setSummary] = useState<JsParam | null>(null);
  const [cancelRequested, setCancelRequested] = useState(false);
  const summaryRef = useRef<JsParam | null>(null);
  const runIdRef = useRef("");

  const dismiss = useCallback(() => {
    summaryRef.current = null;
    runIdRef.current = "";
    setCancelRequested(false);
    setSummary(null);
  }, []);

  const cancelRemaining = useCallback(() => {
    const runId = runIdRef.current;
    if (!runId || summaryRef.current?.phase === "done") return;
    setCancelRequested(true);
    cancelLibraryRemoval(runId).catch(() => {
      setCancelRequested(false);
    });
  }, []);

  const run = useCallback(async ({
    mode,
    targets,
    stream,
  }: {
    mode?: string;
    targets?: unknown[];
    stream: (opts: { onEvent: (event: JsParam) => void; runId: string }) => Promise<JsParam | null | undefined>;
  }) => {
    const runId = createId();
    runIdRef.current = runId;
    setCancelRequested(false);
    const initial = createRemovalSession({ mode, targets });
    summaryRef.current = initial;
    setSummary(initial);
    const onEvent = (event: JsParam) => {
      const next = applyRemovalProgressEvent(summaryRef.current, event);
      summaryRef.current = next;
      setSummary(next);
    };
    try {
      const result = await stream({ onEvent, runId });
      const finished = finishRemovalSession(summaryRef.current, result, {
        stopped: Boolean(result?.cancelled),
      });
      summaryRef.current = finished;
      setSummary(finished);
      return finished.result;
    } catch (error: unknown) {
      if ((error as ApiError)?.name === "AbortError") {
        const finished = finishRemovalSession(summaryRef.current, null, { stopped: true });
        summaryRef.current = finished;
        setSummary(finished);
        return finished.result;
      }
      const failed = failRemovalSession(summaryRef.current, error);
      summaryRef.current = failed;
      setSummary(failed);
      throw error;
    }
  }, []);

  return { summary, run, cancelRemaining, dismiss, cancelRequested };
}
