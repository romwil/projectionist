import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";

const srcRoot = join(dirname(fileURLToPath(import.meta.url)), "..");

function cssFiles(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) out.push(...cssFiles(path));
    else if (name.endsWith(".css")) out.push(path);
  }
  return out;
}

/**
 * VIS-003: --accent is a fill. On Lights Up paper it fails contrast as text,
 * so text uses --accent-ink (#735c00 in Lights Up) and fills pair with --accent-text.
 */
describe("accent text uses --accent-ink (VIS-003)", () => {
  it("no stylesheet sets text color to the raw --accent fill", () => {
    const offenders = [];
    for (const file of cssFiles(srcRoot)) {
      const lines = readFileSync(file, "utf8").split("\n");
      lines.forEach((line, index) => {
        if (/(^|[^-])color:\s*var\(--accent[,)]/.test(line)) {
          offenders.push(`${relative(srcRoot, file)}:${index + 1}`);
        }
      });
    }
    assert.deepEqual(offenders, []);
  });

  it("Lights Up keeps the darker ink token", () => {
    const tokens = readFileSync(join(srcRoot, "styles/01-tokens.css"), "utf8");
    assert.match(tokens, /--accent-ink:\s*#735c00/i);
  });

  it("the gold search submit pairs the fill with --accent-text", () => {
    const css = readFileSync(join(srcRoot, "styles/10-explore-delight.css"), "utf8");
    const block = css.match(/\.explore-search-submit\s*\{([^}]+)\}/);
    assert.ok(block, "expected .explore-search-submit rule");
    assert.match(block[1], /color:\s*var\(--accent-text\)/);
    assert.match(block[1], /background:\s*var\(--accent\)/);
  });
});
