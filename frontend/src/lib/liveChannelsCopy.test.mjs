import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  CREATE_STATION_MODES,
  formatLiveStreamError,
  liveAdminLabel,
  liveGuideEmptyCopy,
  liveHealthSentence,
  liveOnboardingTip,
  liveSetupStepNumbers,
  liveUserEmptyCopy,
} from "./liveChannelsCopy.js";

describe("liveChannelsCopy", () => {
  it("uses household warming copy without Tunarr", () => {
    const warming = liveUserEmptyCopy({ featureOn: true, featureReady: false, guideReady: false });
    assert.equal(warming.title, "Channels are warming up");
    assert.match(warming.body, /TV isn’t ready yet/);
    assert.doesNotMatch(warming.body, /Tunarr/i);
    assert.doesNotMatch(warming.title, /Broadcast engine/i);

    const guide = liveGuideEmptyCopy("tunarr_unreachable");
    assert.doesNotMatch(guide.body, /Tunarr/i);
    assert.match(guide.body, /Admin/);
  });

  it("maps Admin glossary labels", () => {
    assert.equal(liveAdminLabel("Broadcast engine"), "TV engine");
    assert.equal(liveAdminLabel("Filler programming paths"), "Between-show breaks");
    assert.equal(liveAdminLabel("Pad flex max"), "Gap fill (minutes)");
    assert.equal(liveAdminLabel("Programming"), "Play order");
    assert.equal(liveAdminLabel("Recipe"), "Station source");
    assert.equal(liveAdminLabel("Continuity ready"), "Breaks ready");
    assert.equal(liveAdminLabel("Remounting Tunarr"), "Restarting TV engine");
    assert.equal(liveAdminLabel("Plex Tunarr map"), "Plex channel map");
    assert.equal(liveAdminLabel("Installation"), "Setup");
  });

  it("builds a one-sentence health strip", () => {
    const sentence = liveHealthSentence({
      broadcast: { sidecar_up: true },
      channel_count: 3,
      airing: [{ id: "a" }, { id: "b" }],
      last_publish_at: "2026-08-01",
    });
    assert.match(sentence, /TV engine running/);
    assert.match(sentence, /3 stations/);
    assert.match(sentence, /2 airing now/);
    assert.doesNotMatch(sentence, /XMLTV/);
  });

  it("numbers Setup steps stably with and without Docker orch", () => {
    const withOrch = liveSetupStepNumbers({ dockerOrchestration: true });
    assert.equal(withOrch.ready, 1);
    assert.equal(withOrch.engine, 2);
    assert.equal(withOrch.breaks, 3);
    assert.equal(withOrch.create, 4);
    assert.equal(withOrch.plex, 5);

    const noOrch = liveSetupStepNumbers({ dockerOrchestration: false });
    assert.equal(noOrch.ready, 1);
    assert.equal(noOrch.engine, null);
    assert.equal(noOrch.breaks, 2);
    assert.equal(noOrch.create, 3);
    assert.equal(noOrch.plex, 4);
  });

  it("exposes create-station modes and soft onboarding tip", () => {
    assert.deepEqual(
      CREATE_STATION_MODES.map((m) => m.id),
      ["custom", "collection", "starters"],
    );
    assert.equal(liveOnboardingTip({ liveEnabled: true, syncHealthy: true }), null);
    const tip = liveOnboardingTip({ liveEnabled: false, syncHealthy: true });
    assert.equal(tip.ctaTo, "/admin/live-channels");
    assert.match(tip.title, /on the air/i);
  });

  it("softens stream warming errors", () => {
    assert.match(
      formatLiveStreamError({ response: { code: 503 } }),
      /warming up/i,
    );
    assert.doesNotMatch(
      formatLiveStreamError({ response: { code: 503 } }),
      /Broadcast engine/i,
    );
  });
});
