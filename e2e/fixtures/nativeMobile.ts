import { expect, type Locator, type Page } from "@playwright/test";

/** iPhone 12/13 class — official native-mobile QA viewport. */
export const NATIVE_VIEWPORT = { width: 390, height: 844 } as const;

export const TAP_MIN = 44;

export async function assertMinTapSize(locator: Locator, min = TAP_MIN) {
  const box = await locator.boundingBox();
  const name = (await locator.getAttribute("data-testid")) || (await locator.evaluate((el) => el.className));
  expect(box, `${name} should be visible`).not.toBeNull();
  expect(box!.height, `${name} height`).toBeGreaterThanOrEqual(min - 1);
  expect(box!.width, `${name} width`).toBeGreaterThanOrEqual(min - 1);
}

export async function assertNoHorizontalPageOverflow(page: Page) {
  const overflow = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
    innerWidth: window.innerWidth,
  }));
  expect(overflow.scrollWidth).toBeLessThanOrEqual(
    Math.max(overflow.clientWidth, overflow.innerWidth) + 1,
  );
}

/** Composer / sticky chrome should sit on the last slice of the visual viewport. */
export async function assertPinnedNearViewportBottom(
  locator: Locator,
  viewportHeight?: number,
  slack = 32,
) {
  const height = viewportHeight ?? (await locator.page().viewportSize())?.height ?? NATIVE_VIEWPORT.height;
  const box = await locator.boundingBox();
  expect(box).not.toBeNull();
  expect(box!.y + box!.height).toBeGreaterThan(height - slack);
  expect(box!.y + box!.height).toBeLessThanOrEqual(height + 4);
}

export async function computedOverflowY(locator: Locator) {
  return locator.evaluate((el) => getComputedStyle(el).overflowY);
}
