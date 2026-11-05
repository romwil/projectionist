import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, it } from "node:test";

// VIS-001: the screens the 2026-11-01 review named (Chat, Explore, Title
// detail, Admin Overview) use the shared Button. A bare <button> with no
// class inherits the global gold fill, so none may come back here.
const src = join(dirname(fileURLToPath(import.meta.url)), "..");
const ADOPTED = [
  "components/AddActionBanner.tsx",
  "components/TitleCard.tsx",
  "components/ThreadList.tsx",
  "components/RecommendModal.tsx",
  "components/TitleReviewModal.tsx",
  "components/OwnerOpsOverview.tsx",
  "components/PosterOverlayControls.tsx",
  "components/TitleDetailDrawer.tsx",
  "pages/TitleDetailPage.tsx",
];

function bareButtons(source) {
  const found = [];
  const re = /<button\b([\s\S]*?)>/g;
  let match;
  while ((match = re.exec(source))) {
    if (!/className=/.test(match[1])) found.push(match[0].slice(0, 80));
  }
  return found;
}

describe("Button adoption on reviewed screens (VIS-001)", () => {
  for (const file of ADOPTED) {
    const source = readFileSync(join(src, file), "utf8");
    it(`${file} imports Button and has no unstyled <button>`, () => {
      assert.match(source, /import Button from "(\.\/|\.\.\/components\/)Button";/);
      assert.deepEqual(bareButtons(source), []);
    });
  }

  it("generic ghost/primary class buttons are gone from those files", () => {
    for (const file of ADOPTED) {
      const source = readFileSync(join(src, file), "utf8");
      assert.doesNotMatch(source, /<button[^>]*className="(ghost|primary)"/, file);
    }
  });
});

describe("type floor (VIS-004)", () => {
  const tokens = readFileSync(join(src, "styles", "01-tokens.css"), "utf8");

  it("the smallest text token is 12px on the 15px root", () => {
    const xs = Number(tokens.match(/--text-xs:\s*([0-9.]+)rem/)[1]);
    const sm = Number(tokens.match(/--text-sm:\s*([0-9.]+)rem/)[1]);
    assert.ok(xs * 15 >= 12, `--text-xs renders at ${xs * 15}px`);
    assert.ok(sm > xs);
  });

  it("no non-Live stylesheet sets a literal font-size under 12px", () => {
    const sheets = [
      "02-nav-chrome.css",
      "04-config-onboarding.css",
      "05-chat-responsive.css",
      "06-reading-admin-settings.css",
      "08-dashboard-coverage-cards.css",
      "09-title-detail-home.css",
      "10-explore-delight.css",
      "11-youth-guest.css",
    ];
    for (const sheet of sheets) {
      const css = readFileSync(join(src, "styles", sheet), "utf8");
      for (const m of css.matchAll(/font-size:\s*([0-9.]+)(rem|px)\b/g)) {
        const px = m[2] === "rem" ? Number(m[1]) * 15 : Number(m[1]);
        assert.ok(px >= 12, `${sheet}: ${m[0]}`);
      }
    }
  });
});
