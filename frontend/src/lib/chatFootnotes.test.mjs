import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "../..");

test("chat markdown stylesheet styles footnote refs and section", () => {
  const css = readFileSync(join(root, "src/styles/02-nav-chrome.css"), "utf8");
  assert.match(css, /\.markdown-body \.markdown-footnotes/);
  assert.match(css, /\.markdown-body \.markdown-footnote-ref/);
});

test("MessageText wires footnote-friendly markdown components", () => {
  const src = readFileSync(join(root, "src/components/MessageText.jsx"), "utf8");
  assert.match(src, /markdown-footnotes/);
  assert.match(src, /markdown-footnote-ref/);
  assert.match(src, /remarkGfm/);
});
