import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  livePrerollCueId,
  normalizePrerollPayload,
  shouldPlayLivePreroll,
  shouldPlayMoviePreroll,
} from "./prerollClient.js";

describe("prerollClient", () => {
  it("normalizes next-preroll payloads and rejects empties", () => {
    assert.equal(normalizePrerollPayload(null), null);
    assert.equal(normalizePrerollPayload({ id: "a" }), null);
    const ok = normalizePrerollPayload({
      id: "clip-1",
      url: "/api/preroll/asset/clip-1",
      title: "Bumper",
    });
    assert.equal(ok.id, "clip-1");
    assert.equal(ok.url, "/api/preroll/asset/clip-1");
    assert.equal(ok.title, "Bumper");
  });

  it("gates movie preroll vs episode", () => {
    assert.equal(shouldPlayMoviePreroll({ media_type: "movie" }), true);
    assert.equal(shouldPlayMoviePreroll({ media_type: "episode" }), false);
    assert.equal(shouldPlayMoviePreroll({ media_type: "episode" }, { force: true }), true);
  });

  it("plays a live bumper only when a movie is starting or about to air", () => {
    const start = 1_700_000_000;
    const movie = { title: "Heat", media_type: "movie", start, started_at: start };
    const show = {
      title: "The Office",
      media_type: "show",
      episode_title: "Dinner Party",
      start,
      started_at: start,
    };
    const at = (sec) => sec * 1000;

    assert.equal(
      shouldPlayLivePreroll({ isFlex: false, nowProgram: movie, nextProgram: null }, at(start + 20)),
      true,
    );
    assert.equal(
      shouldPlayLivePreroll({ isFlex: false, nowProgram: movie, nextProgram: null }, at(start + 600)),
      false,
    );
    assert.equal(
      shouldPlayLivePreroll({ isFlex: false, nowProgram: show, nextProgram: null }, at(start + 5)),
      false,
    );
    assert.equal(
      shouldPlayLivePreroll(
        { isFlex: false, nowProgram: { title: "Pilot", media_type: "episode", start } },
        at(start + 5),
      ),
      false,
    );
    assert.equal(shouldPlayLivePreroll({ isFlex: false, nowProgram: { title: "Mystery" } }, at(start)), false);

    const nextStart = start + 3600;
    const nextMovie = { title: "Heat", media_type: "movie", start: nextStart, started_at: nextStart };
    assert.equal(
      shouldPlayLivePreroll(
        { isFlex: true, nowProgram: null, nextProgram: nextMovie, nextStart },
        at(nextStart - 60),
      ),
      true,
    );
    assert.equal(
      shouldPlayLivePreroll(
        { isFlex: true, nowProgram: null, nextProgram: nextMovie, nextStart },
        at(nextStart - 3600),
      ),
      false,
    );
    assert.equal(
      shouldPlayLivePreroll(
        {
          isFlex: true,
          nextProgram: { ...show, start: nextStart, started_at: nextStart },
          nextStart,
        },
        at(nextStart - 30),
      ),
      false,
    );

    const cue = livePrerollCueId(
      { isFlex: false, nowProgram: movie },
      at(start + 15),
    );
    assert.equal(cue, `${start}:Heat`);
    assert.equal(livePrerollCueId({ isFlex: false, nowProgram: show }, at(start + 15)), "");
  });
});
