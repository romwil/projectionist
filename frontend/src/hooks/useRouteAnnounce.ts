import { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { documentTitleFor, pageTitleFor, routeNamesItself, withAppName } from "../lib/routeTitles";

const PAGE_NAMED_EVENT = "projectionist:page-named";
// A title page that never loads (error, slow network) still gets announced.
const SELF_NAME_WAIT_MS = 2500;

/**
 * A11Y-004: unique `document.title` per route, focus moved to the page's
 * `<h1>` after navigation (so a screen reader announces it immediately),
 * and a polite announcement string for `RouteAnnouncer` ("Help ·
 * Projectionist") so SR users still hear the new page even when no `<h1>`
 * happens to exist yet on a given page.
 *
 * A11Y-003: title and episode routes name themselves once loaded through
 * `usePageName`; the announcer reads that name instead of "Title".
 *
 * Skips the very first render (initial page load already has its own
 * title/focus from the browser) and only reacts to pathname changes, not
 * query-string-only navigation within the same page.
 */
export function useRouteAnnounce() {
  const { pathname } = useLocation();
  const [announcement, setAnnouncement] = useState("");
  const firstRender = useRef(true);
  const navigated = useRef(false);

  useEffect(() => {
    if (typeof window === "undefined") return undefined;
    function onNamed(event: Event) {
      const name = String((event as CustomEvent).detail || "").trim();
      if (name && navigated.current) setAnnouncement(name);
    }
    window.addEventListener(PAGE_NAMED_EVENT, onNamed);
    return () => window.removeEventListener(PAGE_NAMED_EVENT, onNamed);
  }, []);

  useEffect(() => {
    const title = documentTitleFor(pathname);
    if (typeof document !== "undefined") {
      document.title = title;
    }

    if (firstRender.current) {
      firstRender.current = false;
      return;
    }
    navigated.current = true;

    let fallback: ReturnType<typeof setTimeout> | null = null;
    if (routeNamesItself(pathname)) {
      fallback = setTimeout(() => {
        setAnnouncement((current) => current || pageTitleFor(pathname));
      }, SELF_NAME_WAIT_MS);
      setAnnouncement("");
    } else {
      setAnnouncement(pageTitleFor(pathname));
    }

    if (typeof document === "undefined") return undefined;
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
    return () => {
      cancel(handle);
      if (fallback) clearTimeout(fallback);
    };
  }, [pathname]);

  return announcement;
}

/**
 * A11Y-003: once a page knows its item ("Alien (1979)"), put that name in the
 * tab title and the route announcement. Pass "" while loading.
 */
export function usePageName(name: string) {
  useEffect(() => {
    const label = String(name || "").trim();
    if (!label || typeof document === "undefined") return;
    document.title = withAppName(label);
    if (typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent(PAGE_NAMED_EVENT, { detail: label }));
    }
  }, [name]);
}
