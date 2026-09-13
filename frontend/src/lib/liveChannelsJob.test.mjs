import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import {
  idleLiveJob,
  isLiveJobBusy,
  isLiveMutatingDisabled,
  liveJobRailCopy,
  liveJobSnippet,
  plexRebuildConfirmMessage,
} from "./liveChannelsJob.js";
import { readAllStyles } from "./readStyles.mjs";

const styles = readAllStyles();
const liveSection = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), "../pages/admin/LiveChannelsSection.jsx"),
  "utf8",
);

describe("liveChannelsJob", () => {
  it("treats idle / done / error as not busy", () => {
    assert.equal(isLiveJobBusy(idleLiveJob()), false);
    assert.equal(isLiveJobBusy({ phase: "done", busy: false }), false);
    assert.equal(isLiveJobBusy({ phase: "error", busy: false }), false);
    assert.equal(isLiveJobBusy({ kind: "plex_refresh", phase: "scanning", busy: true }), true);
  });

  it("builds the sticky rail sentence", () => {
    const copy = liveJobRailCopy({
      kind: "plex_refresh",
      phase: "scanning",
      percent: 50,
      message: "Scanning Tunarr channels in Plex…",
      busy: true,
    });
    assert.match(copy, /Working: Refreshing Plex map/);
    assert.match(copy, /Don’t start another Live job/);
    assert.match(copy, /Scanning Tunarr/);
    assert.equal(liveJobRailCopy(idleLiveJob()), "");
  });

  it("disables mutating actions but not status / show-steps", () => {
    const job = { kind: "publish", phase: "publishing", busy: true };
    assert.equal(isLiveMutatingDisabled(job, null), true);
    assert.equal(isLiveMutatingDisabled(idleLiveJob(), "attach-guide"), true);
    assert.equal(isLiveMutatingDisabled(idleLiveJob(), "status"), false);
    assert.equal(isLiveMutatingDisabled(idleLiveJob(), "attach"), false);
    assert.equal(isLiveMutatingDisabled(idleLiveJob(), null), false);
  });

  it("overview snippet is compact", () => {
    assert.match(
      liveJobSnippet({ kind: "plex_rebuild", percent: 30, busy: true, phase: "injecting" }),
      /Rebuilding tuner in Plex · 30%/,
    );
  });

  it("rebuild confirm warns about PMS hang and keeps OTA", () => {
    const msg = plexRebuildConfirmMessage();
    assert.match(msg, /Rebuild tuner in Plex/);
    assert.match(msg, /hang/i);
    assert.match(msg, /OTA/);
    assert.doesNotMatch(msg, /\bRepair\b/);
  });
});

describe("live channels admin chrome", () => {
  it("styles the job rail like service-card alerts, not a yellow slab", () => {
    assert.match(styles, /\.live-channels-job-rail\s*\{[^}]*position:\s*sticky/s);
    assert.match(styles, /\.live-channels-job-rail\s*\{[^}]*font-size:\s*14px/s);
    assert.match(styles, /\.live-channels-job-rail\s*\{[^}]*background:\s*var\(--surface-2\)/s);
    assert.match(styles, /\.service-card-actions\s*\{[^}]*display:\s*flex/s);
    assert.match(styles, /\.live-channels-infra-facts\s*\{[^}]*font-size:\s*14px/s);
    assert.match(styles, /\.live-channels-filler-add\s*\{/);
    assert.match(styles, /\.live-channels-step-label\s*\{[^}]*letter-spacing:\s*0\.1em/s);
  });

  it("mounts one Live Channels job rail (Overview keeps the compact snippet)", () => {
    const rails = liveSection.match(/<LiveJobRail\b/g) || [];
    assert.equal(rails.length, 1);
    assert.match(liveSection, /className="live-channels-filler-add"/);
    assert.match(liveSection, /className="ghost"\s+data-testid="live-channels-filler-add"/);
    assert.doesNotMatch(
      liveSection,
      /className="ghost"\s+data-testid="live-channels-rescan-filler"/,
    );
    assert.match(
      liveSection,
      /className="ghost"\s+data-testid=\{`live-channels-station-save-\$\{settingsStationId\}`\}/,
    );
    assert.match(
      liveSection,
      /className="primary"\s+data-testid=\{`live-channels-station-refill-cta-\$\{settingsStationId\}`\}/,
    );
  });
});
