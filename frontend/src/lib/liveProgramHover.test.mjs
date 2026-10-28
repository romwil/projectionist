import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { placeProgramHoverCard } from "./liveProgramHover.ts";

/** Visible guide under the top bar, matching a bottom Drive-In row. */
const guide = { top: 128, right: 1440, bottom: 820, left: 0 };

describe("placeProgramHoverCard", () => {
  it("keeps the view link inside the guide when the cell is near the bottom", () => {
    const anchor = { top: 692, bottom: 748, left: 860 };
    const cardHeight = 248;
    const linkHeight = 28;
    const placed = placeProgramHoverCard({
      anchor,
      cardWidth: 260,
      cardHeight,
      bounds: guide,
      linkHeight,
    });

    assert.equal(placed.openUp, true);
    assert.ok(placed.top < anchor.top, "card opens above the cell");
    assert.ok(placed.top >= guide.top);
    assert.ok(placed.viewLinkTop >= guide.top);
    assert.ok(placed.viewLinkBottom <= guide.bottom);
    assert.ok(placed.viewLinkBottom - placed.viewLinkTop >= linkHeight - 0.5);
    assert.equal(placed.top + placed.visibleHeight, placed.viewLinkBottom);
  });

  it("opens downward when the synopsis and view link fit under the cell", () => {
    const anchor = { top: 200, bottom: 256, left: 180 };
    const placed = placeProgramHoverCard({
      anchor,
      cardWidth: 260,
      cardHeight: 180,
      bounds: guide,
      linkHeight: 28,
    });

    assert.equal(placed.openUp, false);
    assert.ok(placed.top >= anchor.bottom);
    assert.ok(placed.viewLinkBottom <= guide.bottom);
    assert.ok(placed.viewLinkTop >= guide.top);
  });

  it("pins the view link inside the guide when the synopsis is taller than the guide", () => {
    const placed = placeProgramHoverCard({
      anchor: { top: 700, bottom: 756, left: 400 },
      cardWidth: 260,
      cardHeight: 1400,
      bounds: guide,
      linkHeight: 32,
    });

    assert.equal(placed.visibleHeight, placed.maxHeight);
    assert.ok(placed.top >= guide.top);
    assert.ok(placed.viewLinkBottom <= guide.bottom);
    assert.ok(placed.viewLinkTop >= guide.top);
    assert.ok(placed.viewLinkTop < placed.viewLinkBottom);
  });
});
