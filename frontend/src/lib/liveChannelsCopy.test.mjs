import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  CREATE_STATION_MODES,
  craftSoftCapHonestyNote,
  formatLiveStreamError,
  liveAdminLabel,
  liveGuideEmptyCopy,
  liveHealthSentence,
  liveOnboardingTip,
  liveSetupStepNumbers,
  liveStreamHealthCopy,
  liveUserEmptyCopy,
} from "./liveChannelsCopy.js";
import { LIVE_SOFT_STALL_PHRASES } from "./liveStreamSoftStallCopy.js";

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
      ["custom", "collection", "show", "starters"],
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

  it("uses antenna-library copy for soft stalls; keeps hard errors honest", () => {
    assert.equal(liveStreamHealthCopy("ok"), "");
    assert.equal(
      liveStreamHealthCopy("buffering", { phrase: "Adjusting the antenna arms…" }),
      "Adjusting the antenna arms…",
    );
    assert.equal(
      liveStreamHealthCopy("stalled", { phrase: "Twisting the UHF antenna loop…" }),
      "Twisting the UHF antenna loop…",
    );
    const picked = liveStreamHealthCopy("buffering", { pick: () => LIVE_SOFT_STALL_PHRASES[0] });
    assert.equal(picked, LIVE_SOFT_STALL_PHRASES[0]);
    assert.doesNotMatch(picked, /Buffering|Tunarr/i);
    // Hard failures stay on the serious path.
    assert.match(
      formatLiveStreamError({ response: { code: 503 } }),
      /warming up/i,
    );
  });

  it("states motif soft-cap honesty vs full-run", () => {
    const soft = craftSoftCapHonestyNote({
      soft_capped: true,
      soft_default: 30,
      soft_cap: 80,
      full_run_cap: 1000,
      note: "Matched 40 title(s).",
    });
    assert.match(soft, /Matched 40/);
    assert.match(soft, /30–80/);
    assert.match(soft, /1000/);
    const full = craftSoftCapHonestyNote({ fill_mode: "full_run" });
    assert.match(full, /full resolved pool/i);
  });
});
