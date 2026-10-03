import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  CHANNEL_KINDS,
  LIVE_OWNER_JARGON,
  channelSummaryLine,
  createStepsFor,
  launchBlockers,
  launchReadinessRows,
  liveStationState,
  ownerLiveText,
  publishSucceeded,
} from "./liveChannelsOwnerCopy.js";

describe("ownerLiveText", () => {
  it("rewrites operator vocabulary into Projectionist words", () => {
    assert.equal(
      ownerLiveText("Publish this station to Tunarr?"),
      "Publish this channel to the broadcast?",
    );
    assert.equal(ownerLiveText("Tunarr XMLTV URL"), "Channel guide URL");
    assert.equal(ownerLiveText("Scanning Tunarr channels in Plex…"), "Scanning Projectionist channels in Plex…");
    assert.equal(ownerLiveText("Tunarr URL or managed Docker"), "Broadcast address");
    assert.equal(ownerLiveText("Docker orchestration"), "Automatic engine start");
    assert.equal(ownerLiveText("TV engine ready"), "Broadcast ready");
  });

  it("never leaves jargon behind for common API messages", () => {
    const samples = [
      "Tunarr unreachable at http://host.docker.internal:8000",
      "XMLTV guide attach failed",
      "Disk space (~1 GB for Tunarr image)",
      "Pull the Docker image chrisbenincasa/tunarr:1.3.9",
      "Published 3 stations to Tunarr's lineup",
      "Tunarr Live TV sessions drop",
    ];
    for (const sample of samples) {
      const out = ownerLiveText(sample);
      assert.doesNotMatch(out, LIVE_OWNER_JARGON, `${sample} -> ${out}`);
    }
  });

  it("capitalizes at sentence start and tolerates empty input", () => {
    assert.match(ownerLiveText("Tunarr is down."), /^Broadcast engine is down\./);
    assert.equal(ownerLiveText(null), "");
    assert.equal(ownerLiveText(undefined), "");
  });
});

describe("create flow", () => {
  it("offers four owner-language ways to start a channel", () => {
    assert.deepEqual(
      CHANNEL_KINDS.map((k) => k.id),
      ["show", "collection", "mood", "suggest"],
    );
    for (const kind of CHANNEL_KINDS) {
      assert.doesNotMatch(`${kind.title} ${kind.blurb}`, LIVE_OWNER_JARGON);
    }
  });

  it("skips the shaping step when Projectionist suggests the lineup", () => {
    assert.deepEqual(createStepsFor("suggest").map((s) => s.id), ["pick", "launch"]);
    assert.deepEqual(createStepsFor("show").map((s) => s.id), ["pick", "shape", "launch"]);
  });

  it("summarizes a channel in one honest line", () => {
    assert.equal(
      channelSummaryLine({
        kind: "mood",
        name: "Midnight Mystery",
        number: 101,
        programmingMode: "shuffle",
        mediaScope: "movies",
      }),
      "Channel 101 · Midnight Mystery · shuffled · movies only",
    );
    assert.equal(
      channelSummaryLine({ kind: "show", pickTitle: "Columbo", programmingMode: "sequential" }),
      "Columbo · in order",
    );
  });
});

describe("liveStationState", () => {
  const up = { broadcast: { sidecar_up: true }, channel_count: 4 };

  it("is off, then loading, without claiming problems while warming", () => {
    assert.equal(liveStationState({ enabled: false }).key, "off");
    assert.equal(liveStationState({ enabled: true, status: null }).key, "loading");
    assert.equal(
      liveStationState({ enabled: true, status: { warming: true, channel_count: 0 } }).key,
      "loading",
    );
  });

  it("walks empty → ready to launch → on air", () => {
    assert.equal(
      liveStationState({ enabled: true, status: { channel_count: 0, broadcast: {} } }).key,
      "empty",
    );
    const offAir = liveStationState({
      enabled: true,
      status: { channel_count: 2, broadcast: { sidecar_up: false } },
    });
    assert.equal(offAir.key, "ready_to_launch");
    assert.match(offAir.title, /2 channels are built/);
    const onAir = liveStationState({
      enabled: true,
      status: {
        ...up,
        guide_index: { plex_livetv: { mapping_ok: true, mapped: 4, expected: 4 } },
      },
    });
    assert.equal(onAir.key, "on_air");
    assert.equal(onAir.title, "4 channels on the air");
  });

  it("flags a Plex mismatch honestly and reports launching", () => {
    const state = liveStationState({
      enabled: true,
      status: {
        ...up,
        guide_index: { plex_livetv: { mapping_ok: false, mapped: 1, expected: 4 } },
      },
    });
    assert.equal(state.key, "attention");
    assert.match(state.detail, /1 of 4/);
    assert.equal(liveStationState({ enabled: true, status: up, launching: true }).key, "launching");
  });

  it("never exposes jargon in any state", () => {
    const states = [
      liveStationState({ enabled: false }),
      liveStationState({ enabled: true }),
      liveStationState({ enabled: true, status: { channel_count: 0 } }),
      liveStationState({ enabled: true, status: { channel_count: 1, broadcast: {} } }),
      liveStationState({ enabled: true, launching: true }),
    ];
    for (const s of states) {
      assert.doesNotMatch(`${s.title} ${s.detail}`, LIVE_OWNER_JARGON);
    }
  });
});

describe("launch readiness", () => {
  const preflight = {
    checks: [
      { id: "plex_reachable", ok: true, soft: false, label: "Plex reachable", message: "ok" },
      { id: "tunarr_url", ok: false, soft: false, label: "Tunarr URL or managed Docker", message: "Tunarr is not reachable" },
      { id: "gpu", ok: false, soft: true, label: "GPU (optional)", message: "none" },
    ],
  };

  it("maps checks to friendly labels and scrubs messages", () => {
    const rows = launchReadinessRows(preflight);
    assert.equal(rows[0].label, "Plex is connected");
    assert.equal(rows[1].label, "Broadcast engine is reachable");
    assert.doesNotMatch(rows[1].message, LIVE_OWNER_JARGON);
  });

  it("only hard failures block launch", () => {
    const blockers = launchBlockers(preflight);
    assert.deepEqual(blockers.map((b) => b.id), ["tunarr_url"]);
    assert.deepEqual(launchBlockers({ checks: [] }), []);
    assert.deepEqual(launchBlockers(null), []);
  });

  it("decides publish success from the job result", () => {
    assert.equal(publishSucceeded({ phase: "done" }), true);
    assert.equal(publishSucceeded({ ok: true, count_errors: 0 }), true);
    assert.equal(publishSucceeded({ phase: "error" }), false);
    assert.equal(publishSucceeded({ ok: false }), false);
    assert.equal(publishSucceeded({ count_errors: 2 }), false);
    assert.equal(publishSucceeded(null), false);
  });
});
