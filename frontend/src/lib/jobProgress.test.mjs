import assert from "node:assert/strict";
import test from "node:test";

import {
  displayJobPercent,
  formatCountHint,
  formatLastSyncRelative,
  formatSyncJobDetails,
  formatSyncJobStatus,
  friendlyProgressMessage,
  parseLastSyncTimestamp,
  phaseLabel,
} from "./jobProgress.js";

test("friendlyProgressMessage maps snake_case keys", () => {
  assert.equal(friendlyProgressMessage("scanning_plex"), "Scanning Plex library…");
  assert.equal(friendlyProgressMessage("", "enriching"), "Enriching metadata…");
  assert.equal(friendlyProgressMessage("library_sync", "", "library_sync"), "Library sync");
});

test("friendlyProgressMessage keeps already-friendly API copy", () => {
  assert.equal(
    friendlyProgressMessage("Scanning movies… 120 of ~500", "movies"),
    "Scanning movies… 120 of ~500",
  );
  assert.equal(friendlyProgressMessage("Enriching metadata… 40 of ~200", "enriching"), "Enriching metadata… 40 of ~200");
});

test("phaseLabel uses novice titles", () => {
  assert.equal(phaseLabel("movies"), "Scanning movies");
  assert.equal(phaseLabel("tv"), "Scanning TV");
  assert.equal(phaseLabel("enriching"), "Enriching metadata");
});

test("displayJobPercent never hits 100 while running", () => {
  assert.equal(displayJobPercent({ status: "running", progress: { percent: 100 } }), 99);
  assert.equal(displayJobPercent({ status: "running", progress: { percent: 42 } }), 42);
  assert.equal(displayJobPercent({ status: "completed", progress: { percent: 100 } }), 100);
});

test("formatCountHint shows current of total", () => {
  assert.equal(formatCountHint({ current: 120, total: 500 }), "120 of ~500");
  assert.equal(formatCountHint({ current: 1, total: 1 }), "");
});

test("formatSyncJobStatus is hoster-friendly", () => {
  const line = formatSyncJobStatus({
    status: "running",
    job_type: "library_sync",
    progress: {
      message: "scanning_plex",
      phase: "tv",
      percent: 100,
      current: 200,
      total: 200,
    },
  });
  assert.match(line, /Scanning/i);
  assert.doesNotMatch(line, /scanning_plex/);
  assert.match(line, /\(99%\)/);
});

test("formatSyncJobDetails for Config card", () => {
  const running = formatSyncJobDetails({
    status: "running",
    progress: {
      phase: "movies",
      label: "Scanning movies",
      message: "Scanning movies… 120 of ~500",
      percent: 12,
      current: 120,
      total: 500,
    },
  });
  assert.equal(running.state, "running");
  assert.equal(running.headline, "Scanning movies");
  assert.match(running.detail, /120 of ~500/);
  assert.equal(running.percent, 12);

  const done = formatSyncJobDetails(
    { status: "completed" },
    { movies: 146, shows: 38 },
  );
  assert.equal(done.state, "completed");
  assert.match(done.headline, /Last synced just now/);
  assert.match(done.headline, /146 movies/);
});

test("parseLastSyncTimestamp reads sync_state JSON and bare epochs", () => {
  assert.equal(parseLastSyncTimestamp(null), null);
  assert.equal(parseLastSyncTimestamp(""), null);
  assert.equal(parseLastSyncTimestamp(1710000000), 1710000000);
  assert.equal(parseLastSyncTimestamp("1710000000.5"), 1710000000.5);
  assert.equal(
    parseLastSyncTimestamp(JSON.stringify({ items: 10, timestamp: 1710000000 })),
    1710000000,
  );
  assert.equal(parseLastSyncTimestamp({ finished_at: 1710000001 }), 1710000001);
  assert.equal(parseLastSyncTimestamp("{bad"), null);
});

test("formatLastSyncRelative never returns Invalid Date", () => {
  assert.equal(formatLastSyncRelative(null), "Never synced");
  assert.equal(formatLastSyncRelative(""), "Never synced");
  assert.equal(formatLastSyncRelative("{bad"), "Unknown");
  assert.equal(
    formatLastSyncRelative(JSON.stringify({ timestamp: Date.now() / 1000 })),
    "just now",
  );
  assert.doesNotMatch(
    formatLastSyncRelative(JSON.stringify({ timestamp: Date.now() / 1000 - 90 })),
    /Invalid Date/,
  );
});
