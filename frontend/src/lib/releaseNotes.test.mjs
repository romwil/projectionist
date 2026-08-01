import assert from "node:assert/strict";
import test from "node:test";
import {
  LAST_SEEN_VERSION_KEY,
  RELEASE_JUMP_RECENT_LIMIT,
  allocateReleaseVersionJumps,
  compareSemver,
  fetchReleaseNotes,
  findReleaseByVersion,
  getLastSeenVersion,
  normalizeReleaseNotes,
  pickLatestRelease,
  plainChangelogText,
  setLastSeenVersion,
  shouldShowWhatsNew,
} from "./releaseNotes.js";

test("compareSemver orders patch/minor/major", () => {
  assert.ok(compareSemver("1.8.3", "1.8.2") > 0);
  assert.ok(compareSemver("1.8.2", "1.8.3") < 0);
  assert.equal(compareSemver("1.8.3", "1.8.3"), 0);
  assert.ok(compareSemver("2.0.0", "1.9.9") > 0);
  assert.ok(compareSemver("1.10.0", "1.9.0") > 0);
});

test("compareSemver tolerates v-prefix and junk", () => {
  assert.equal(compareSemver("v1.8.3", "1.8.3"), 0);
  assert.ok(compareSemver("1.8.3", "") > 0);
  assert.equal(compareSemver(null, null), 0);
});

test("shouldShowWhatsNew only after upgrade", () => {
  assert.equal(shouldShowWhatsNew("1.8.3", null), false);
  assert.equal(shouldShowWhatsNew("1.8.3", ""), false);
  assert.equal(shouldShowWhatsNew("1.8.3", "1.8.3"), false);
  assert.equal(shouldShowWhatsNew("1.8.3", "1.8.2"), true);
  assert.equal(shouldShowWhatsNew("1.8.2", "1.8.3"), false);
  assert.equal(shouldShowWhatsNew("", "1.8.2"), false);
});

test("last seen version storage helpers", () => {
  const store = new Map();
  const storage = {
    getItem: (k) => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => store.set(k, v),
  };
  assert.equal(getLastSeenVersion(storage), null);
  setLastSeenVersion("1.8.3", storage);
  assert.equal(store.get(LAST_SEEN_VERSION_KEY), "1.8.3");
  assert.equal(getLastSeenVersion(storage), "1.8.3");
});

test("normalizeReleaseNotes accepts payload or array", () => {
  assert.deepEqual(normalizeReleaseNotes(null), []);
  assert.deepEqual(
    normalizeReleaseNotes({ releases: [{ version: "1.0.0" }, { version: "" }] }),
    [{ version: "1.0.0" }],
  );
  assert.deepEqual(normalizeReleaseNotes([{ version: "1.2.0" }]), [{ version: "1.2.0" }]);
});

test("pickLatestRelease and findReleaseByVersion", () => {
  const releases = [
    { version: "1.8.1", date: "2026-07-16" },
    { version: "1.8.3", date: "2026-07-16" },
    { version: "1.8.2", date: "2026-07-16" },
  ];
  assert.equal(pickLatestRelease(releases).version, "1.8.3");
  assert.equal(findReleaseByVersion(releases, "1.8.2").version, "1.8.2");
  assert.equal(findReleaseByVersion(releases, "9.9.9"), null);
});

test("plainChangelogText strips light markdown", () => {
  assert.equal(plainChangelogText("**Scheduled Tasks** admin"), "Scheduled Tasks admin");
  assert.equal(plainChangelogText("use `enrich` flag"), "use enrich flag");
});

test("allocateReleaseVersionJumps keeps short histories as chips", () => {
  const releases = Array.from({ length: 4 }, (_, i) => ({ version: `1.0.${i}` }));
  const got = allocateReleaseVersionJumps(releases);
  assert.equal(got.mode, "chips");
  assert.deepEqual(got.recent, ["1.0.0", "1.0.1", "1.0.2", "1.0.3"]);
  assert.deepEqual(got.all, got.recent);
});

test("allocateReleaseVersionJumps switches long histories to picker + recent rail", () => {
  const releases = Array.from({ length: RELEASE_JUMP_RECENT_LIMIT + 5 }, (_, i) => ({
    version: `1.30.${RELEASE_JUMP_RECENT_LIMIT + 4 - i}`,
  }));
  const got = allocateReleaseVersionJumps(releases);
  assert.equal(got.mode, "picker");
  assert.equal(got.recent.length, RELEASE_JUMP_RECENT_LIMIT);
  assert.equal(got.all.length, RELEASE_JUMP_RECENT_LIMIT + 5);
  assert.equal(got.recent[0], got.all[0]);
  assert.equal(got.recent.at(-1), got.all[RELEASE_JUMP_RECENT_LIMIT - 1]);
  assert.ok(!got.recent.includes(got.all.at(-1)));
});

test("fetchReleaseNotes rejects non-OK and HTML responses", async () => {
  await assert.rejects(
    () =>
      fetchReleaseNotes(async () => ({
        ok: false,
        status: 404,
        headers: { get: () => "application/json" },
        json: async () => ({}),
      })),
    /404/,
  );

  await assert.rejects(
    () =>
      fetchReleaseNotes(async () => ({
        ok: true,
        status: 200,
        headers: { get: () => "text/html; charset=utf-8" },
        json: async () => ({ releases: [] }),
      })),
    /HTML response/,
  );

  const payload = { releases: [{ version: "1.8.7" }] };
  const got = await fetchReleaseNotes(async () => ({
    ok: true,
    status: 200,
    headers: { get: () => "application/json" },
    json: async () => payload,
  }));
  assert.equal(got.releases[0].version, "1.8.7");
});
