import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, it } from "node:test";
import { isLocalOnlyJoin, joinLede, joinMethods } from "./joinPage.ts";

const src = join(dirname(fileURLToPath(import.meta.url)), "..");

describe("join page copy (GRO-009)", () => {
  it("never mentions Plex on a local-only install", () => {
    const methods = joinMethods(["local"], ["plex", "local"]);
    assert.deepEqual(methods, { plex: false, oidc: false, local: true });
    assert.equal(isLocalOnlyJoin(methods), true);
    for (const loading of [true, false]) {
      for (const hasInvite of [true, false]) {
        assert.doesNotMatch(joinLede({ loading, hasInvite, methods }), /plex/i);
      }
    }
    assert.equal(joinLede({ loading: false, hasInvite: true, methods }), "Choose a username and password to join.");
  });

  it("an invite that only allows local is local-only even when Plex is on", () => {
    const methods = joinMethods(["plex", "local"], ["local"]);
    assert.equal(isLocalOnlyJoin(methods), true);
    assert.doesNotMatch(joinLede({ loading: false, hasInvite: true, methods }), /plex/i);
  });

  it("keeps the Plex sentence when Plex is how this invite signs in", () => {
    const methods = joinMethods(["plex", "local"], ["plex", "local"]);
    assert.equal(isLocalOnlyJoin(methods), false);
    assert.match(joinLede({ loading: false, hasInvite: true, methods }), /Sign in with Plex/);
  });

  it("SSO without Plex does not mention Plex", () => {
    const methods = joinMethods(["oidc", "local"], ["oidc", "local"]);
    assert.doesNotMatch(joinLede({ loading: false, hasInvite: true, methods }), /plex/i);
  });

  it("JoinPage renders Plex words only behind plexEnabled or an active Plex wait", () => {
    const source = readFileSync(join(src, "pages", "JoinPage.tsx"), "utf8");
    const view = source.slice(source.indexOf("  return (\n    <GlassDoor"));
    assert.match(view, /lede=\{joinLede\(/);
    assert.match(view, /showLocal \|\| localOnly \?/);
    const jsxPlex = [...view.matchAll(/>[^<>{}]*Plex[^<>{}]*</g)].map((m) => ({ text: m[0], at: m.index }));
    for (const { text, at } of jsxPlex) {
      const before = view.slice(0, at);
      const guard = Math.max(before.lastIndexOf("{plexEnabled ? ("), before.lastIndexOf("{waitingForPlex ? ("));
      const closed = before.lastIndexOf(") : null}");
      assert.ok(guard > closed, `unguarded Plex copy: ${text}`);
    }
  });
});
