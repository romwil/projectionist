import { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { documentTitleFor, pageTitleFor } from "../lib/routeTitles";

/**
 * A11Y-004: unique `document.title` per route, focus moved to the page's
 * `<h1>` after navigation (so a screen reader announces it immediately),
 * and a polite announcement string for `RouteAnnouncer` ("Help ·
 * Projectionist") so SR users still hear the new page even when no `<h1>`
 * happens to exist yet on a given page.
 *
 * Skips the very first render (initial page load already has its own
 * title/focus from the browser) and only reacts to pathname changes, not
 * query-string-only navigation within the same page.
 */
export function useRouteAnnounce() {
  const { pathname } = useLocation();
  const [announcement, setAnnouncement] = useState("");
  const firstRender = useRef(true);

  useEffect(() => {
    const title = documentTitleFor(pathname);
    if (typeof document !== "undefined") {
      document.title = title;
    }

    if (firstRender.current) {
      firstRender.current = false;
      return;
    }

    setAnnouncement(pageTitleFor(pathname));

    if (typeof document === "undefined") return;
    // Let the new route's DOM commit first, then move focus to its heading.
    // Lazy route chunks render a Suspense fallback with no <h1> first, so keep
    // looking for a few seconds instead of giving up after one frame.
    const useRaf = typeof window !== "undefined" && Boolean(window.requestAnimationFrame);
    const schedule = (cb: () => void): number =>
      useRaf ? window.requestAnimationFrame(cb) : (setTimeout(cb, 16) as unknown as number);
    const cancel = (id: number) => {
      if (useRaf) window.cancelAnimationFrame(id);
      else clearTimeout(id);
    };
    const deadline = Date.now() + 3000;
    let handle = 0;
    const tryFocus = () => {
      const heading = document.querySelector<HTMLElement>("main h1, h1");
      if (!heading) {
        if (Date.now() < deadline) handle = schedule(tryFocus);
        return;
      }
      if (!heading.hasAttribute("tabindex")) {
        heading.setAttribute("tabindex", "-1");
      }
      heading.focus();
    };
    handle = schedule(tryFocus);
    return () => cancel(handle);
  }, [pathname]);

  return announcement;
}
