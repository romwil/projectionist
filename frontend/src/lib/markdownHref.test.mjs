import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { isAllowedMarkdownHref, markdownLinkKind } from "./markdownHref.js";

describe("markdown href allowlist", () => {
  it("allows http(s), in-app title/library, and hash fragments", () => {
    assert.equal(markdownLinkKind("https://example.com/a"), "http");
    assert.equal(markdownLinkKind("http://example.com/a"), "http");
    assert.equal(markdownLinkKind("/title/movie/78"), "title");
    assert.equal(markdownLinkKind("/title/show/2199?id_type=tvdb"), "title");
    assert.equal(markdownLinkKind("/library/saved/abc"), "library");
    assert.equal(markdownLinkKind("#fn-1"), "hash");
    assert.equal(markdownLinkKind("#"), "hash");
    assert.equal(isAllowedMarkdownHref("https://example.com"), true);
    assert.equal(isAllowedMarkdownHref("/library/shelves/1"), true);
  });

  it("treats javascript, data, and vbscript schemes as text", () => {
    assert.equal(markdownLinkKind("javascript:alert(1)"), "text");
    assert.equal(markdownLinkKind("JAVASCRIPT:void(0)"), "text");
    assert.equal(markdownLinkKind("data:text/html,hi"), "text");
    assert.equal(markdownLinkKind("vbscript:msgbox"), "text");
    assert.equal(isAllowedMarkdownHref("javascript:alert(1)"), false);
    assert.equal(isAllowedMarkdownHref("data:text/plain,x"), false);
    assert.equal(isAllowedMarkdownHref("vbscript:msgbox"), false);
  });

  it("rejects other schemes and protocol-relative URLs", () => {
    assert.equal(isAllowedMarkdownHref("mailto:x@example.com"), false);
    assert.equal(isAllowedMarkdownHref("ftp://files.example"), false);
    assert.equal(isAllowedMarkdownHref("//evil.example/x"), false);
    assert.equal(isAllowedMarkdownHref("/admin"), false);
    assert.equal(isAllowedMarkdownHref(""), false);
  });
});

describe("MessageText wires the allowlist and rehype-sanitize", () => {
  const src = readFileSync(
    join(dirname(fileURLToPath(import.meta.url)), "../components/MessageText.jsx"),
    "utf8",
  );

  it("uses isAllowedMarkdownHref and rehype-sanitize, not rehype-raw", () => {
    assert.match(src, /isAllowedMarkdownHref/);
    assert.match(src, /rehypeSanitize/);
    assert.match(src, /from "rehype-sanitize"/);
    assert.equal(src.includes("rehype-raw"), false);
    assert.equal(src.includes("rehypeRaw"), false);
  });
});
