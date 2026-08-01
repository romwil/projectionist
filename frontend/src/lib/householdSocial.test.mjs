import assert from "node:assert/strict";
import test from "node:test";

import {
  callbackTitleDeepLink,
  defaultWatchPartyNote,
  digInRecommendCtaLabel,
  isWatchPartyRecommendation,
  libraryShareFlash,
  librarySharePrivacyNote,
  normalizeRecommendIntent,
  recommendModalCopy,
  recommendationIntent,
} from "./householdSocial.js";

test("normalizeRecommendIntent accepts watch-party aliases", () => {
  assert.equal(normalizeRecommendIntent("watch_party"), "watch_party");
  assert.equal(normalizeRecommendIntent("Watch Together"), "watch_party");
  assert.equal(normalizeRecommendIntent("recommend"), "recommend");
  assert.equal(normalizeRecommendIntent(""), "recommend");
});

test("recommendationIntent reads payload.intent", () => {
  assert.equal(
    recommendationIntent({ kind: "recommendation", payload: { intent: "watch_party" } }),
    "watch_party",
  );
  assert.equal(isWatchPartyRecommendation({ intent: "recommend" }), false);
  assert.equal(isWatchPartyRecommendation({ payload: { intent: "watch_party" } }), true);
});

test("recommend modal + dig-in CTA copy for watch party", () => {
  assert.equal(digInRecommendCtaLabel("watch_party"), "Watch together");
  assert.equal(digInRecommendCtaLabel("recommend"), "Recommend");
  assert.equal(recommendModalCopy("watch_party").sendLabel, "Invite to watch");
  assert.equal(recommendModalCopy("recommend").eyebrow, "Recommend to…");
  assert.match(defaultWatchPartyNote("Heat"), /Heat/);
});

test("callbackTitleDeepLink builds title identity from memory metadata", () => {
  const item = callbackTitleDeepLink({
    kind: "callback",
    text: "the bleak UK comedy bit",
    metadata: { title: "The Office", media_type: "show", tmdb_id: 2236, year: 2001 },
  });
  assert.equal(item.title, "The Office");
  assert.equal(item.media_type, "show");
  assert.equal(item.tmdb_id, 2236);
  assert.equal(callbackTitleDeepLink({ text: "no title meta" }), null);
});

test("library share flash + privacy note stay account-scoped", () => {
  assert.match(libraryShareFlash("copy"), /household/i);
  assert.match(librarySharePrivacyNote(), /never a public/i);
  assert.equal(libraryShareFlash("save"), "Saved to your private library.");
});
