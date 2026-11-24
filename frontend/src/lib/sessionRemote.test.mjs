import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  capabilityOn,
  estimatePlayhead,
  formatPlayhead,
  joinSentence,
  openSessionBody,
  mayUseRemote,
  remoteRole,
  roomRows,
  sessionLiveUrl,
  transportCommand,
} from "./sessionRemote.ts";

describe("session remote", () => {
  it("keeps the room list to names", () => {
    const rows = roomRows({
      rooms: [
        {
          id: "room-1",
          name: "Living Room",
          kind: "tv",
          rating_key: "secret",
          title: "Blade Runner",
        },
        { id: "", name: "Missing" },
        { name: "No id" },
      ],
    });
    assert.deepEqual(rows, [{ id: "room-1", name: "Living Room", kind: "tv" }]);
    assert.equal(JSON.stringify(rows).includes("Blade Runner"), false);
    assert.equal(JSON.stringify(rows).includes("secret"), false);
  });

  it("hides the film until a join is accepted", () => {
    assert.match(joinSentence("pending"), /Nothing about the film/);
    assert.equal(joinSentence("declined"), "Not now.");
    assert.equal(joinSentence("joined"), "");
    assert.equal(joinSentence("pending").includes("Blade Runner"), false);
  });

  it("estimates the playhead from the server clock", () => {
    assert.equal(estimatePlayhead(5000, 1000, 4000, "playing"), 8000);
    assert.equal(estimatePlayhead(5000, 1000, 9000, "paused"), 5000);
    assert.equal(formatPlayhead(65000), "1:05");
  });

  it("starts a session on a room and speaks the live channel", () => {
    assert.deepEqual(openSessionBody("room-1", "plex-78"), {
      screen_id: "room-1",
      rating_key: "plex-78",
      level: "off",
    });
    assert.deepEqual(transportCommand("pause"), { command: "pause" });
    assert.deepEqual(transportCommand("skip", -10), { command: "skip", s: -10 });
    assert.equal(
      sessionLiveUrl("sess-1", "https://films.example/remote/sess-1"),
      "wss://films.example/api/sessions/sess-1/live",
    );
    assert.equal(capabilityOn({ capabilities: { rooms: 1, session_object: 0 } }, "rooms"), true);
    assert.equal(capabilityOn({ capabilities: { rooms: 1 } }, "session_object"), false);
  });

  it("lets a guest use the remote only when the starter allows it", () => {
    const session = { owner_id: "owner-1", guests: ["guest-1"] };
    assert.equal(remoteRole(session, "owner-1"), "owner");
    assert.equal(remoteRole(session, "guest-1"), "guest");
    assert.equal(remoteRole(session, "screen-1"), "screen");
    assert.equal(mayUseRemote("guest", false), false);
    assert.equal(mayUseRemote("guest", true), true);
    assert.equal(mayUseRemote("owner", false), true);
    assert.equal(mayUseRemote("screen", false), true);
  });
});
