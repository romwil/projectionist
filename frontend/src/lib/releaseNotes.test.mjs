import assert from "node:assert/strict";
import test from "node:test";
import {
  LAST_SEEN_VERSION_KEY,
  compareSemver,
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
