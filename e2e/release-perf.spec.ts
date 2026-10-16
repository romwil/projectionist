import { execSync } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { expect, test, type Browser } from "@playwright/test";

/**
 * Release page-speed budgets on the mocked e2e server (no live Plex).
 *
 * Measures About, Explore, Movies, Inbox, and Live. A run fails when the
 * median sample exceeds the committed budget in frontend/perf/baseline.json.
 *
 * Record a new baseline (maintainer machine, current main):
 *   RELEASE_PERF_RECORD=1 npm run test:release-perf
 */

const ROOT = process.cwd();
const BASELINE_PATH = path.join(ROOT, "frontend/perf/baseline.json");
const LAST_RUN_PATH = path.join(ROOT, "frontend/perf/last-run.json");
const SAMPLES = 3;
const SETTLE_MS = 400;

const SANE = {
  contentMs: 2500,
  lcpMs: 2500,
  cls: 0.1,
  documentServerMs: 800,
  jsonServerMs: 800,
};

type MetricKey = "contentMs" | "lcpMs" | "cls" | "documentServerMs" | "jsonServerMs";

type Sample = Record<MetricKey, number | null> & {
  contentLabel: string;
  jsonUrl: string | null;
};

type PageSpec = {
  id: string;
  path: string;
  content: string;
  jsonNeedle: string;
};

const PAGES: PageSpec[] = [
  {
    id: "about",
    path: "/about",
    content: "heading “The story”",
    jsonNeedle: "/release-notes.json",
  },
  {
    id: "explore",
    path: "/explore",
    content: "Library Pulse settled (not “Loading pulse…”)",
    jsonNeedle: "/api/library/feeds/hub",
  },
  {
    id: "movies",
    path: "/search?media_type=movie",
    content: "movie results or empty library (not “Loading…”)",
    jsonNeedle: "/api/library/query",
  },
  {
    id: "inbox",
    path: "/inbox",
    content: "heading “Nothing waiting” or inbox rows (not “Loading inbox…”)",
    jsonNeedle: "/api/notifications",
  },
  {
    id: "live",
    path: "/live",
    content: "“Not on the air yet” or Live chrome (not “Filling in the guide…”)",
    jsonNeedle: "/api/live-channels/guide",
  },
];

function installReleasePerf(pageId: string) {
  const perf = {
    contentMs: null as number | null,
    contentLabel: "",
    lcpMs: null as number | null,
    cls: 0,
    lcpSupported: false,
    clsSupported: false,
    error: "",
  };
  window.__releasePerf = perf;
  try {
    new PerformanceObserver((list) => {
      const entries = list.getEntries();
      const last = entries[entries.length - 1];
      if (last) perf.lcpMs = last.startTime;
    }).observe({ type: "largest-contentful-paint", buffered: true });
    perf.lcpSupported = true;
  } catch (err) {
    perf.error = String(err);
  }
  try {
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        const shift = entry as PerformanceEntry & { hadRecentInput?: boolean; value?: number };
        if (!shift.hadRecentInput) perf.cls += shift.value || 0;
      }
    }).observe({ type: "layout-shift", buffered: true });
    perf.clsSupported = true;
  } catch (err) {
    perf.error = String(err);
  }

  function textOf(el: Element) {
    return (el.textContent || "").replace(/\s+/g, " ").trim();
  }
  function heading(name: string) {
    return [...document.querySelectorAll("h1,h2,h3")].some((el) => textOf(el) === name);
  }
  function ready() {
    if (pageId === "about") return heading("The story") ? "The story" : "";
    if (pageId === "explore") {
      if (!heading("Library Pulse")) return "";
      if (document.body && document.body.innerText.includes("Loading pulse")) return "";
      return "Library Pulse";
    }
    if (pageId === "movies") {
      const sections = [...document.querySelectorAll("section")];
      for (const section of sections) {
        const paras = [...section.querySelectorAll("p")].map(textOf);
        const loading = paras.some((item) => item === "Loading…");
        const empty = paras.find((item) => item.startsWith("No titles match") || item.startsWith("No library titles"));
        const cards = section.querySelectorAll("a[href*='/title/']").length;
        if (loading) return "";
        if (empty) return empty;
        if (cards) return "movie grid";
      }
      return "";
    }
    if (pageId === "inbox") {
      const bodyText = document.body ? document.body.innerText : "";
      if (bodyText.includes("Loading inbox")) return "";
      if (textOf(document.body) === "Loading…") return "";
      if (heading("Nothing waiting")) return "Nothing waiting";
      const main = document.querySelector("main");
      if (main && textOf(main).length > 40 && heading("Inbox")) return "inbox rows";
      return "";
    }
    if (pageId === "live") {
      const bodyText = document.body ? document.body.innerText : "";
      if (bodyText.includes("Filling in the guide")) return "";
      if (heading("Not on the air yet")) return "Not on the air yet";
      if (heading("Live")) return "Live";
      return "";
    }
    return "";
  }
  function mark() {
    try {
      if (perf.contentMs != null) return;
      const label = ready();
      if (!label) return;
      perf.contentMs = performance.now();
      perf.contentLabel = label;
    } catch (err) {
      perf.error = String(err);
    }
  }
  if (document.documentElement) {
    new MutationObserver(mark).observe(document.documentElement, {
      childList: true,
      subtree: true,
      characterData: true,
    });
  }
  window.setInterval(mark, 50);
  mark();
}

function roundMs(value: number | null): number | null {
  if (value == null || Number.isNaN(value)) return null;
  return Math.round(value);
}

function roundCls(value: number | null): number | null {
  if (value == null || Number.isNaN(value)) return null;
  return Math.round(value * 10000) / 10000;
}

function median(values: Array<number | null>): number | null {
  const nums = values.filter((value): value is number => value != null).sort((a, b) => a - b);
  if (!nums.length) return null;
  return nums[Math.floor(nums.length / 2)];
}

function msBudget(measured: number, factor: number, add: number, floor: number): number {
  return Math.max(floor, Math.ceil(measured * factor + add));
}

function budgetsFor(medianSample: Sample, runs: Sample[]) {
  const clsSamples = runs.map((run) => run.cls).filter((value): value is number => value != null);
  const worstCls = clsSamples.length ? Math.max(...clsSamples) : null;
  return {
    contentMs: msBudget(medianSample.contentMs ?? 0, 1.75, 500, 1500),
    lcpMs: medianSample.lcpMs == null ? null : msBudget(medianSample.lcpMs, 1.75, 500, 1500),
    cls: worstCls == null ? null : Math.round(Math.max(0.25, worstCls + 0.08) * 1000) / 1000,
    documentServerMs: msBudget(medianSample.documentServerMs ?? 0, 2, 200, 400),
    jsonServerMs: msBudget(medianSample.jsonServerMs ?? 0, 2, 200, 400),
  };
}

function saneNotes(medianSample: Sample): string[] {
  const notes: string[] = [];
  if ((medianSample.contentMs ?? 0) > SANE.contentMs) {
    notes.push(`content ${medianSample.contentMs}ms is over a 2.5s first-content budget; kept as the baseline`);
  }
  if (medianSample.lcpMs != null && medianSample.lcpMs > SANE.lcpMs) {
    notes.push(`LCP ${medianSample.lcpMs}ms is over 2.5s; kept as the baseline`);
  }
  if (medianSample.cls != null && medianSample.cls > SANE.cls) {
    notes.push(`CLS ${medianSample.cls} is over 0.1; kept as the baseline`);
  }
  if ((medianSample.documentServerMs ?? 0) > SANE.documentServerMs) {
    notes.push(`document server time ${medianSample.documentServerMs}ms is over 800ms; kept as the baseline`);
  }
  if ((medianSample.jsonServerMs ?? 0) > SANE.jsonServerMs) {
    notes.push(`JSON server time ${medianSample.jsonServerMs}ms is over 800ms; kept as the baseline`);
  }
  return notes;
}

function gitRevision(): string {
  try {
    return execSync("git rev-parse HEAD", { cwd: ROOT, encoding: "utf8" }).trim();
  } catch {
    return "unknown";
  }
}

async function samplePage(browser: Browser, spec: PageSpec): Promise<Sample> {
  const context = await browser.newContext();
  const page = await context.newPage();
  const client = await context.newCDPSession(page);
  await client.send("Network.setCacheDisabled", { cacheDisabled: true });
  await page.addInitScript(installReleasePerf, spec.id);
  await page.goto(spec.path, { waitUntil: "commit" });
  await page.waitForFunction(() => window.__releasePerf && window.__releasePerf.contentMs != null, undefined, {
    timeout: 20_000,
  });
  await page.waitForTimeout(SETTLE_MS);
  const raw = await page.evaluate((needle: string) => {
    const perf = window.__releasePerf;
    const nav = performance.getEntriesByType("navigation")[0] as PerformanceNavigationTiming | undefined;
    const documentServerMs =
      nav && nav.responseStart && nav.requestStart ? nav.responseStart - nav.requestStart : null;
    const match = performance
      .getEntriesByType("resource")
      .filter((entry) => entry.name.includes(needle))
      .sort((a, b) => a.startTime - b.startTime)[0] as PerformanceResourceTiming | undefined;
    const jsonServerMs =
      match && match.responseStart && match.requestStart ? match.responseStart - match.requestStart : null;
    return {
      contentMs: perf.contentMs,
      contentLabel: perf.contentLabel,
      lcpMs: perf.lcpSupported ? perf.lcpMs : null,
      cls: perf.clsSupported ? perf.cls : null,
      documentServerMs,
      jsonServerMs,
      jsonUrl: match ? match.name : null,
    };
  }, spec.jsonNeedle);
  await context.close();
  return {
    contentMs: roundMs(raw.contentMs),
    lcpMs: roundMs(raw.lcpMs),
    cls: roundCls(raw.cls),
    documentServerMs: roundMs(raw.documentServerMs),
    jsonServerMs: roundMs(raw.jsonServerMs),
    contentLabel: raw.contentLabel,
    jsonUrl: raw.jsonUrl,
  };
}

function summarize(runs: Sample[]): Sample {
  return {
    contentMs: roundMs(median(runs.map((run) => run.contentMs))),
    lcpMs: roundMs(median(runs.map((run) => run.lcpMs))),
    cls: roundCls(median(runs.map((run) => run.cls))),
    documentServerMs: roundMs(median(runs.map((run) => run.documentServerMs))),
    jsonServerMs: roundMs(median(runs.map((run) => run.jsonServerMs))),
    contentLabel: runs[runs.length - 1]?.contentLabel || "",
    jsonUrl: runs.map((run) => run.jsonUrl).find(Boolean) || null,
  };
}

test.describe("release page-speed budgets", () => {
  test("About, Explore, Movies, Inbox, and Live stay within budget", async ({ browser }, testInfo) => {
    test.setTimeout(240_000);
    const revision = gitRevision();
    const measuredAt = new Date().toISOString();
    const pages = [];

    for (const spec of PAGES) {
      const runs: Sample[] = [];
      for (let index = 0; index < SAMPLES; index += 1) {
        runs.push(await samplePage(browser, spec));
      }
      const medianSample = summarize(runs);
      expect(medianSample.contentMs, `${spec.id} content`).not.toBeNull();
      expect(medianSample.jsonServerMs, `${spec.id} JSON ${spec.jsonNeedle}`).not.toBeNull();
      expect(medianSample.documentServerMs, `${spec.id} document`).not.toBeNull();
      pages.push({
        id: spec.id,
        path: spec.path,
        content: spec.content,
        jsonNeedle: spec.jsonNeedle,
        runs,
        median: medianSample,
        notes: saneNotes(medianSample),
      });
    }

    const recording = process.env.RELEASE_PERF_RECORD === "1";
    let baseline: {
      revision: string;
      tolerance: string;
      pages: Array<{ id: string; budget: Record<string, number | null>; median: Sample; notes?: string[] }>;
    };
    if (recording) {
      baseline = {
        revision,
        tolerance:
          "content/LCP budget = max(1500ms, median × 1.75 + 500ms); document/JSON server = max(400ms, median × 2 + 200ms); CLS = max(0.25, worst sample + 0.08). Floors keep laptop-vs-CI noise from failing the job. Medians below a floor still fail once they cross it.",
        pages: pages.map((page) => ({
          id: page.id,
          path: page.path,
          content: page.content,
          jsonNeedle: page.jsonNeedle,
          median: {
            contentMs: page.median.contentMs,
            lcpMs: page.median.lcpMs,
            cls: page.median.cls,
            documentServerMs: page.median.documentServerMs,
            jsonServerMs: page.median.jsonServerMs,
            contentLabel: page.median.contentLabel,
          },
          budget: budgetsFor(page.median, page.runs),
          notes: page.notes,
        })),
      };
    } else {
      baseline = JSON.parse(readFileSync(BASELINE_PATH, "utf8"));
    }

    const report = {
      revision,
      measuredAt,
      baselineRevision: baseline.revision,
      samplesPerPage: SAMPLES,
      pages: pages.map((page) => {
        const budget = baseline.pages.find((item) => item.id === page.id)?.budget;
        return { ...page, budget: budget || null };
      }),
    };

    mkdirSync(path.dirname(LAST_RUN_PATH), { recursive: true });
    if (recording) {
      writeFileSync(BASELINE_PATH, `${JSON.stringify({ ...baseline, measuredAt }, null, 2)}\n`);
    }
    writeFileSync(LAST_RUN_PATH, `${JSON.stringify(report, null, 2)}\n`);
    await testInfo.attach("release-perf.json", {
      body: JSON.stringify(report, null, 2),
      contentType: "application/json",
    });
    console.log(`release-perf ${recording ? "recorded" : "checked"} ${LAST_RUN_PATH}`);
    console.log(JSON.stringify(report, null, 2));

    if (recording) return;

    const failures: string[] = [];
    for (const page of report.pages) {
      const budget = page.budget;
      if (!budget) {
        failures.push(`${page.id}: missing budget in frontend/perf/baseline.json`);
        continue;
      }
      const checks: MetricKey[] = ["contentMs", "lcpMs", "cls", "documentServerMs", "jsonServerMs"];
      for (const key of checks) {
        const actual = page.median[key];
        const limit = budget[key];
        if (actual == null || limit == null) continue;
        if (actual > limit) {
          failures.push(`${page.id} ${key} ${actual} > budget ${limit}`);
        }
      }
    }
    expect(failures, failures.join("\n")).toEqual([]);
  });
});

declare global {
  interface Window {
    __releasePerfPage?: string;
    __releasePerf?: {
      contentMs: number | null;
      contentLabel: string;
      lcpMs: number | null;
      cls: number;
      lcpSupported: boolean;
      clsSupported: boolean;
    };
  }
}
