export function selectActiveSyncJob(jobs, trackedId) {
  const syncJobs = (jobs || []).filter((job) => job.job_type === "library_sync");
  const running = syncJobs.find((job) => job.status === "running" || job.status === "queued");
  const tracked =
    (trackedId && syncJobs.find((job) => job.id === trackedId)) || syncJobs[0] || null;
  return {
    syncJobs,
    running: running || null,
    active: running || tracked,
  };
}

export function librarySyncStartedFeedback() {
  return {
    type: "success",
    message: "Library sync started. Progress appears below.",
  };
}

export function librarySyncFailedFeedback(error) {
  return {
    type: "error",
    message: error?.message || "Library sync failed to start.",
  };
}
