import assert from "node:assert/strict";
import test from "node:test";

import {
  POP_OUT_OF_WINDOW_LABEL,
  SHRINK_ONTO_PAGE_LABEL,
  playbackMountKey,
  playerBarActions,
  resolvePlaybackHost,
  shrinkOntoPage,
} from "./inAppPip.js";

test("shrinking does not call pause", () => {
  let pauses = 0;
  const video = {
    paused: false,
    pause() {
      pauses += 1;
      this.paused = true;
    },
  };
  const next = shrinkOntoPage(video, { ratingKey: "plex-949", returnTo: "/explore" });
  assert.equal(pauses, 0);
  assert.equal(video.paused, false);
  assert.equal(next.paused, false);
  assert.equal(next.presentation, "pip");
  assert.equal(next.ratingKey, "plex-949");
  assert.equal(next.returnTo, "/explore");
});

test("floating player stays mounted across chat, explore, and search", () => {
  const session = { presentation: "pip", ratingKey: "plex-949" };
  const chat = resolvePlaybackHost({ pathname: "/chat", session });
  const explore = resolvePlaybackHost({ pathname: "/explore", session });
  const search = resolvePlaybackHost({ pathname: "/search", session });
  assert.equal(chat.active, true);
  assert.equal(explore.active, true);
  assert.equal(search.active, true);
  assert.equal(chat.presentation, "pip");
  assert.equal(playbackMountKey(chat), playbackMountKey(explore));
  assert.equal(playbackMountKey(explore), playbackMountKey(search));
  assert.equal(playbackMountKey(chat), "library-play:plex-949");

  const stage = resolvePlaybackHost({ pathname: "/watch/plex-949", session: null });
  assert.equal(stage.presentation, "stage");
  assert.equal(playbackMountKey(stage), playbackMountKey(chat));

  const left = resolvePlaybackHost({ pathname: "/explore", session: null });
  assert.equal(left.active, false);
  assert.equal(playbackMountKey(left), "");
});

test("pop-out stays a separate action from shrink", () => {
  const desktop = playerBarActions({ presentation: "stage", popoutWindow: false, phone: false });
  assert.equal(desktop.shrinkOntoPage, true);
  assert.equal(desktop.popOutOfWindow, true);
  assert.notEqual(SHRINK_ONTO_PAGE_LABEL, POP_OUT_OF_WINDOW_LABEL);

  const shrunk = playerBarActions({ presentation: "pip", popoutWindow: false, phone: false });
  assert.equal(shrunk.shrinkOntoPage, false);
  assert.equal(shrunk.popOutOfWindow, true);

  const popup = playerBarActions({ presentation: "stage", popoutWindow: true, phone: false });
  assert.equal(popup.shrinkOntoPage, false);
  assert.equal(popup.popOutOfWindow, false);

  const popoutRoute = resolvePlaybackHost({
    pathname: "/watch/plex-949/popout",
    session: { presentation: "pip", ratingKey: "plex-949" },
  });
  assert.equal(popoutRoute.active, false);
});

test("shrink return path rejects watch and off-site targets", () => {
  assert.equal(shrinkOntoPage(null, { ratingKey: "a", returnTo: "/watch/a" }).returnTo, "/chat");
  assert.equal(shrinkOntoPage(null, { ratingKey: "a", returnTo: "//evil.example" }).returnTo, "/chat");
  assert.equal(shrinkOntoPage(null, { ratingKey: "a", returnTo: "" }).returnTo, "/chat");
  assert.equal(
    shrinkOntoPage({ paused: true }, { ratingKey: "a", returnTo: "/search?q=heat" }).returnTo,
    "/search?q=heat",
  );
});
