import assert from "node:assert/strict";
import test from "node:test";

import {
  resolveDockDropTarget,
  statusDockDropHint,
} from "./easterEggs.ts";

test("resolveDockDropTarget routes movies to Radarr and shows to Sonarr", () => {
  const connections = { radarrConnected: true, sonarrConnected: true };
  assert.equal(
    resolveDockDropTarget({ media_type: "movie", tmdb_id: 78, in_library: false }, connections),
    "radarr",
  );
  assert.equal(
    resolveDockDropTarget({ media_type: "show", tvdb_id: 79126, in_library: false }, connections),
    "sonarr",
  );
  assert.equal(
    resolveDockDropTarget({ media_type: "movie", tmdb_id: 78, in_library: true }, connections),
    null,
  );
});

test("statusDockDropHint reflects connected services", () => {
  assert.match(
    statusDockDropHint({ radarrConnected: true, sonarrConnected: true }),
    /Radarr or Sonarr/,
  );
  assert.match(statusDockDropHint({ radarrConnected: true, sonarrConnected: false }), /Radarr/);
  assert.match(statusDockDropHint({ radarrConnected: false, sonarrConnected: true }), /Sonarr/);
  assert.equal(statusDockDropHint({ radarrConnected: false, sonarrConnected: false }), "");
});

test("resolveDockDropTarget returns null when services disconnected or ids missing", () => {
  assert.equal(
    resolveDockDropTarget(
      { media_type: "movie", tmdb_id: 78, in_library: false },
      { radarrConnected: false, sonarrConnected: true },
    ),
    null,
  );
  assert.equal(
    resolveDockDropTarget(
      { media_type: "show", tvdb_id: 1, in_library: false },
      { radarrConnected: true, sonarrConnected: false },
    ),
    null,
  );
  assert.equal(
    resolveDockDropTarget(
      { media_type: "movie", in_library: false },
      { radarrConnected: true, sonarrConnected: true },
    ),
    null,
  );
  assert.equal(
    resolveDockDropTarget(
      { media_type: "show", in_library: false },
      { radarrConnected: true, sonarrConnected: true },
    ),
    null,
  );
});
