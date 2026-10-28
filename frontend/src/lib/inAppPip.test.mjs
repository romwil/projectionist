import assert from "node:assert/strict";
import test from "node:test";

import {
  POP_OUT_OF_WINDOW_LABEL,
  SHRINK_ONTO_PAGE_LABEL,
  clearShrunkPlay,
  initialPipState,
  persistShrunkPlay,
  playShrunkAfterReload,
  playbackMountKey,
  playerBarActions,
  resolvePlaybackHost,
  shrinkOntoPage,
} from "./inAppPip.ts";

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

function memoryStorage(initial = {}) {
  const data = { ...initial };
  return {
    getItem(key) {
      return Object.prototype.hasOwnProperty.call(data, key) ? data[key] : null;
    },
    setItem(key, value) {
      data[key] = String(value);
    },
    removeItem(key) {
      delete data[key];
    },
  };
}

test("stored shrunk session restores the overlay after a fresh page, and Close does not", async () => {
  const storage = memoryStorage();
  const saved = persistShrunkPlay(
    {
      ratingKey: "plex-949",
      offsetMs: 125000,
      title: "Hope",
      stream_url: "https://plex.example/stream",
      token: "plex-token",
    },
    storage,
  );
  assert.deepEqual(Object.keys(saved).sort(), ["offsetMs", "ratingKey", "shrunk", "title"]);
  assert.equal(saved.stream_url, undefined);
  assert.equal(saved.token, undefined);

  const pip = initialPipState("/explore", storage);
  assert.equal(pip.restored, true);
  assert.equal(pip.ratingKey, "plex-949");
  assert.equal(pip.offsetMs, 125000);
  assert.equal(pip.title, "Hope");
  const host = resolvePlaybackHost({
    pathname: "/explore",
    session: { presentation: "pip", ratingKey: pip.ratingKey },
  });
  assert.equal(host.active, true);
  assert.equal(host.presentation, "pip");
  assert.equal(playbackMountKey(host), "library-play:plex-949");

  clearShrunkPlay(storage);
  assert.equal(initialPipState("/explore", storage), null);
  const afterClose = resolvePlaybackHost({ pathname: "/explore", session: null });
  assert.equal(afterClose.active, false);
  assert.equal(playbackMountKey(afterClose), "");

  let plays = 0;
  const video = {
    muted: false,
    async play() {
      plays += 1;
      if (plays === 1 && this.muted === false) {
        const err = new Error("NotAllowedError");
        err.name = "NotAllowedError";
        throw err;
      }
    },
  };
  const result = await playShrunkAfterReload(video);
  assert.equal(result.playing, true);
  assert.equal(result.muted, true);
  assert.equal(result.unmuteOnTap, true);
  assert.equal(video.muted, true);
});
