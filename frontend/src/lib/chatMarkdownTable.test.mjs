import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";

const root = dirname(fileURLToPath(import.meta.url));
const css = readFileSync(join(root, "../styles/02-nav-chrome.css"), "utf8");
const messageText = readFileSync(join(root, "../components/MessageText.jsx"), "utf8");

function ruleBody(source, selector) {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = source.match(new RegExp(`${escaped}\\s*\\{([^}]+)\\}`));
  assert.ok(match, `missing rule ${selector}`);
  return match[1];
}

describe("chat markdown tables wrap inside the thread column", () => {
  it("renders every markdown table through the shared wrap", () => {
    assert.match(messageText, /className="markdown-table-wrap"/);
    assert.match(messageText, /<table>\{children\}<\/table>/);
  });

  it("sizes the table to the chat column and wraps cells on word boundaries", () => {
    const wrap = ruleBody(css, ".markdown-table-wrap");
    const table = ruleBody(css, ".markdown-body table");
    const cells = ruleBody(css, ".markdown-body th,\n.markdown-body td");

    assert.match(wrap, /max-width:\s*100%/);
    assert.match(wrap, /overflow:\s*visible/);
    assert.doesNotMatch(wrap, /overflow-x:\s*auto/);
    assert.doesNotMatch(wrap, /overflow:\s*hidden/);
    assert.doesNotMatch(wrap, /text-overflow:\s*ellipsis/);

    assert.match(table, /width:\s*100%/);
    assert.match(table, /max-width:\s*100%/);
    assert.match(table, /table-layout:\s*fixed/);
    assert.doesNotMatch(table, /max-content/);
    assert.doesNotMatch(table, /white-space:\s*nowrap/);

    assert.match(cells, /white-space:\s*normal/);
    assert.match(cells, /overflow-wrap:\s*break-word/);
    assert.match(cells, /word-break:\s*normal/);
    assert.match(cells, /overflow:\s*visible/);
    assert.doesNotMatch(cells, /white-space:\s*nowrap/);
    assert.doesNotMatch(cells, /text-overflow:\s*ellipsis/);
    assert.doesNotMatch(cells, /overflow:\s*hidden/);
  });

  it("keeps the first column narrow and gives the prose column the rest", () => {
    const first = ruleBody(
      css,
      ".markdown-body th:first-child:not(:last-child),\n.markdown-body td:first-child:not(:last-child)",
    );
    const middle = ruleBody(
      css,
      ".markdown-body th:nth-child(2):not(:last-child),\n.markdown-body td:nth-child(2):not(:last-child)",
    );
    assert.match(first, /width:\s*6\.5rem/);
    assert.match(middle, /width:\s*34%/);
  });
});
