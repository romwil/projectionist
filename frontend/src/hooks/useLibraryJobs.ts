import { useEffect, useRef, useState } from "react";
import { api, listJobs } from "../api/client";
import type {Job, JsonObject, JsParam} from "../api/types";
import {
  librarySyncFailedFeedback,
  librarySyncStartedFeedback,
  selectActiveSyncJob,
} from "../lib/configLibraryJobs.js";
import { jobIsActive, startVisibleBusyPoll } from "../lib/visibleBusyPoll.js";

/** @param {{ enabled?: boolean, setLibraryStats?: Function, setLibraryHealth?: Function, setActionFeedback?: Function }} [opts] */
export default function useLibraryJobs({
  enabled = true,
  setLibraryStats,
  setLibraryHealth,
  setActionFeedback,
}: {
  enabled?: boolean;
  setLibraryStats?: (data: JsParam) => void;
  setLibraryHealth?: (data: JsParam) => void;
  setActionFeedback?: (key: string, value: unknown) => void;
} = {}) {
  const [activeSyncJob, setActiveSyncJob] = useState<Job | null>(null);
  const [syncingLibrary, setSyncingLibrary] = useState(false);
  const [trackedSyncJobId, setTrackedSyncJobId] = useState<string | null>(null);
  const trackedSyncJobIdRef = useRef<string | null>(null);
  const syncWasRunningRef = useRef(false);
  const syncingLibraryRef = useRef(false);

  useEffect(() => {
    syncingLibraryRef.current = syncingLibrary;
  }, [syncingLibrary]);

  useEffect(() => {
    if (!enabled) return undefined;
    let cancelled = false;

    async function pollSyncJobs() {
      try {
        const jobs = await listJobs();
        if (cancelled) return;
        const { running, active } = selectActiveSyncJob(jobs, trackedSyncJobIdRef.current);
        setActiveSyncJob(active);
        const isRunning = Boolean(running);
        setSyncingLibrary(isRunning);
        if (syncWasRunningRef.current && !isRunning && active?.status === "completed") {
          api("/library/stats")
            .then((data) => setLibraryStats?.(data))
            .catch(() => {});
          api("/library/health")
            .then((data) => setLibraryHealth?.(data))
            .catch(() => {});
        }
        syncWasRunningRef.current = isRunning;
      } catch {
        if (!cancelled) setSyncingLibrary(false);
      }
    }

    const stop = startVisibleBusyPoll(pollSyncJobs, {
      isBusy: () => Boolean(syncingLibraryRef.current || syncWasRunningRef.current),
      isEnabled: () => !cancelled,
    });
    return () => {
      cancelled = true;
      stop();
    };
  }, [enabled, setLibraryHealth, setLibraryStats]);

  async function handleLibrarySync() {
    setSyncingLibrary(true);
    setActionFeedback?.("library-sync", null);
    try {
      const job = await api<Job>("/library/sync", { method: "POST" });
      trackedSyncJobIdRef.current = job.id ?? null;
      setTrackedSyncJobId(job.id ?? null);
      setActiveSyncJob(job);
      syncWasRunningRef.current = jobIsActive(job);
      const started = librarySyncStartedFeedback();
      setActionFeedback?.("library-sync", started);
    } catch (error) {
      setSyncingLibrary(false);
      const failed = librarySyncFailedFeedback(error);
      setActionFeedback?.("library-sync", failed);
    }
  }

  return {
    syncingLibrary,
    handleLibrarySync,
    activeSyncJob,
    trackedSyncJobId,
  };
}
