import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  LIBRARIES_HUB_TABS,
  buildLibrariesAttention,
  countPathConflicts,
  isSyncStale,
  resolveLibrariesHubTab,
} from "./librariesHub.ts";

describe("librariesHub", () => {
  it("exposes sticky subnav tabs in stewardship order", () => {
    assert.deepEqual(
      LIBRARIES_HUB_TABS.map((tab) => tab.id),
      ["sync", "arr", "repair", "rematch", "identify", "plex"],
    );
    assert.equal(LIBRARIES_HUB_TABS.find((tab) => tab.id === "plex")?.label, "Plex");
  });

  it("counts path conflicts and routes attention to Repair", () => {
    const job = {
      items: [
        { id: 1, outcome: "path_conflict" },
        { id: 2, outcome: "registered" },
        { id: 3, outcome: "path_conflict" },
      ],
    };
    assert.equal(countPathConflicts(job), 2);
    const attention = buildLibrariesAttention({
      libraryStats: { last_sync: new Date().toISOString() },
      radarrRegister: job,
    });
    assert.equal(attention[0]?.id, "path-conflicts");
    assert.equal(attention[0]?.tabId, "repair");
    assert.equal(attention[0]?.panelId, "libraries-panel-repair");
    assert.match(attention[0]?.title || "", /2 path conflicts/);
  });

  it("flags never-synced and week-old sync as stale → Sync", () => {
    assert.equal(isSyncStale(null), true);
    assert.equal(isSyncStale({ last_sync: null }), true);
    const weekAgo = Date.now() - 8 * 24 * 60 * 60 * 1000;
    assert.equal(isSyncStale({ last_sync: new Date(weekAgo).toISOString() }), true);
    assert.equal(isSyncStale({ last_sync: new Date().toISOString() }), false);

    const stale = buildLibrariesAttention({
      libraryStats: { last_sync: new Date(weekAgo).toISOString() },
    });
    assert.equal(stale.some((item) => item.id === "stale-sync" && item.tabId === "sync"), true);

    const never = buildLibrariesAttention({ libraryStats: null });
    assert.equal(never.some((item) => item.id === "stale-sync"), true);
  });

  it("routes failed sync and Sonarr failures to the right tabs", () => {
    const failedSync = buildLibrariesAttention({
      libraryStats: { last_sync: new Date().toISOString() },
      activeSyncJob: { status: "failed", error: "timeout" },
    });
    assert.equal(failedSync[0]?.id, "sync-failed");
    assert.equal(failedSync[0]?.tabId, "sync");

    const sonarr = buildLibrariesAttention({
      libraryStats: { last_sync: new Date().toISOString() },
      sonarrMissing: { execution: { failed: 2, last_error: "rate limited" } },
    });
    assert.equal(sonarr.some((item) => item.id === "sonarr-failures" && item.tabId === "arr"), true);
  });

  it("resolves hashes and aliases to hub tabs", () => {
    assert.equal(resolveLibrariesHubTab(""), "sync");
    assert.equal(resolveLibrariesHubTab("#rematch-studio"), "rematch");
    assert.equal(resolveLibrariesHubTab("episode-investigate"), "identify");
    assert.equal(resolveLibrariesHubTab("libraries-panel-arr"), "arr");
    assert.equal(resolveLibrariesHubTab("plex-mapping"), "plex");
    assert.equal(resolveLibrariesHubTab("path-conflict"), "repair");
  });
});
