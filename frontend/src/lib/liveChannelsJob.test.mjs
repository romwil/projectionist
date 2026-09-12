import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  idleLiveJob,
  isLiveJobBusy,
  isLiveMutatingDisabled,
  liveJobRailCopy,
  liveJobSnippet,
  plexRebuildConfirmMessage,
} from "./liveChannelsJob.js";

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
