import assert from "node:assert/strict";
import { readFileSync, unlinkSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import test from "node:test";
import { build } from "esbuild";

const srcDir = join(dirname(fileURLToPath(import.meta.url)), "..");

test("poster results hide the stray loading line; an empty in-flight grid shows a skeleton", async () => {
  const outfile = join(srcDir, ".tmp-browse-grid-pending.mjs");
  await build({
    stdin: {
      contents: `
        import { createElement } from "react";
        import { renderToStaticMarkup } from "react-dom/server";
        import BrowseResultsRegion from "./components/BrowseResultsRegion.jsx";

        export function renderSettled(loading) {
          return renderToStaticMarkup(
            createElement(
              BrowseResultsRegion,
              {
                testId: "library-browse-results",
                loading,
                hasItems: true,
                error: "",
              },
              createElement("article", { "data-testid": "library-browse-card" }, "Lamb"),
            ),
          );
        }

        export function renderWaiting() {
          return renderToStaticMarkup(
            createElement(BrowseResultsRegion, {
              testId: "library-browse-results",
              loading: true,
              hasItems: false,
              error: "",
            }),
          );
        }
      `,
      resolveDir: srcDir,
      sourcefile: "browse-grid-pending-render.jsx",
      loader: "jsx",
    },
    bundle: true,
    format: "esm",
    platform: "node",
    jsx: "automatic",
    packages: "external",
    outfile,
    logLevel: "silent",
  });

  let renderSettled;
  let renderWaiting;
  try {
    ({ renderSettled, renderWaiting } = await import(pathToFileURL(outfile).href));
  } catch (error) {
    unlinkSync(outfile);
    throw error;
  }

  try {
    const withPosters = renderSettled(true);
    assert.match(withPosters, /data-testid="library-browse-results"/);
    assert.match(withPosters, /data-testid="library-browse-card"/);
    assert.match(withPosters, /Lamb/);
    assert.doesNotMatch(withPosters, /Loading/);
    assert.doesNotMatch(withPosters, /browse-grid-pending/);

    const quietAfterLoad = renderSettled(false);
    assert.match(quietAfterLoad, /Lamb/);
    assert.doesNotMatch(quietAfterLoad, /Loading/);

    const waiting = renderWaiting();
    assert.match(waiting, /data-testid="library-browse-results"/);
    assert.match(waiting, /data-testid="browse-grid-pending"/);
    assert.match(waiting, /data-testid="browse-grid-pending-label"/);
    assert.match(waiting, /Loading titles/);
    assert.equal((waiting.match(/data-testid="browse-grid-pending-card"/g) || []).length, 8);
    assert.doesNotMatch(waiting, /status-secondary/);
    assert.doesNotMatch(waiting, /Loading…/);
    assert.doesNotMatch(waiting, /Loading\.\.\./);
  } finally {
    unlinkSync(outfile);
  }

  const region = readFileSync(
    new URL("../components/BrowseResultsRegion.jsx", import.meta.url),
    "utf8",
  );
  assert.match(region, /waiting = Boolean\(loading\) && !hasItems && !error/);
  assert.match(region, /hasItems \? children : null/);

  const styles = readFileSync(new URL("../styles/03-browse-controls.css", import.meta.url), "utf8");
  assert.match(styles, /\.browse-grid-pending-label \{[\s\S]*color: var\(--text\)/);
  assert.match(styles, /html\[data-theme="lights-up"\] \.browse-grid-pending-card/);

  for (const file of [
    "../pages/LibraryBrowsePage.jsx",
    "../pages/TagPage.jsx",
    "../pages/ExploreSectionPage.jsx",
  ]) {
    const source = readFileSync(new URL(file, import.meta.url), "utf8");
    assert.match(source, /<BrowseResultsRegion/);
    assert.doesNotMatch(source, /status status-secondary">Loading/);
  }

  const browse = readFileSync(new URL("../pages/LibraryBrowsePage.jsx", import.meta.url), "utf8");
  assert.match(browse, /browseFacetsFollowGrid\(gridSettled\)/);
  assert.match(browse, /getLibraryAggregate\("language"/);
  assert.match(browse, /queryLibrary\(filters\)/);
  const facetEffect = browse.slice(
    browse.indexOf("if (!browseFacetsFollowGrid(gridSettled)"),
    browse.indexOf("}, [gridSettled, facetScope]);"),
  );
  assert.doesNotMatch(facetEffect, /setState/);
  assert.doesNotMatch(facetEffect, /Loading/);
});
