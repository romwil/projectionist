import assert from "node:assert/strict";
import test from "node:test";

import {
  SLASH_COMMANDS,
  executeSlashCommand,
  formatCollectionsDeniedMessage,
  formatCollectionsDisabledMessage,
  formatCollectionsMessage,
  formatHelpMessage,
  formatPurgeMessage,
  formatStatsMessage,
  formatSyncDeniedMessage,
  formatSyncStartedMessage,
  parseSlashCommand,
} from "./slashCommands.js";

test("parseSlashCommand returns null for normal chat", () => {
  assert.equal(parseSlashCommand("find neo-noir films"), null);
  assert.equal(parseSlashCommand("  hello  "), null);
});

test("parseSlashCommand parses command names and args", () => {
  assert.deepEqual(parseSlashCommand("/help"), {
    command: "help",
    args: "",
    raw: "/help",
  });
  assert.deepEqual(parseSlashCommand("  /STATS  "), {
    command: "stats",
    args: "",
    raw: "/STATS",
  });
  assert.deepEqual(parseSlashCommand("/sync full"), {
    command: "sync",
    args: "full",
    raw: "/sync full",
  });
});

test("formatHelpMessage lists core slash commands", () => {
  const text = formatHelpMessage("Flemming");
  assert.match(text, /Flemming slash commands/);
  for (const command of ["help", "stats", "sync", "rate", "purge"]) {
    assert.match(text, new RegExp(`/${command}`));
  }
  assert.doesNotMatch(text, /\/collections/);
});

test("formatHelpMessage includes collections when enabled", () => {
  const text = formatHelpMessage("Flemming", { plexCollectionsEnabled: true });
  assert.match(text, /\/collections/);
});

test("formatStatsMessage renders library counts", () => {
  const text = formatStatsMessage({ movies: 10, shows: 5, total: 15, last_sync: null });
  assert.match(text, /Movies: \*\*10\*\*/);
  assert.match(text, /TV shows: \*\*5\*\*/);
  assert.match(text, /Last sync: never/);
});

test("formatStatsMessage parses last_sync JSON timestamp", () => {
  const recent = JSON.stringify({ items: 15, timestamp: Date.now() / 1000 });
  const text = formatStatsMessage({ movies: 10, shows: 5, total: 15, last_sync: recent });
  assert.match(text, /Last sync: just now/);
  assert.doesNotMatch(text, /Invalid Date/);

  const objectForm = formatStatsMessage({
    movies: 1,
    shows: 0,
    total: 1,
    last_sync: { timestamp: Date.now() / 1000 - 120 },
  });
  assert.match(objectForm, /Last sync: 2 min ago/);

  const bareEpoch = formatStatsMessage({
    movies: 1,
    shows: 0,
    total: 1,
    last_sync: String(Date.now() / 1000 - 7200),
  });
  assert.match(bareEpoch, /Last sync: 2 h ago/);

  const garbage = formatStatsMessage({
    movies: 0,
    shows: 0,
    total: 0,
    last_sync: "{not-json",
  });
  assert.match(garbage, /Last sync: Unknown/);
  assert.doesNotMatch(garbage, /Invalid Date/);
});

test("formatSyncDeniedMessage explains owner-only sync", () => {
  const text = formatSyncDeniedMessage();
  assert.match(text, /owner-only/i);
  assert.match(text, /Config/);
});

test("formatPurgeMessage summarizes purge candidates", () => {
  const text = formatPurgeMessage([
    { title: "Big Movie", recommendation_reason: "4.2 GB, 0 plays" },
  ]);
  assert.match(text, /Purge candidates/);
  assert.match(text, /Big Movie/);
});

test("formatCollectionsMessage lists Plex collections", () => {
  const text = formatCollectionsMessage(
    { items: [{ title: "Neo-Noir" }] },
    { items: [{ title: "Prestige TV" }] },
  );
  assert.match(text, /Neo-Noir/);
  assert.match(text, /Prestige TV/);
});

test("formatStatsMessage handles zeros and missing stats", () => {
  assert.match(formatStatsMessage({ movies: 0, shows: 0, total: 0, last_sync: null }), /Movies: \*\*0\*\*/);
  assert.match(formatStatsMessage(null), /not available yet/);
});

test("formatSyncStartedMessage is friendly without job ids", () => {
  const text = formatSyncStartedMessage({ id: "abc123" });
  assert.match(text, /Library sync queued/i);
  assert.match(text, /status dock/i);
  assert.doesNotMatch(text, /abc123/);
  assert.doesNotMatch(text, /Job `/);
});

test("formatCollectionsDisabledMessage and denied message guide the user", () => {
  assert.match(formatCollectionsDisabledMessage(), /disabled/i);
  assert.match(formatCollectionsDeniedMessage(), /owner/i);
});

test("parseSlashCommand handles bare slash and unknown casing", () => {
  assert.deepEqual(parseSlashCommand("/"), { command: "", args: "", raw: "/" });
  assert.equal(parseSlashCommand("/HELP").command, "help");
});

test("executeSlashCommand help and unknown command", async () => {
  const help = await executeSlashCommand(
    { command: "help", args: "", raw: "/help" },
    { curatorName: "Flemming", getFeatures: async () => ({ features: {} }) },
  );
  assert.equal(help.role, "assistant");
  assert.match(help.blocks[0].content, /Flemming slash commands/);

  const unknown = await executeSlashCommand(
    { command: "wat", args: "", raw: "/wat" },
    { curatorName: "Flemming" },
  );
  assert.match(unknown.blocks[0].content, /Unknown command/);
});

test("executeSlashCommand stats and sync paths", async () => {
  const calls = [];
  const api = async (path, options) => {
    calls.push({ path, options });
    if (path === "/library/stats") {
      return { movies: 0, shows: 0, total: 0, last_sync: null };
    }
    if (path === "/library/sync") {
      return { id: "job-9", status: "queued" };
    }
    throw new Error(`unexpected ${path}`);
  };

  const stats = await executeSlashCommand(
    { command: "stats", args: "", raw: "/stats" },
    { api, curatorName: "Flemming" },
  );
  assert.match(stats.blocks[0].content, /Movies: \*\*0\*\*/);

  const syncDenied = await executeSlashCommand(
    { command: "sync", args: "", raw: "/sync" },
    {
      api,
      getFeatures: async () => ({ features: { multi_user_enabled: true } }),
    },
  );
  assert.match(syncDenied.blocks[0].content, /owner-only/i);

  const syncOk = await executeSlashCommand(
    { command: "sync", args: "", raw: "/sync" },
    {
      api,
      getFeatures: async () => ({ features: { multi_user_enabled: false } }),
    },
  );
  assert.match(syncOk.blocks[0].content, /Library sync queued/i);
  assert.doesNotMatch(syncOk.blocks[0].content, /job-9/);
  assert.equal(calls.some((c) => c.path === "/library/sync" && c.options?.method === "POST"), true);
});

test("SLASH_COMMANDS includes core novice commands", () => {
  for (const name of ["help", "stats", "sync", "rate", "purge"]) {
    assert.equal(SLASH_COMMANDS.includes(name), true);
  }
});

test("/rate without args returns a review batch strip", async () => {
  const calls = [];
  const api = async (path, options) => {
    calls.push({ path, options });
    if (path.startsWith("/reviews/to-rate")) {
      return {
        items: [
          {
            id: "viewed-unrated-1",
            rating_key: "rk-1",
            media_type: "movie",
            title: "Heat",
            completion_pct: 100,
          },
        ],
        count: 1,
      };
    }
    throw new Error(`unexpected ${path}`);
  };
  const message = await executeSlashCommand(
    { command: "rate", args: "", raw: "/rate" },
    { api, curatorName: "Jefferson", user: { preferred_name: "Will" } },
  );
  assert.match(message.blocks[0].content, /^Will —/);
  assert.match(message.blocks[0].content, /half-stars/i);
  assert.doesNotMatch(message.blocks[0].content, /Jefferson/);
  assert.equal(message.blocks[1].type, "review_batch");
  assert.equal(message.blocks[1].payload.prompts[0].title, "Heat");
  assert.equal(calls[0].path.includes("/reviews/to-rate"), true);
});

test("/rate lead uses preferred_name and never curator name", async () => {
  const api = async (path) => {
    if (path.startsWith("/reviews/to-rate")) {
      return { items: [{ id: "1", title: "Heat", media_type: "movie" }], count: 1 };
    }
    throw new Error(`unexpected ${path}`);
  };
  const named = await executeSlashCommand(
    { command: "rate", args: "", raw: "/rate" },
    { api, curatorName: "Jefferson", user: { preferred_name: "Will", display_name: "wrompala" } },
  );
  assert.match(named.blocks[0].content, /^Will —/);

  const neutral = await executeSlashCommand(
    { command: "rate", args: "", raw: "/rate" },
    { api, curatorName: "Jefferson", user: null },
  );
  assert.match(neutral.blocks[0].content, /^Rate what you've watched/);
  assert.doesNotMatch(neutral.blocks[0].content, /Jefferson|Curator/);
});
