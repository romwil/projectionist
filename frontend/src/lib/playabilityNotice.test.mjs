import assert from "node:assert/strict";
import test from "node:test";

import { playabilityNotice } from "./playabilityNotice.ts";

const STOPPED = "The walk stopped early. Refresh to finish the library.";

test("a stopped walk still shows its message when profile rows are present", () => {
  const notice = playabilityNotice({
    complete: false,
    running: false,
    message: STOPPED,
    profiles: [{ profile: "safari", title_count: 2 }],
  });
  assert.equal(notice, STOPPED);
});

test("an empty library keeps its own message", () => {
  assert.equal(
    playabilityNotice({
      complete: true,
      running: false,
      message: "The library has no titles to check yet.",
      profiles: [],
    }),
    "The library has no titles to check yet.",
  );
  assert.equal(
    playabilityNotice({ complete: false, running: false, profiles: [] }),
    "No playability report yet. Refresh to walk the library.",
  );
});

test("a finished report with rows does not repeat the summary as an empty state", () => {
  assert.equal(
    playabilityNotice({
      complete: true,
      running: false,
      message: "Planned 4 titles from Plex metadata. Confirmed 4 with ffprobe.",
      profiles: [{ profile: "safari", title_count: 4 }],
    }),
    "",
  );
});
