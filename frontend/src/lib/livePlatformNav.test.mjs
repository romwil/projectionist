import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import { buildPrimaryNavItems } from "./primaryNav.js";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");

function source(rel) {
  return readFileSync(join(root, rel), "utf8");
}

describe("live platform nav", () => {
  it("mounts in-app /live in AppShell so guide uses the shared primary nav", () => {
    const page = source("pages/LivePage.jsx");
    const shell = source("layouts/AppShell.jsx");
    const topbar = source("components/PrimaryTopbar.jsx");

    assert.match(page, /import AppShell from "\.\.\/layouts\/AppShell"/);
    assert.match(page, /function LivePlatformFrame/);
    assert.match(page, /<AppShell[\s\S]*className="app-root live-shell"/);
    assert.match(page, /if \(popout\) return node;\s*return <LivePlatformFrame>/);
    assert.match(page, /data-testid="live-mode-guide"/);
    assert.match(page, /data-testid="live-mode-watch"/);
    assert.doesNotMatch(page, /data-testid="live-back-chat"/);

    assert.match(shell, /<PrimaryTopbar/);
    assert.match(topbar, /buildPrimaryNavItems/);
    assert.match(topbar, /data-testid="projectionist-brand"|<ProjectionistBrand/);
    assert.match(topbar, /data-testid="app-topbar-peers"/);

    const peers = buildPrimaryNavItems({
      role: "owner",
      isOwner: true,
      authReady: true,
      liveChannelsReady: true,
    });
    const byId = Object.fromEntries(peers.map((item) => [item.id, item]));
    assert.equal(byId.chat.testId, "topbar-chat-link");
    assert.equal(byId.explore.testId, "topbar-explore-link");
    assert.equal(byId.search.testId, "topbar-search-link");
    assert.equal(byId.chat.label, "Chat");
    assert.equal(byId.explore.label, "Explore");
  });
});
