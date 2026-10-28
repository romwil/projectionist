import assert from "node:assert/strict";
import test from "node:test";

import {
  librarySyncFailedFeedback,
  librarySyncStartedFeedback,
  selectActiveSyncJob,
} from "./configLibraryJobs.js";

test("selectActiveSyncJob prefers a running library_sync job", () => {
  const jobs = [
    { id: "old", job_type: "library_sync", status: "completed" },
    { id: "live", job_type: "library_sync", status: "running" },
    { id: "other", job_type: "live_publish", status: "running" },
  ];
  const picked = selectActiveSyncJob(jobs, "old");
  assert.equal(picked.running.id, "live");
  assert.equal(picked.active.id, "live");
  assert.equal(picked.syncJobs.length, 2);
});

test("selectActiveSyncJob falls back to the tracked id then the latest sync job", () => {
  const jobs = [
    { id: "a", job_type: "library_sync", status: "completed" },
    { id: "b", job_type: "library_sync", status: "completed" },
  ];
  assert.equal(selectActiveSyncJob(jobs, "b").active.id, "b");
  assert.equal(selectActiveSyncJob(jobs, "missing").active.id, "a");
  assert.equal(selectActiveSyncJob([], "x").active, null);
});

test("library sync feedback copy is stable", () => {
  assert.equal(librarySyncStartedFeedback().type, "success");
  assert.match(librarySyncStartedFeedback().message, /Library sync started/);
  assert.equal(librarySyncFailedFeedback({ message: "boom" }).message, "boom");
  assert.match(librarySyncFailedFeedback(null).message, /failed to start/);
});
