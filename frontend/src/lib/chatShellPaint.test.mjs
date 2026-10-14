import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");

function source(rel) {
  return readFileSync(join(root, rel), "utf8");
}

describe("chat and live first paint", () => {
  it("does not replace chat with a full-page loader while auth or features hang", () => {
    const chat = source("components/ChatWorkspace.jsx");
    assert.match(chat, /data-testid="chat-workspace"/);
    assert.match(chat, /data-testid="workspace-main"/);
    assert.match(chat, /className="composer composer-raised"/);
    assert.doesNotMatch(chat, /data-testid="app-auth-loading"/);
    assert.doesNotMatch(chat, /if \(!authReady\)/);
    assert.doesNotMatch(chat, /login-lede">Loading…/);
  });

  it("paints the same Live peer from the install stamp before auth settles", () => {
    const gate = source("components/UserMenu.jsx");
    const settings = source("layouts/SettingsLayout.jsx");
    const admin = source("layouts/AdminLayout.jsx");
    const shell = source("layouts/AppShell.jsx");
    for (const file of [gate, settings, admin]) {
      assert.match(file, /initialLiveChannelsReady/);
    }
    assert.match(shell, /authReady=\{false\}/);
    assert.match(shell, /liveChannelsReady=\{liveChannelsReady\}/);
    assert.doesNotMatch(gate, /setLiveChannelsReady\(false\)/);
  });

  it("starts the live guide without waiting on auth and caps a hung warming poll", () => {
    const page = source("pages/LivePage.jsx");
    assert.match(page, /readLiveGuideCache/);
    assert.match(page, /timeoutMs: LIVE_GUIDE_WAIT_MS/);
    assert.match(page, /shouldShowGuideSkeleton/);
    assert.match(page, /guideStallError/);
    assert.doesNotMatch(page, /useAuthGate/);
    assert.doesNotMatch(page, /if \(!authReady\) return/);
    assert.doesNotMatch(page, /getFeatures\(\)/);
    assert.doesNotMatch(page, /!authReady \|\| loading \|\| guideWarming/);
  });
});
