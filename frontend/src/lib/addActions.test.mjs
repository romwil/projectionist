import assert from "node:assert/strict";
import test from "node:test";

import {
  collectAddableFromMessage,
  lastAssistantHasTitleCards,
  normalizePendingTokens,
  summarizePendingTokenActions,
  tokenConfirmButtonLabel,
  tokenConfirmFailureMessage,
  tokenConfirmPrompt,
  tokenConfirmSuccessMessage,
} from "./addActions.js";

test("lastAssistantHasTitleCards detects in-chat bulk confirm host", () => {
  assert.equal(lastAssistantHasTitleCards([]), false);
  assert.equal(
    lastAssistantHasTitleCards([
      { role: "user", blocks: [{ type: "text", content: "hi" }] },
      { role: "assistant", blocks: [{ type: "text", content: "hello" }] },
    ]),
    false,
  );
  assert.equal(
    lastAssistantHasTitleCards([
      {
        role: "assistant",
        blocks: [
          { type: "text", content: "picks" },
          { type: "title_cards", items: [{ title: "Dumbo" }] },
        ],
      },
    ]),
    true,
  );
});

test("normalizePendingTokens accepts legacy string tokens", () => {
  assert.deepEqual(normalizePendingTokens(["abc", "def"]), [
    { token: "abc", action: "add_radarr" },
    { token: "def", action: "add_radarr" },
  ]);
});

test("normalizePendingTokens preserves action metadata", () => {
  assert.deepEqual(
    normalizePendingTokens([
      { token: "a", action: "remove_arr" },
      { token: "b", action: "remove_arr" },
    ]),
    [
      { token: "a", action: "remove_arr" },
      { token: "b", action: "remove_arr" },
    ],
  );
});

test("token confirm copy distinguishes removals from adds", () => {
  const removals = [
    { token: "a", action: "remove_arr" },
    { token: "b", action: "remove_arr" },
  ];
  assert.equal(tokenConfirmPrompt(2, removals), "Confirm all 2 proposed removals?");
  assert.equal(tokenConfirmButtonLabel(2, removals), "Confirm all 2 removals");
  assert.equal(tokenConfirmSuccessMessage(2, removals), "Confirmed 2 removals.");
  assert.equal(tokenConfirmFailureMessage(removals), "Could not confirm proposed removals.");

  const adds = [
    { token: "a", action: "add_radarr" },
    { token: "b", action: "add_sonarr" },
  ];
  assert.equal(tokenConfirmPrompt(2, adds), "Confirm all 2 proposed adds?");
  assert.equal(tokenConfirmButtonLabel(2, adds), "Confirm all 2 adds");
});

test("summarizePendingTokenActions counts mixed action types", () => {
  assert.deepEqual(
    summarizePendingTokenActions([
      { token: "a", action: "remove_arr" },
      { token: "b", action: "add_radarr" },
      { token: "c", action: "create_plex_collection" },
    ]),
    { add: 1, remove: 1, plex: 1, other: 0 },
  );
});

test("token confirm copy uses generic actions for mixed tokens", () => {
  const mixed = [
    { token: "a", action: "remove_arr" },
    { token: "b", action: "add_radarr" },
  ];
  assert.equal(tokenConfirmPrompt(2, mixed), "Confirm all 2 proposed actions?");
  assert.equal(tokenConfirmButtonLabel(2, mixed), "Confirm all 2");
  assert.equal(tokenConfirmSuccessMessage(2, mixed), "Confirmed 2 actions.");
  assert.equal(tokenConfirmFailureMessage(mixed), "Could not confirm proposed actions.");
});

test("token confirm copy for single removal and plex-only batches", () => {
  const oneRemoval = [{ token: "a", action: "remove_arr" }];
  assert.equal(tokenConfirmPrompt(1, oneRemoval), "Confirm all 1 proposed removal?");
  assert.equal(tokenConfirmSuccessMessage(1, oneRemoval), "Confirmed 1 removal.");

  const plexOnly = [
    { token: "a", action: "create_plex_collection" },
    { token: "b", action: "add_to_plex_collection" },
  ];
  assert.equal(tokenConfirmPrompt(2, plexOnly), "Confirm all 2 proposed Plex actions?");
  assert.equal(tokenConfirmButtonLabel(2, plexOnly), "Confirm all 2 Plex actions");
});

test("normalizePendingTokens drops empty entries", () => {
  assert.deepEqual(normalizePendingTokens([null, {}, { token: "ok", action: "remove_arr" }]), [
    { token: "ok", action: "remove_arr" },
  ]);
});

test("collectAddableFromMessage ignores empty placeholder cards", () => {
  const message = {
    role: "assistant",
    blocks: [
      {
        type: "title_cards",
        items: [
          { title: "Ready", media_type: "show", tvdb_id: 1 },
          { media_type: "show" },
          { title: "No TVDB", media_type: "show", tmdb_id: 2 },
        ],
      },
    ],
  };
  const { sonarr } = collectAddableFromMessage(message, { requestPath: "arr" });
  assert.equal(sonarr.length, 1);
  assert.equal(sonarr[0].title, "Ready");
});
