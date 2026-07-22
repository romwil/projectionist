import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const readingCss = join(here, "../styles/06-reading-admin-settings.css");

/**
 * Guard: Help/Privacy prose must use theme tokens so Lights Up stays readable.
 * Regression: hardcoded rgba(243, 239, 230, …) body color on cream paper.
 */
describe("privacy-prose contrast (Help / Privacy)", () => {
  const css = readFileSync(readingCss, "utf8");

  it("sets body copy color via --text, not a Lights Down cream literal", () => {
    const block = css.match(/\.privacy-prose p,\s*\n\.privacy-prose li\s*\{([^}]+)\}/);
    assert.ok(block, "expected .privacy-prose p/li rule");
    assert.match(block[1], /color:\s*var\(--text\)/);
    assert.doesNotMatch(block[1], /rgba\s*\(\s*243\s*,\s*239\s*,\s*230/);
    assert.doesNotMatch(block[1], /#f3efe6|#e6e2d6/i);
  });

  it("does not leave other privacy-prose text rules on hardcoded cream", () => {
    const proseRules = [...css.matchAll(/\.privacy-prose[^{]*\{([^}]+)\}/g)].map((m) => m[1]);
    assert.ok(proseRules.length >= 3, "expected privacy-prose rules");
    for (const body of proseRules) {
      if (!/\bcolor\s*:/.test(body)) continue;
      assert.doesNotMatch(
        body,
        /color:\s*rgba\s*\(\s*243\s*,\s*239\s*,\s*230/,
        "privacy-prose color must not hardcode dark-theme cream",
      );
    }
  });
});
