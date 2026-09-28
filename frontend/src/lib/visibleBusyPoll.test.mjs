import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import {
  BUSY_POLL_MS,
  IDLE_POLL_MS,
  jobIsActive,
  nextPollDelayMs,
  shouldPollChatJobs,
  shouldPollVisibleSection,
  snapshotIsBusy,
  startVisibleBusyPoll,
  syncToastIsOpen,
} from "./visibleBusyPoll.js";

const here = dirname(fileURLToPath(import.meta.url));
const configPage = readFileSync(join(here, "../pages/ConfigPage.jsx"), "utf8");
const libraries = readFileSync(join(here, "../pages/admin/LibrariesSection.jsx"), "utf8");
const app = readFileSync(join(here, "../App.jsx"), "utf8");

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

describe("visible busy poll helper", () => {
  it("uses 2s while busy and at least 8s when idle", () => {
    assert.equal(BUSY_POLL_MS, 2000);
    assert.ok(IDLE_POLL_MS >= 8000);
    assert.equal(nextPollDelayMs({ busy: true, hidden: false }), BUSY_POLL_MS);
    assert.ok(nextPollDelayMs({ busy: false, hidden: false }) >= 8000);
    assert.equal(nextPollDelayMs({ busy: false, hidden: false }), IDLE_POLL_MS);
  });

  it("pauses when the document is hidden, even if a section is busy", () => {
    assert.equal(nextPollDelayMs({ busy: true, hidden: true }), null);
    assert.equal(nextPollDelayMs({ busy: false, hidden: true }), null);
    assert.equal(shouldPollVisibleSection({ sectionVisible: true, hidden: true }), false);
    assert.equal(shouldPollVisibleSection({ sectionVisible: true, hidden: false }), true);
    assert.equal(shouldPollVisibleSection({ sectionVisible: false, hidden: false }), false);
  });

  it("drops chat-shell jobs unless a sync toast is open", () => {
    assert.equal(jobIsActive({ status: "running" }), true);
    assert.equal(jobIsActive({ status: "queued" }), true);
    assert.equal(jobIsActive({ status: "completed" }), false);
    assert.equal(syncToastIsOpen([]), false);
    assert.equal(syncToastIsOpen([{ status: "completed", job_type: "library_sync" }]), false);
    assert.equal(syncToastIsOpen([{ status: "running", job_type: "library_sync" }]), true);
    assert.equal(shouldPollChatJobs({ syncToastOpen: false, hidden: false }), false);
    assert.equal(shouldPollChatJobs({ syncToastOpen: true, hidden: false }), true);
    assert.equal(shouldPollChatJobs({ syncToastOpen: true, hidden: true }), false);
    assert.equal(snapshotIsBusy({ busy: true }), true);
    assert.equal(snapshotIsBusy({ busy: false }), false);
  });

  it("ticks immediately when visible, then idles at the idle delay", async () => {
    let hidden = false;
    const ticks = [];
    const stop = startVisibleBusyPoll(
      () => {
        ticks.push("tick");
      },
      {
        isBusy: () => false,
        isHidden: () => hidden,
        busyMs: 15,
        idleMs: 40,
        addVisibilityListener: () => () => {},
      },
    );
    await wait(5);
    assert.equal(ticks.length, 1);
    await wait(50);
    assert.ok(ticks.length >= 2);
    stop();
    const afterStop = ticks.length;
    await wait(50);
    assert.equal(ticks.length, afterStop);
  });

  it("does not tick while hidden and resumes on visibilitychange", async () => {
    let hidden = true;
    let onVisibility = null;
    const ticks = [];
    const stop = startVisibleBusyPoll(
      () => {
        ticks.push("tick");
      },
      {
        isBusy: () => true,
        isHidden: () => hidden,
        busyMs: 15,
        idleMs: 40,
        addVisibilityListener: (handler) => {
          onVisibility = handler;
          return () => {
            onVisibility = null;
          };
        },
      },
    );
    await wait(20);
    assert.equal(ticks.length, 0);
    hidden = false;
    onVisibility();
    await wait(5);
    assert.equal(ticks.length, 1);
    stop();
  });
});

describe("visible busy poll wiring", () => {
  it("gates ConfigPage library polls to the libraries section", () => {
    assert.match(configPage, /startVisibleBusyPoll/);
    assert.match(configPage, /section !== "libraries"/);
    assert.match(configPage, /IDLE_POLL_MS|isBusy:/);
    assert.doesNotMatch(configPage, /setInterval\(pollSyncJobs,\s*2000\)/);
    assert.doesNotMatch(configPage, /setInterval\(pollSonarrMissing,\s*2000\)/);
    assert.doesNotMatch(configPage, /setInterval\(pollRadarrRegister,\s*2000\)/);
  });

  it("backs off Investigate instead of a 2s forever interval", () => {
    assert.match(libraries, /startVisibleBusyPoll/);
    assert.doesNotMatch(libraries, /setInterval\(poll,\s*2000\)/);
  });

  it("drops chat-shell listJobs unless a sync toast is open", () => {
    assert.match(app, /syncToastIsOpen/);
    assert.match(app, /startVisibleBusyPoll/);
    assert.doesNotMatch(app, /setInterval\(refreshJobs,\s*5000\)/);
  });
});
