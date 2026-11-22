import { expect, test, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

/**
 * Real clips, real Chrome, fixture media source. No Plex.
 * Duration is 48 seconds of generated media. After the first frame the
 * playhead runs at 4× so currentTime can pass 30 seconds; the assertion is
 * the playhead, and the file is long enough without that rate.
 */

const fixtureDir =
  process.env.PROJECTIONIST_FIXTURE_MEDIA_DIR || path.join("e2e", ".playback-fixtures");

type CatalogTitle = {
  rating_key: string;
  title: string;
  kind: string;
};

type Catalog = {
  cue: string;
  duration_s: number;
  titles: CatalogTitle[];
};

type ChromeProfile = {
  video?: { codec?: string }[];
  audio?: string[];
};

function catalog(): Catalog {
  return JSON.parse(fs.readFileSync(path.join(fixtureDir, "catalog.json"), "utf8")) as Catalog;
}

/** Planner outcome for these generated clips on the profile Chrome just sent. */
function expectedTier(kind: string, profile: ChromeProfile): string {
  const video = new Set((profile.video || []).map((row) => String(row.codec || "")));
  const audio = new Set(profile.audio || []);
  if (kind === "mpeg2" || !video.has("h264")) return "source-transcode";
  if (kind === "mp4-aac") return "direct";
  if (kind === "mkv-aac") return "remux";
  if (kind === "flac") return audio.has("flac") ? "remux" : "audio";
  if (kind === "truehd" || kind === "dts") return "audio";
  if (kind === "eac3") return audio.has("eac3") ? "remux" : "audio";
  throw new Error(`unknown fixture kind ${kind}`);
}

async function paintedCue(page: Page, cue: string): Promise<boolean> {
  return page.evaluate((needle) => {
    const videos = [...document.querySelectorAll("video")];
    for (const video of videos) {
      const tracks = video.textTracks;
      if (!tracks) continue;
      for (let index = 0; index < tracks.length; index += 1) {
        const track = tracks[index];
        if (!track || track.mode !== "showing") continue;
        const cues = track.activeCues;
        if (!cues) continue;
        for (let cueIndex = 0; cueIndex < cues.length; cueIndex += 1) {
          const text = String((cues[cueIndex] as { text?: string }).text || "");
          if (text.includes(needle)) return true;
        }
      }
    }
    return false;
  }, cue);
}

test.describe.configure({ mode: "serial" });

let chromeProfile: ChromeProfile | null = null;

test("H.264/AAC MP4 planned tier, first frame within 10 seconds, playhead past 30 seconds, and a seek far ahead plays", async ({
  page,
}) => {
  const plexStarts: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/api/library/playback/start")) plexStarts.push(request.url());
  });
  const started = Date.now();
  const sessionResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" && response.url().endsWith("/api/playback/sessions"),
  );
  const frameAt = page
    .waitForFunction(() => {
      const videos = [...document.querySelectorAll("video")];
      return videos.some((video) => video.videoWidth > 0 && video.readyState >= 2);
    }, null, { timeout: 10_000 })
    .then(() => Date.now());
  await page.goto("/watch/fx-h264-aac-mp4", { waitUntil: "commit" });
  const response = await sessionResponse;
  const body = await response.json();
  chromeProfile = response.request().postDataJSON().profile as ChromeProfile;
  const tier = expectedTier("mp4-aac", chromeProfile);
  expect(body.plan, `planned tier is ${tier} (${body.reason})`).toBe(tier);
  expect(tier, "planned tier is direct").toBe("direct");
  expect(body.playable, "planned tier direct is playable").toBe(true);
  const painted = await frameAt;
  expect(painted - started, "first frame within 10 seconds").toBeLessThanOrEqual(10_000);
  await page.evaluate(() => {
    const videos = [...document.querySelectorAll("video")];
    const video =
      videos.find((item) => item.videoWidth > 0) || videos.find((item) => item.currentSrc || item.src);
    if (!video) return;
    video.playbackRate = 4;
    if (video.paused) void video.play();
  });
  await page.waitForFunction(
    () => {
      const videos = [...document.querySelectorAll("video")];
      const video = videos.find((item) => item.videoWidth > 0) || videos[0];
      return Boolean(video && video.currentTime > 30);
    },
    null,
    { timeout: 70_000 },
  );
  const target = await page.evaluate(() => {
    const videos = [...document.querySelectorAll("video")];
    const video = videos.find((item) => item.videoWidth > 0) || videos[0];
    if (!video) return 0;
    const duration = Number(video.duration);
    const next = Number.isFinite(duration) && duration > 36 ? duration - 4 : 40;
    video.currentTime = next;
    return next;
  });
  expect(target, "seek far ahead of the start").toBeGreaterThan(30);
  await page.waitForFunction(
    (mark) => {
      const videos = [...document.querySelectorAll("video")];
      const video = videos.find((item) => item.videoWidth > 0) || videos[0];
      if (!video || video.videoWidth <= 0) return false;
      return Math.abs(video.currentTime - Number(mark)) < 3;
    },
    target,
    { timeout: 10_000 },
  );
  const atSeek = await page.evaluate(() => {
    const videos = [...document.querySelectorAll("video")];
    const video = videos.find((item) => item.videoWidth > 0) || videos[0];
    return video ? video.currentTime : 0;
  });
  await page.waitForFunction(
    (mark) => {
      const videos = [...document.querySelectorAll("video")];
      const video = videos.find((item) => item.videoWidth > 0) || videos[0];
      return Boolean(video && video.currentTime > Number(mark) + 0.2 && video.videoWidth > 0 && !video.paused);
    },
    atSeek,
    { timeout: 10_000 },
  );
  expect(plexStarts, "playback stays on the fixture media source").toEqual([]);
});

test("each fixture reports its planned tier", async ({ page }) => {
  expect(chromeProfile, "Chrome profile captured while H.264/AAC played").toBeTruthy();
  const profile = chromeProfile as ChromeProfile;
  for (const title of catalog().titles) {
    const response = await page.request.post("/api/playback/sessions", {
      data: {
        rating_key: title.rating_key,
        profile,
        engine_opt_in: true,
        start_over: true,
      },
    });
    const body = await response.json();
    const tier = expectedTier(title.kind, profile);
    expect(
      response.ok(),
      `${title.title} session opened for planned tier ${tier} (${response.status()} ${body.detail || body.reason || ""})`,
    ).toBeTruthy();
    expect(body.plan, `${title.title} planned tier is ${tier} (${body.reason})`).toBe(tier);
    if (tier === "source-transcode") {
      expect(body.playable, `${title.title} planned tier source-transcode is not played here`).toBe(false);
      expect(body.provider, `${title.title} planned tier source-transcode uses the fixture source`).toBe(
        "fixture",
      );
    } else {
      expect(body.playable, `${title.title} planned tier ${tier} is playable`).toBe(true);
    }
    if (body.session_id) {
      await page.request.post(`/api/playback/sessions/${encodeURIComponent(body.session_id)}/stop`, {
        data: {},
      });
    }
  }
});

test("H.264 FLAC SRT caption cue paints", async ({ page }) => {
  const listed = catalog();
  const title = listed.titles.find((item) => item.kind === "flac");
  expect(title, "catalog includes the SRT clip").toBeTruthy();
  const cue = listed.cue;
  expect(cue, "caption cue text").toBe("FIXTURE CUE NORTH WINDOW");
  const sessionResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" && response.url().endsWith("/api/playback/sessions"),
  );
  await page.goto(`/watch/${title?.rating_key}`, { waitUntil: "commit" });
  const response = await sessionResponse;
  const body = await response.json();
  const profile = response.request().postDataJSON().profile as ChromeProfile;
  const tier = expectedTier("flac", profile);
  expect(body.plan, `${title?.title} planned tier is ${tier} (${body.reason})`).toBe(tier);
  expect(body.playable, `${title?.title} planned tier ${tier} can show the cue`).toBe(true);
  await expect
    .poll(() => paintedCue(page, cue), {
      timeout: 20_000,
      message: `caption cue ${cue} paints`,
    })
    .toBe(true);
});
