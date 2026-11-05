import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, it } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ManageToggle from "../components/ManageToggle.tsx";
import { bulkManageControls } from "./bulkLibraryDelete.ts";

const src = join(dirname(fileURLToPath(import.meta.url)), "..");

// UX-005: Search (LibraryBrowsePage) and Browse (section + language landings).
const PAGES = [
  ["pages/LibraryBrowsePage.tsx", "library-browse"],
  ["pages/ExploreSectionPage.tsx", "explore-section"],
  ["pages/LanguageLandingPage.tsx", "language-landing"],
];

describe("bulk Delete waits for Manage (UX-005)", () => {
  it("owners see Manage; Delete only after Manage is on", () => {
    assert.deepEqual(bulkManageControls({ isOwner: true }), { showManage: true, showDelete: false });
    assert.deepEqual(bulkManageControls({ isOwner: true, manageOn: true }), {
      showManage: true,
      showDelete: true,
    });
  });

  it("members and youth never see Manage or Delete", () => {
    for (const opts of [
      { isOwner: false },
      { isOwner: false, manageOn: true },
      { isOwner: false, isYouth: true, manageOn: true },
      { isOwner: true, isYouth: true, manageOn: true },
    ]) {
      assert.deepEqual(bulkManageControls(opts), { showManage: false, showDelete: false }, JSON.stringify(opts));
    }
  });

  for (const [file, prefix] of PAGES) {
    it(`${file} renders Delete only inside showDelete and Manage only inside showManage`, () => {
      const source = readFileSync(join(src, file), "utf8");
      assert.match(source, /bulkManageControls\(\{ isOwner, isYouth, manageOn \}\)/);
      const del = source.indexOf(`data-testid="${prefix}-bulk-delete"`);
      assert.ok(del > 0, "delete button present");
      const before = source.slice(Math.max(0, del - 220), del);
      assert.match(before, /\{bulkControls\.showDelete \? \(\s*<button/);
      const manage = source.indexOf(`testId="${prefix}-manage"`);
      assert.ok(manage > 0, "manage toggle present");
      assert.match(source.slice(Math.max(0, manage - 260), manage), /\{bulkControls\.showManage \? \(\s*<ManageToggle/);
      assert.match(source, /function openBulkDelete\(\) \{\n\s*if \(!bulkControls\.showDelete/);
    });
  }

  it("the Manage toggle exposes its pressed state", () => {
    const off = renderToStaticMarkup(createElement(ManageToggle, { on: false, onToggle() {}, testId: "m" }));
    const on = renderToStaticMarkup(createElement(ManageToggle, { on: true, onToggle() {}, testId: "m" }));
    assert.match(off, /aria-pressed="false"[^>]*>Manage</);
    assert.match(on, /aria-pressed="true"[^>]*>Done managing</);
  });
});
