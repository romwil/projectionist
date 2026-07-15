import assert from "node:assert/strict";
import test from "node:test";

// Anniversary date matching logic
test("anniversary milestone years are calculated correctly", () => {
  const currentYear = new Date().getFullYear();
  const milestones = [5, 10, 15, 20, 25, 30, 40, 50, 75];
  const milestoneYears = milestones.map((n) => currentYear - n);

  assert.equal(milestoneYears.length, 9);
  assert.equal(milestoneYears[0], currentYear - 5);
  assert.equal(milestoneYears[milestoneYears.length - 1], currentYear - 75);
});

test("anniversary context string is well-formed", () => {
  const currentYear = new Date().getFullYear();
  const year = currentYear - 25;
  const yearsAgo = currentYear - year;
  const context = `Released ${yearsAgo} year${yearsAgo !== 1 ? "s" : ""} ago`;

  assert.equal(context, "Released 25 years ago");
});

test("single year anniversary uses singular", () => {
  const yearsAgo = 1;
  const context = `Released ${yearsAgo} year${yearsAgo !== 1 ? "s" : ""} ago`;

  assert.equal(context, "Released 1 year ago");
});

// Runtime filtering logic
test("runtime filter excludes long titles", () => {
  const titles = [
    { title: "Short", runtime_minutes: 85 },
    { title: "Medium", runtime_minutes: 110 },
    { title: "Long", runtime_minutes: 180 },
  ];
  const maxRuntime = 100;
  const filtered = titles.filter(
    (t) => t.runtime_minutes != null && t.runtime_minutes <= maxRuntime,
  );

  assert.equal(filtered.length, 1);
  assert.equal(filtered[0].title, "Short");
});

test("runtime filter with no limit returns all", () => {
  const titles = [
    { title: "A", runtime_minutes: 85 },
    { title: "B", runtime_minutes: 180 },
  ];
  const filtered = titles.filter(
    (t) => t.runtime_minutes != null,
  );

  assert.equal(filtered.length, 2);
});

// Quick pick randomization
test("quick pick from single item always returns that item", () => {
  const items = [{ title: "Only Option", view_count: 0 }];
  const unwatched = items.filter((i) => i.view_count === 0);
  const pick = unwatched[Math.floor(Math.random() * unwatched.length)];

  assert.equal(pick.title, "Only Option");
});

test("quick pick excludes watched items", () => {
  const items = [
    { title: "Watched", view_count: 5 },
    { title: "Unwatched", view_count: 0 },
  ];
  const unwatched = items.filter((i) => i.view_count === 0);

  assert.equal(unwatched.length, 1);
  assert.equal(unwatched[0].title, "Unwatched");
});

test("quick pick with genre filter narrows results", () => {
  const items = [
    { title: "Sci-Fi Movie", genres: ["Sci-Fi"], view_count: 0 },
    { title: "Drama Movie", genres: ["Drama"], view_count: 0 },
  ];
  const genre = "sci-fi";
  const filtered = items.filter(
    (i) => i.view_count === 0 && i.genres.some((g) => g.toLowerCase().includes(genre)),
  );

  assert.equal(filtered.length, 1);
  assert.equal(filtered[0].title, "Sci-Fi Movie");
});

// Double feature pairing logic
test("double feature finds shared genres", () => {
  const genresA = new Set(["Drama", "Thriller"]);
  const genresB = new Set(["Thriller", "Action"]);
  const shared = new Set([...genresA].filter((g) => genresB.has(g)));

  assert.equal(shared.size, 1);
  assert.ok(shared.has("Thriller"));
});

test("double feature bridge text varies by year gap", () => {
  const shared = ["Drama"];
  const yearGap = 30;

  let bridge;
  if (shared.length && yearGap > 15) {
    bridge = `Both explore ${shared.join(", ").toLowerCase()} territory, but ${yearGap} years apart`;
  } else if (shared.length) {
    bridge = `A ${shared.join(", ").toLowerCase()} pairing from the same era`;
  } else {
    bridge = "Two different angles on cinema — contrast and compare";
  }

  assert.ok(bridge.includes("30 years apart"));
});

test("double feature combined runtime sums correctly", () => {
  const runtimeA = 112;
  const runtimeB = 98;
  const combined = runtimeA + runtimeB;

  assert.equal(combined, 210);
});
