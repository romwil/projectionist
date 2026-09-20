import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import { readAllStyles } from "./readStyles.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const styles = readAllStyles();
const indexHtml = readFileSync(join(here, "../../index.html"), "utf8");
const appJsx = readFileSync(join(here, "../App.jsx"), "utf8");

describe("native mobile tokens and global touch chrome", () => {
  it("exposes shared tap and input-size tokens", () => {
    assert.match(styles, /--tap-min:\s*44px/);
    assert.match(styles, /--font-size-input:\s*16px/);
  });

  it("kills iOS tap highlight and 300ms delay on interactive chrome", () => {
    assert.match(styles, /-webkit-tap-highlight-color:\s*transparent/);
    assert.match(styles, /touch-action:\s*manipulation/);
  });

  it("does not use 100vw for the Explore page (horizontal bounce)", () => {
    assert.match(styles, /\.explore-page\s*\{[^}]*max-width:\s*100%/s);
    assert.doesNotMatch(styles, /\.explore-page\s*\{[^}]*max-width:\s*100vw/s);
  });

  it("keeps viewport-fit and keyboard-aware interactive-widget", () => {
    assert.match(indexHtml, /viewport-fit=cover/);
    assert.match(indexHtml, /interactive-widget=resizes-content/);
  });
});

describe("native mobile member contract (phone 768)", () => {
  it("keeps composer sticky with 16px input and 44px send/mic", () => {
    assert.match(
      styles,
      /@media \(max-width: 768px\)[\s\S]*?\.composer\s*\{[^}]*position:\s*sticky/s,
    );
    assert.match(
      styles,
      /@media \(max-width: 768px\)[\s\S]*?\.composer textarea\s*\{[^}]*font-size:\s*var\(--font-size-input\)/s,
    );
    assert.match(
      styles,
      /@media \(max-width: 768px\)[\s\S]*?\.composer-send[\s\S]*?min-height:\s*var\(--tap-min\)/s,
    );
  });

  it("does not shrink primary-topbar icons below 44px on phone", () => {
    const phone = styles.match(/@media \(max-width: 768px\)[\s\S]*?@media \(min-width: 1440px\)/)?.[0] || "";
    assert.doesNotMatch(phone, /\.primary-topbar a\.app-topbar-icon[\s\S]{0,120}width:\s*40px/);
  });

  it("gives settings fields a stacked 16px input (no iOS zoom)", () => {
    assert.match(styles, /\.settings-field\s*\{[^}]*display:\s*grid/s);
    assert.match(
      styles,
      /\.settings-field input:not\(\[type="checkbox"\]\)[\s\S]*?font-size:\s*var\(--font-size-input\)/s,
    );
  });

  it("raises member copy to 14px on phone (wizard-note rhythm)", () => {
    assert.match(
      styles,
      /@media \(max-width: 768px\)[\s\S]*?\.settings-field-hint[\s\S]*?font-size:\s*14px/s,
    );
    assert.match(
      styles,
      /@media \(max-width: 768px\)[\s\S]*?\.welcome-panel-hint[\s\S]*?font-size:\s*14px/s,
    );
  });

  it("makes poster hover actions visible on touch and on phone widths", () => {
    assert.match(
      styles,
      /@media \(hover: none\), \(max-width: 768px\)[\s\S]*?\.explore-card-hover-actions/s,
    );
    assert.match(
      styles,
      /@media \(hover: none\), \(max-width: 768px\)[\s\S]*?\.explore-card-hover-actions\s*\{[^}]*pointer-events:\s*none/s,
    );
    assert.match(
      styles,
      /@media \(hover: none\), \(max-width: 768px\)[\s\S]*?\.explore-hover-icon[\s\S]*?pointer-events:\s*auto/s,
    );
  });

  it("collapses /search chrome so the query field wins the phone fold", () => {
    assert.match(styles, /\.media-browse-filters-toggle/);
    assert.match(
      styles,
      /@media \(max-width: 768px\)[\s\S]*?\.media-browse-filters-toggle\s*\{[^}]*min-height:\s*var\(--tap-min\)/s,
    );
    assert.match(
      styles,
      /@media \(max-width: 768px\)[\s\S]*?\.media-browse-secondary-actions[\s\S]*?display:\s*none/s,
    );
    assert.match(
      styles,
      /@media \(max-width: 720px\)[\s\S]*?\.search-page \.explore-search\s*\{[^}]*flex-direction:\s*row/s,
    );
    const page = readFileSync(join(here, "../pages/LibraryBrowsePage.jsx"), "utf8");
    assert.match(page, /isSearchRoute \? null/);
    assert.doesNotMatch(page, /title=\{isSearchRoute \? "Search"/);
    assert.match(
      styles,
      /@media \(max-width: 768px\)[\s\S]*?\.explore-poster-wall\s*\{[^}]*grid-template-columns:\s*repeat\(2/s,
    );
  });

  it("sheets the title overlay to the phone safe area", () => {
    assert.match(
      styles,
      /@media \(max-width: 768px\)[\s\S]*?\.title-detail-drawer-panel[\s\S]*?bottom:\s*0/s,
    );
    assert.match(
      styles,
      /\.title-detail-drawer-close\s*\{[^}]*min-height:\s*var\(--tap-min\)/s,
    );
  });
});

describe("native mobile admin contract (phone 768)", () => {
  it("keeps Live watch mode toggles at 44px", () => {
    assert.match(
      styles,
      /\.live-mode-toggle button\s*\{[^}]*min-height:\s*var\(--tap-min\)/s,
    );
  });

  it("gives admin primary actions 44px taps", () => {
    assert.match(
      styles,
      /@media \(max-width: 768px\)[\s\S]*?button\.primary[\s\S]*?min-height:\s*var\(--tap-min\)/s,
    );
  });

  it("gives Live Channels tabs and Libraries browse controls 44px taps", () => {
    assert.match(
      styles,
      /@media \(max-width: 768px\)[\s\S]*?\.live-channels-tab\s*\{[^}]*min-height:\s*var\(--tap-min\)/s,
    );
    assert.match(
      styles,
      /@media \(max-width: 768px\)[\s\S]*?\.media-browse-controls select[\s\S]*?min-height:\s*var\(--tap-min\)/s,
    );
  });

  it("keeps 1.35.1 admin density: 14px notes and 12px action gaps", () => {
    assert.match(styles, /\.wizard-note[\s\S]{0,80}\.wizard-summary\s*\{[^}]*font-size:\s*14px/s);
    assert.match(styles, /\.service-card-actions\s*\{[^}]*gap:\s*12px/s);
    assert.match(styles, /\.service-fields > button[^{]*\{[^}]*align-self:\s*end/s);
  });
});

describe("narrow pane fit (Simple Browser + phone)", () => {
  it("never ellipsis-clips the Projectionist wordmark", () => {
    assert.match(styles, /\.primary-topbar \.app-topbar-brand\s*\{[^}]*overflow:\s*visible/s);
    assert.match(styles, /\.primary-topbar \.app-topbar-brand\s*\{[^}]*min-width:\s*max-content/s);
    assert.doesNotMatch(
      styles,
      /\.primary-topbar \.app-topbar-brand h1\s*\{[^}]*text-overflow:\s*ellipsis/s,
    );
  });

  it("hides peer icons into the hamburger at ≤900px instead of crowding the brand", () => {
    assert.match(
      styles,
      /@media \(max-width: 900px\)[\s\S]*?\.primary-topbar \.app-topbar-peers\s*\{[^}]*display:\s*none/s,
    );
    assert.match(styles, /\.app-topbar-peers\b/);
    assert.match(styles, /\.app-topbar-cluster\b/);
  });

  it("pins the chat shell to the visible viewport so the composer cannot fall below the fold", () => {
    assert.match(styles, /\.app-root\.workspace\s*\{[^}]*position:\s*fixed/s);
    assert.match(styles, /\.app-root\.workspace\s*\{[^}]*inset:\s*0/s);
    assert.match(styles, /html:has\(\.app-root\.workspace\)[\s\S]*?overflow:\s*hidden/s);
    assert.match(styles, /\.composer\s*\{[^}]*position:\s*sticky/s);
  });

  it("keeps the phone composer to input + send (no mood-chip wall)", () => {
    assert.match(
      styles,
      /@media \(max-width: 768px\)[\s\S]*?\.ambient-context-tag\s*\{[^}]*display:\s*none/s,
    );
    assert.match(
      styles,
      /@media \(max-width: 768px\)[\s\S]*?\.composer \.composer-mood-row\s*\{[^}]*display:\s*none/s,
    );
  });

  it("stacks Overview glance tiles 2-col on a narrow pane", () => {
    assert.match(
      styles,
      /\.owner-health-grid\s*\{[^}]*grid-template-columns:\s*repeat\(2,\s*minmax\(0,\s*1fr\)\)/s,
    );
  });
});

describe("New reply chip stays above the composer", () => {
  it("mounts as a sibling between transcript and composer in App.jsx", () => {
    const workspace = appJsx.match(/<main className="workspace-main"[^>]*>[\s\S]*?<\/main>/)?.[0] || "";
    const scrollAt = workspace.indexOf("chat-scroll-region");
    const chipAt = workspace.indexOf("<NewReplyChip");
    const composerAt = workspace.search(/className="composer[\s"]/);
    assert.ok(scrollAt >= 0 && chipAt > scrollAt && composerAt > chipAt);
  });

  it("does not sticky-overlay the transcript", () => {
    const chipBlock = styles.match(/\.new-reply-chip\s*\{[^}]*\}/s)?.[0] || "";
    assert.match(chipBlock, /flex-shrink:\s*0/);
    assert.match(chipBlock, /min-height:\s*var\(--tap-min\)/);
    assert.doesNotMatch(chipBlock, /position:\s*sticky/);
  });
});
