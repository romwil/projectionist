import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

// styles.css is a thin @import aggregator (see frontend/src/styles/). Tests that
// assert on the stylesheet read the concatenated partials here so they keep
// working regardless of how the CSS is partitioned. Order is irrelevant for the
// substring/regex checks these tests perform.
export function readAllStyles() {
  const srcRoot = join(dirname(fileURLToPath(import.meta.url)), "..");
  const dir = join(srcRoot, "styles");
  return readdirSync(dir)
    .filter((f) => f.endsWith(".css"))
    .sort()
    .map((f) => readFileSync(join(dir, f), "utf8"))
    .join("\n");
}
