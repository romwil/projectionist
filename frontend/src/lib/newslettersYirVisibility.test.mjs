/**
 * Regression: Ops → Newsletters must always mount Year in Review UI markers.
 * Mail-not-configured / generate failures are honest states — never omit the panel.
 * (1.32.1 shipped YIR on Mail; iPad Safari users could not reach it. Home is Newsletters.)
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");

describe("Newsletters Year in Review visibility", () => {
  it("always mounts YearInReviewAdminPanel (not gated on mailConfigured)", () => {
    const page = readFileSync(join(root, "pages", "NewslettersPage.jsx"), "utf8");

    assert.match(page, /import YearInReviewAdminPanel from/);
    assert.match(page, /data-testid="admin-newsletters"/);
    assert.match(
      page,
      /<YearInReviewAdminPanel[^>]*testIdPrefix="newsletters"[^>]*mailConfigured=\{mailConfigured\}\s*\/>/,
    );
    // Panel must not be wrapped in a mailConfigured truthiness gate
    assert.equal(
      /mailConfigured\s*&&[\s\S]{0,80}YearInReviewAdminPanel/.test(page),
      false,
      "YearInReviewAdminPanel must not be behind mailConfigured &&",
    );
    assert.equal(
      /mailConfigured\s*\?\s*[\s\S]{0,80}YearInReviewAdminPanel/.test(page),
      false,
      "YearInReviewAdminPanel must not be behind mailConfigured ?",
    );
    // Honest disabled/error note is OK — omitting the panel is not
    assert.match(page, /newsletters-mail-not-configured/);
  });

  it("panel always emits YIR section markers regardless of mailConfigured prop", () => {
    const panel = readFileSync(
      join(root, "components", "admin", "YearInReviewAdminPanel.jsx"),
      "utf8",
    );

    assert.match(panel, /testId=\{`\$\{testIdPrefix\}-yir-panel`\}/);
    assert.match(panel, /data-testid=\{`\$\{testIdPrefix\}-yir-self-generate`\}/);
    assert.match(panel, /Generate my Year in Review/);
    assert.match(panel, /title="Year in Review"/);
    // Default prefix yields newsletters-yir-panel on Ops → Newsletters
    assert.match(panel, /testIdPrefix = "newsletters"/);
    // Test generate is YTD — not a stale prior year
    assert.match(panel, /current calendar year \(year to date\)/);
    assert.match(panel, /yirPathFromGenerateResult/);
    assert.match(panel, /reopen from <Link to="\/inbox">Inbox<\/Link>/);
    // mailConfigured only adds a hint — never an early return that skips the panel
    assert.equal(
      /if\s*\(\s*mailConfigured\s*===?\s*false\s*\)\s*return/.test(panel),
      false,
      "must not early-return when mail is not configured",
    );
    assert.match(panel, /mailConfigured === false \?/);
  });

  it("keeps Mail sticky save bar non-sticky on tablet widths (Safari reachability)", () => {
    const css = readFileSync(join(root, "styles", "06-reading-admin-settings.css"), "utf8");
    assert.match(css, /\.mail-settings-save-bar\s*\{[\s\S]*?position:\s*sticky/);
    assert.match(
      css,
      /@media \(max-width: 1024px\)\s*\{[\s\S]*?\.mail-settings-save-bar\s*\{[\s\S]*?position:\s*static/,
    );
    assert.match(
      css,
      /\.settings-stack\[data-testid="admin-newsletters"\]\s*\{[\s\S]*?safe-area-inset-bottom/,
    );
  });
});
