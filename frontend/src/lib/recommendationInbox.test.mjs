import assert from "node:assert/strict";
import test from "node:test";

import {
  dedupeNotifications,
  dedupeRecommendations,
  formatUnreadBadge,
  inboxHeadline,
  normalizeRecommendation,
} from "./recommendationInbox.js";
import { canWatchOnPlex } from "./titleLinks.js";

test("dedupeRecommendations returns the same visible records for a bulk dismissal", () => {
  const visible = dedupeRecommendations([
    { id: "short-note", media_type: "movie", tmdb_id: 78, title: "Blade Runner", message: "Watch this" },
    { id: "other-title", media_type: "movie", tmdb_id: 680, title: "Pulp Fiction" },
    { id: "rich-note", media_type: "movie", tmdb_id: 78, title: "Blade Runner", message: "The final cut is a great rainy-night watch." },
  ]);

  assert.deepEqual(
    visible.map((item) => item.id),
    ["rich-note", "other-title"],
  );
});

test("normalizeRecommendation marks rating-key recommendations as playable library titles", () => {
  assert.equal(
    canWatchOnPlex(normalizeRecommendation({ media_type: "movie", rating_key: "plex-949" })),
    true,
  );
  assert.equal(
    canWatchOnPlex(normalizeRecommendation({ media_type: "movie", rating_key: "plex-949", in_library: false })),
    false,
  );
});

test("dedupeNotifications keeps distinct kinds and ids", () => {
  const items = dedupeNotifications([
    { id: "a", kind: "arrival", title: "Arrival A" },
    { id: "a", kind: "arrival", title: "Arrival A duplicate id" },
    { id: "b", kind: "digest", title: "Weekly" },
  ]);
  assert.equal(items.length, 2);
  assert.equal(items[0].id, "a");
  assert.equal(items[1].kind, "digest");
});

test("inboxHeadline and formatUnreadBadge cover multi-kind inbox chrome", () => {
  assert.equal(inboxHeadline([]), "Inbox");
  assert.equal(inboxHeadline([{ kind: "arrival", title: "X" }]), "Something new arrived");
  assert.equal(inboxHeadline([{ kind: "digest" }, { kind: "nudge" }]), "2 new notifications");
  assert.equal(formatUnreadBadge(0), "");
  assert.equal(formatUnreadBadge(3), "3");
  assert.equal(formatUnreadBadge(120), "99+");
});
