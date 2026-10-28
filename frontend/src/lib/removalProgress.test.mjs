import assert from "node:assert/strict";
import { unlinkSync } from "node:fs";
import { dirname, join } from "node:path";
import { pathToFileURL, fileURLToPath } from "node:url";
import { describe, it } from "node:test";
import { build } from "esbuild";
import {
  applyRemovalProgressEvent,
  createRemovalSession,
  removalProgressView,
} from "./removalProgress.ts";

const GB = 1024 ** 3;
const FIRST_BYTES = Math.round(11.99 * GB);
const SECOND_BYTES = Math.round(1.22 * GB);

function removedEvent(ratingKey, title, bytes, done) {
  return {
    type: "title",
    status: "removed",
    rating_key: ratingKey,
    title,
    done,
    total: 2,
    files_so_far: done,
    folders_so_far: done,
    bytes_freed_so_far: done === 1 ? FIRST_BYTES : FIRST_BYTES + SECOND_BYTES,
    entry: {
      title,
      files: [`/movies/${title}/${title}.mkv`],
      folders: [`/movies/${title}`],
      bytes_freed: bytes,
      bytes_source: "arr",
    },
  };
}

describe("multi-title removal progress", () => {
  it("renders a rising done count before the finished totals", async () => {
    const session = createRemovalSession({
      mode: "full",
      targets: [
        { rating_key: "silence", title: "A Place Called Silence" },
        { rating_key: "dread", title: "Wings of Dread" },
      ],
    });
    const started = removalProgressView(session);
    assert.equal(started.running, true);
    assert.equal(started.titleCountLabel, "0 of 2");
    assert.equal(started.heading, "What is being removed");

    const mid = applyRemovalProgressEvent(
      session,
      removedEvent("silence", "A Place Called Silence", FIRST_BYTES, 1),
    );
    const midView = removalProgressView(mid);
    assert.equal(midView.running, true);
    assert.equal(midView.titleCountLabel, "1 of 2");
    assert.equal(mid.items[0].status, "removed");
    assert.equal(mid.items[0].files.length, 1);
    assert.equal(mid.items[1].status, "waiting");
    assert.ok(Number(mid.bytes_freed) > Number(session.bytes_freed));

    const both = applyRemovalProgressEvent(
      mid,
      removedEvent("dread", "Wings of Dread", SECOND_BYTES, 2),
    );
    const finished = applyRemovalProgressEvent(both, {
      type: "complete",
      result: {
        mode: "full",
        deleted: 2,
        results: both.items.filter((item) => item.status === "removed"),
        errors: [],
        totals: {
          files: 2,
          folders: 2,
          bytes_freed: FIRST_BYTES + SECOND_BYTES,
        },
      },
    });
    const doneView = removalProgressView(finished);
    assert.equal(doneView.running, false);
    assert.equal(doneView.heading, "What was removed");
    assert.equal(doneView.titleCount, 2);
    assert.equal(doneView.titleCountLabel, "2");
    assert.equal(doneView.filesLabel, "2");
    assert.equal(doneView.foldersLabel, "2");

    const srcDir = join(dirname(fileURLToPath(import.meta.url)), "..");
    const outfile = join(srcDir, ".tmp-removal-progress-render.mjs");
    await build({
      stdin: {
        contents: `
          import { createElement } from "react";
          import { renderToStaticMarkup } from "react-dom/server";
          import RemovalSummaryDialog from "./components/RemovalSummaryDialog.tsx";
          export function renderRemoval(result) {
            return renderToStaticMarkup(
              createElement(RemovalSummaryDialog, { open: true, result }),
            );
          }
        `,
        resolveDir: srcDir,
        sourcefile: "removal-render.jsx",
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
    let renderRemoval;
    try {
      ({ renderRemoval } = await import(pathToFileURL(outfile).href));
    } catch (error) {
      unlinkSync(outfile);
      throw error;
    }
    try {
    const htmlStart = renderRemoval(session);
    const htmlMid = renderRemoval(mid);
    const htmlDone = renderRemoval(finished);

    assert.match(htmlStart, /What is being removed/);
    assert.match(htmlStart, /data-testid="removal-progress-count"/);
    assert.match(htmlStart, />0 of 2</);
    assert.match(htmlMid, />1 of 2</);
    assert.match(htmlMid, /A Place Called Silence/);
    assert.match(htmlMid, /\/movies\/A Place Called Silence\/A Place Called Silence\.mkv/);
    assert.match(htmlMid, /Waiting/);
    assert.doesNotMatch(htmlMid, /What was removed/);
    assert.match(htmlDone, /What was removed/);
    assert.doesNotMatch(htmlDone, /removal-progress-count/);
    assert.match(
      htmlDone,
      /data-testid="removal-summary-totals"[\s\S]*?<strong>2<\/strong>[\s\S]*?<span>titles<\/span>/,
    );
    assert.match(htmlDone, new RegExp(doneView.freedLabel.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
    assert.match(htmlDone, /data-testid="removal-summary-done"/);
      assert.match(htmlDone, /Wings of Dread/);
    } finally {
      unlinkSync(outfile);
    }
  });
});
