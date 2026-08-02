import assert from "node:assert/strict";
import test from "node:test";

import {
  ACCESS_REQUEST_ADMIN_PATH,
  INBOX_LIST_PARAMS,
  LIVE_CHANNELS_PATH,
  dedupeNotifications,
  dedupeRecommendations,
  digestBlurb,
  digestPicks,
  eventPrimaryCta,
  formatUnreadBadge,
  inboxCardCopy,
  inboxHeadline,
  normalizeRecommendation,
  nudgeCardNote,
  recommendationMediaTitle,
} from "./recommendationInbox.js";
import { canWatchOnPlex } from "./titleLinks.js";

test("inbox list params request unread-only so dismiss/clear-all persists on reopen", () => {
  assert.equal(INBOX_LIST_PARAMS.unread_only, true);
  assert.equal(INBOX_LIST_PARAMS.limit, 50);
});

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
  assert.equal(
    inboxHeadline([{ kind: "recommendation", payload: { intent: "watch_party" }, title: "Heat" }]),
    "Someone invited you to watch together",
  );
  assert.equal(
    inboxHeadline([{ kind: "library-share", title: "Noir night" }]),
    "Someone shared a saved page",
  );
  assert.equal(formatUnreadBadge(0), "");
  assert.equal(formatUnreadBadge(3), "3");
  assert.equal(formatUnreadBadge(120), "99+");
});

test("digest helpers prefer payload picks/blurb and fail-closed without ids", () => {
  const digest = {
    kind: "digest",
    title: "This week for you, Will",
    body: "Hi Will,\n\nLong email body with many lines.\n\nOpen CuratorX anytime.",
    payload: {
      newsletter: "weekly",
      blurb: "Scout here — rainy-night energy.",
      picks: [
        { title: "Heat", year: 1995, tmdb_id: 949, media_type: "movie", poster_url: "/p.jpg" },
        { title: "No id junk", year: 1999, media_type: "movie" },
        { title: "Library only", media_type: "show", rating_key: "rk-1" },
      ],
    },
  };
  const picks = digestPicks(digest);
  assert.equal(picks.length, 2);
  assert.equal(picks[0].title, "Heat");
  assert.equal(picks[1].rating_key, "rk-1");
  assert.equal(digestBlurb(digest), "Scout here — rainy-night energy.");
  const copy = inboxCardCopy(digest);
  assert.match(copy.lead, /This week for you/);
  assert.equal(copy.note, "Scout here — rainy-night energy.");
  assert.notEqual(copy.note, digest.body);
});

test("eventPrimaryCta wires access-request and live nudge paths", () => {
  assert.deepEqual(eventPrimaryCta({ kind: "access-request", payload: { access_request_id: "r1" } }, { role: "owner" }), {
    href: ACCESS_REQUEST_ADMIN_PATH,
    label: "Review request",
    testIdSuffix: "review-access",
  });
  assert.equal(
    eventPrimaryCta({ kind: "access-request", payload: { access_request_id: "r1" } }, { role: "member" }),
    null,
  );
  assert.deepEqual(
    eventPrimaryCta({
      kind: "nudge",
      payload: { live_channels: true, cta: "/live" },
    }),
    {
      href: LIVE_CHANNELS_PATH,
      label: "Open Live",
      testIdSuffix: "open-live",
    },
  );
});

test("nudgeCardNote tames enthusiast recently-watched dumps", () => {
  const note = nudgeCardNote({
    kind: "nudge",
    title: "Heat",
    body: "Scout here: you have to see Heat (1995). (reacting to what you recently watched: Blade Runner, Alien)\nBecause you recently watched Blade Runner\nOpen CuratorX when you’re ready.",
    payload: {
      enthusiast: true,
      pick_why: "Because you recently watched Blade Runner",
      recently_watched: [{ title: "Blade Runner" }, { title: "Alien" }],
    },
  });
  assert.equal(note, "Because you recently watched Blade Runner");
  assert.ok(!/Blade Runner, Alien/.test(note));
});

test("recommendationMediaTitle strips legacy precomposed notification titles", () => {
  assert.equal(
    recommendationMediaTitle({
      title: "qa-member recommended Family Guy (1999)",
      from_display_name: "qa-member",
      year: 1999,
    }),
    "Family Guy",
  );
  assert.equal(
    recommendationMediaTitle({
      title: "Family Guy",
      from_display_name: "qa-member",
      year: 1999,
    }),
    "Family Guy",
  );
  assert.equal(
    inboxCardCopy({
      kind: "recommendation",
      title: "qa-member recommended Family Guy (1999)",
      from_display_name: "qa-member",
      year: 1999,
    }).leadText,
    "qa-member recommended Family Guy (1999) for you",
  );
});
