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
  assert.match(src, /TitleDetailLink/);
  assert.match(src, /linkifyKnownTitles/);
});

test("parseMarkdownFootnotes extracts [^n] definitions", async () => {
  const { parseMarkdownFootnotes } = await import("./chatFootnotes.js");
  assert.deepEqual(
    parseMarkdownFootnotes(
      "Kurosawa cuts on movement[^1] and holds the rain.[^2]\n\n[^1]: Rashomon (1950) — courtyard geometry.\n[^2]: Seven Samurai (1954) — the weather as chorus.\n",
    ),
    [
      { id: "1", text: "Rashomon (1950) — courtyard geometry." },
      { id: "2", text: "Seven Samurai (1954) — the weather as chorus." },
    ],
  );
  assert.deepEqual(parseMarkdownFootnotes("No citations here."), []);
});

test("footnoteIdFromHref reads GFM footnote anchors", async () => {
  const { footnoteIdFromHref } = await import("./chatFootnotes.js");
  assert.equal(footnoteIdFromHref("#user-content-fn-1"), "1");
  assert.equal(footnoteIdFromHref("#fn-2"), "2");
  assert.equal(footnoteIdFromHref("#user-content-fnref-3", "3"), "3");
  assert.equal(footnoteIdFromHref("https://example.com"), "");
});

test("MessageText opens a footnote sheet instead of a raw dump", () => {
  const src = readFileSync(join(root, "src/components/MessageText.jsx"), "utf8");
  assert.match(src, /parseMarkdownFootnotes/);
  assert.match(src, /data-testid="chat-footnote-sheet"/);
  assert.match(src, /role="dialog"/);
  assert.match(src, /data-testid="chat-footnote-ref"/);
  assert.match(src, /hidden|aria-hidden/);
  assert.match(src, /useState/);
});

test("footnote sheet CSS lives next to MessageText", () => {
  const css = readFileSync(join(root, "src/components/MessageText.css"), "utf8");
  assert.match(css, /chat-footnote-sheet/);
  assert.match(css, /role|dialog|sheet/);
});

test("walk footnote ids get a walk sheet label", async () => {
  const { footnoteSheetLabel, footnoteWalkKind } = await import("./chatFootnotes.js");
  assert.equal(footnoteSheetLabel({ id: "lineage-1" }), "Lineage source 1");
  assert.equal(footnoteSheetLabel({ id: "gap-2" }), "Gap list source 2");
  assert.equal(footnoteSheetLabel({ id: "1" }), "Source 1");
  assert.equal(footnoteWalkKind("seminar-3"), "seminar");
  assert.equal(footnoteWalkKind("1"), "");
});

test("MessageText labels walk footnote sheets", () => {
  const src = readFileSync(join(root, "src/components/MessageText.jsx"), "utf8");
  assert.match(src, /footnoteSheetLabel/);
  assert.match(src, /data-walk-kind/);
});
