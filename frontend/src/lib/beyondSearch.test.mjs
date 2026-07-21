import assert from "node:assert/strict";
import test from "node:test";

import { resolveAddCapability } from "./addActions.js";
import {
  BEYOND_STATUS,
  BEYOND_TURNSTYLE_TITLE,
  beyondAffordancePlacement,
  beyondItemBadge,
  beyondItemShowsAcquire,
  beyondStatusForError,
  beyondStatusForResult,
  beyondTurnstyleExpand,
  isBeyondItemAcquirable,
  isTmdbUnavailableError,
  normalizeExternalResults,
  shouldShowBeyondAffordance,
} from "./beyondSearch.js";

test("affordance visibility is gated on an active query", () => {
  assert.equal(shouldShowBeyondAffordance({ q: "" }), false);
  assert.equal(shouldShowBeyondAffordance({ q: "   " }), false);
  assert.equal(shouldShowBeyondAffordance({ q: "dune" }), true);
});

test("affordance hides once external search is unavailable", () => {
  assert.equal(shouldShowBeyondAffordance({ q: "dune", unavailable: true }), false);
});

test("placement is prominent with no library results, secondary otherwise", () => {
  assert.equal(beyondAffordancePlacement({ hasLibraryResults: false }), "prominent");
  assert.equal(beyondAffordancePlacement({ hasLibraryResults: true }), "secondary");
});

test("503 responses map to the unavailable state", () => {
  assert.equal(isTmdbUnavailableError({ status: 503 }), true);
  assert.equal(isTmdbUnavailableError({ status: 400 }), false);
  assert.equal(beyondStatusForError({ status: 503 }), BEYOND_STATUS.unavailable);
  assert.equal(beyondStatusForError({ status: 500 }), BEYOND_STATUS.error);
});

test("normalizeExternalResults tolerates missing fields", () => {
  assert.deepEqual(normalizeExternalResults(null), {
    items: [],
    total: 0,
    returned: 0,
    query: "",
  });
  const payload = {
    items: [{ title: "Dune", tmdb_id: 438631 }],
    total_matched: 12,
    returned: 1,
    query: "dune",
  };
  const normalized = normalizeExternalResults(payload);
  assert.equal(normalized.items.length, 1);
  assert.equal(normalized.total, 12);
  assert.equal(normalized.query, "dune");
});

test("results map to loaded when hits exist, empty otherwise", () => {
  assert.equal(beyondStatusForResult({ items: [{ tmdb_id: 1 }] }), BEYOND_STATUS.loaded);
  assert.equal(beyondStatusForResult({ items: [] }), BEYOND_STATUS.empty);
});

test("already-in-library and queued titles are de-duped (not acquirable)", () => {
  assert.equal(isBeyondItemAcquirable({ tmdb_id: 1 }), true);
  assert.equal(isBeyondItemAcquirable({ tmdb_id: 1, in_library: true }), false);
  assert.equal(isBeyondItemAcquirable({ tmdb_id: 1, already_queued: true }), false);
  assert.equal(isBeyondItemAcquirable({ tmdb_id: 1, in_radarr: true }), false);
  assert.equal(isBeyondItemAcquirable({ tmdb_id: 1, in_sonarr: true }), false);
});

test("badges reflect library/queue/new state", () => {
  assert.equal(beyondItemBadge({ in_library: true }), "In library");
  assert.equal(beyondItemBadge({ already_queued: true }), "In queue");
  assert.equal(beyondItemBadge({ in_sonarr: true }), "In queue");
  assert.equal(beyondItemBadge({ tmdb_id: 9 }), "New");
});

test("owners/members can acquire new titles; guests are info-only", () => {
  const item = { tmdb_id: 1, media_type: "movie" };
  const owner = resolveAddCapability({ role: "owner", requestPath: "arr" });
  const member = resolveAddCapability({ role: "member", requestPath: "seerr" });
  const guest = resolveAddCapability({ role: "guest" });

  assert.equal(beyondItemShowsAcquire(item, owner), true);
  assert.equal(beyondItemShowsAcquire(item, member), true);
  assert.equal(beyondItemShowsAcquire(item, guest), false);

  // Even owners get no acquire control for an already-owned title.
  assert.equal(beyondItemShowsAcquire({ ...item, in_library: true }, owner), false);
});

test("turnstyle expand is gated on displayable results and counts like the chat", () => {
  const none = beyondTurnstyleExpand([]);
  assert.equal(none.show, false);
  assert.equal(none.count, 0);
  assert.equal(none.title, BEYOND_TURNSTYLE_TITLE);

  // Bare objects with no title/id/rating_key are not displayable and don't count.
  const mixed = beyondTurnstyleExpand([
    { title: "Dune", tmdb_id: 438631 },
    { tmdb_id: 12345 },
    {},
    null,
  ]);
  assert.equal(mixed.show, true);
  assert.equal(mixed.count, 2);
  assert.equal(mixed.label, "Expand 2 titles in turnstyle view");
  assert.equal(mixed.title, BEYOND_TURNSTYLE_TITLE);
});

test("turnstyle expand accepts a custom overlay title", () => {
  const expand = beyondTurnstyleExpand([{ title: "Heat", tmdb_id: 949 }], {
    title: "Search results",
  });
  assert.equal(expand.title, "Search results");
  assert.equal(expand.count, 1);
  assert.equal(expand.label, "Expand 1 titles in turnstyle view");
});
