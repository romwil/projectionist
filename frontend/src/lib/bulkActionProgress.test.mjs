import assert from "node:assert/strict";
import test from "node:test";

import { bulkActionProgressView, shouldShowBulkActionProgress } from "./bulkActionProgress.js";

test("shows progress for multi-item work and asynchronous single-item work", () => {
  assert.equal(shouldShowBulkActionProgress({ total: 2 }), true);
  assert.equal(shouldShowBulkActionProgress({ total: 1, asynchronous: true }), true);
  assert.equal(shouldShowBulkActionProgress({ total: 1 }), false);
});

test("builds an accessible count and percent for bulk progress", () => {
  assert.deepEqual(
    bulkActionProgressView({ label: "Pinning to watchlist", current: 2, total: 5 }),
    { label: "Pinning to watchlist…", count: "2 / 5", percent: 40 },
  );
});
