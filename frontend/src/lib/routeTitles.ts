// A11Y-004: give every route in AppRoutes.tsx a unique, readable
// `document.title` ("<Page> · Projectionist") and a string an aria-live
// announcer can read after navigation ("As a SR user, when I open Help I
// hear 'Help · Projectionist'"). Pure/DOM-free so it is unit-testable
// without a browser; `matchPath` itself does no DOM work.
import { matchPath } from "react-router-dom";

export const APP_NAME = "Projectionist";

function titleCaseSlug(slug: string | undefined): string {
  const value = String(slug || "").trim();
  if (!value) return "";
  return value
    .split(/[-_]+/)
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

type Params = Record<string, string | undefined>;

type RouteTitleEntry = {
  pattern: string;
  title: (params: Params) => string;
};

// Ordered to mirror AppRoutes.tsx: specific paths before the catch-alls
// that share a segment shape (`/library/:pageId`, `/admin/:section`, `*`).
const ROUTE_TITLES: RouteTitleEntry[] = [
  { pattern: "/", title: () => APP_NAME },
  { pattern: "/chat", title: () => "Chat" },
  { pattern: "/search", title: () => "Search" },
  { pattern: "/inbox", title: () => "Inbox" },
  { pattern: "/whisper", title: () => "Whisper Inbox" },
  { pattern: "/year-in-review/:year", title: ({ year }) => `Year in Review ${year || ""}`.trim() },
  { pattern: "/my-journey", title: () => "My Journey" },
  { pattern: "/explore/tags", title: () => "Tags" },
  { pattern: "/explore/related", title: () => "Related Titles" },
  { pattern: "/explore/plot-lab", title: () => "Related Titles" },
  { pattern: "/explore/browse", title: () => "Browse" },
  { pattern: "/explore/engagement", title: () => "My Journey" },
  { pattern: "/explore/section/:sectionId", title: ({ sectionId }) => {
    const label = titleCaseSlug(sectionId);
    return label ? `Explore — ${label}` : "Explore";
  } },
  { pattern: "/explore", title: () => "Explore" },
  { pattern: "/watchlist", title: () => "Watchlist" },
  { pattern: "/live/watch", title: () => "Watching Live" },
  { pattern: "/live/popout", title: () => "Watching Live" },
  { pattern: "/live", title: () => "Live TV" },
  { pattern: "/watch/:ratingKey/popout", title: () => "Now Playing" },
  { pattern: "/watch/:ratingKey", title: () => "Now Playing" },
  { pattern: "/title/episode/:ratingKey", title: () => "Episode" },
  { pattern: "/library/saved/:pageId", title: () => "Saved Page" },
  { pattern: "/library/saved", title: () => "Saved Pages" },
  { pattern: "/library/shelves/:listId", title: () => "Shelf" },
  { pattern: "/library/collections/:listId", title: () => "Collection" },
  { pattern: "/library/:pageId", title: () => "Library" },
  { pattern: "/library", title: () => "Library" },
  { pattern: "/lists/:listId", title: () => "Shelf" },
  { pattern: "/lists", title: () => "Library" },
  { pattern: "/collections/:listId", title: () => "Collection" },
  { pattern: "/collections", title: () => "Library" },
  { pattern: "/tour", title: () => "Sign in" },
  { pattern: "/setup", title: () => "Setup" },
  { pattern: "/login", title: () => "Sign in" },
  { pattern: "/join", title: () => "Join" },
  { pattern: "/privacy", title: () => "Privacy & data use" },
  { pattern: "/about", title: () => "About" },
  { pattern: "/help", title: () => "Help" },
  { pattern: "/config", title: () => "Admin" },
  { pattern: "/admin/health", title: () => "Health" },
  { pattern: "/admin/dashboard", title: () => "Health" },
  { pattern: "/admin/usage", title: () => "Health" },
  { pattern: "/admin/issues", title: () => "Health" },
  { pattern: "/admin/tasks", title: () => "Scheduled Tasks" },
  { pattern: "/admin/youth", title: () => "Youth Review" },
  { pattern: "/admin/holidays", title: () => "Holidays" },
  { pattern: "/admin/taxonomy", title: () => "Taxonomy" },
  { pattern: "/admin/access", title: () => "Access Requests" },
  { pattern: "/admin/mail", title: () => "Mail" },
  { pattern: "/admin/lobby", title: () => "Lobby Display" },
  { pattern: "/admin/newsletters", title: () => "Newsletters" },
  { pattern: "/admin/logs", title: () => "Logs" },
  { pattern: "/admin/scheduled-tasks", title: () => "Scheduled Tasks" },
  { pattern: "/admin/sync", title: () => "Libraries" },
  { pattern: "/admin/:section", title: ({ section }) => titleCaseSlug(section) || "Admin" },
  { pattern: "/admin", title: () => "Admin Overview" },
  { pattern: "/settings/profile", title: () => "Profile" },
  { pattern: "/settings/voice", title: () => "Voice" },
  { pattern: "/settings/taste", title: () => "Taste" },
  { pattern: "/settings/notifications", title: () => "Notifications" },
  { pattern: "/settings/watchlist", title: () => "Watchlist Settings" },
  { pattern: "/settings/lists", title: () => "Lists Settings" },
  { pattern: "/settings", title: () => "Profile" },
  { pattern: "/title/:mediaType/:itemId", title: () => "Title" },
  { pattern: "/person/:tmdbPersonId", title: () => "Person" },
  { pattern: "/tag/:tagName", title: ({ tagName }) => {
    const label = titleCaseSlug(tagName ? decodeURIComponent(tagName) : "");
    return label ? `Tag — ${label}` : "Tags";
  } },
  { pattern: "*", title: () => "Not Found" },
];

/** Resolve the page label for a pathname (no " · Projectionist" suffix). */
export function pageTitleFor(pathname: string): string {
  const path = String(pathname || "/");
  for (const entry of ROUTE_TITLES) {
    const match = matchPath({ path: entry.pattern, end: true }, path);
    if (match) return entry.title((match.params || {}) as Params);
  }
  return APP_NAME;
}

/** Full `document.title` for a pathname, e.g. "Help · Projectionist". */
export function documentTitleFor(pathname: string): string {
  return withAppName(pageTitleFor(pathname));
}

export function withAppName(page: string): string {
  const label = String(page || "").trim();
  return !label || label === APP_NAME ? APP_NAME : `${label} · ${APP_NAME}`;
}

/**
 * A11Y-003: routes whose real name is only known after the item loads.
 * The route announcer waits for the page to name itself instead of
 * reading "Title" for every film.
 */
const ITEM_NAMED_PATTERNS = ["/title/episode/:ratingKey", "/title/:mediaType/:itemId"];

export function routeNamesItself(pathname: string): boolean {
  const path = String(pathname || "/");
  return ITEM_NAMED_PATTERNS.some((pattern) => matchPath({ path: pattern, end: true }, path));
}

/** "Alien (1979)" — or "" until the item has a title. */
export function titlePageName(detail: { title?: unknown; year?: unknown } | null | undefined): string {
  const title = String(detail?.title || "").trim();
  if (!title) return "";
  const year = String(detail?.year || "").trim();
  return /^\d{4}$/.test(year) ? `${title} (${year})` : title;
}

/** "The Wire S01E03" — show name plus code, falling back to the episode title. */
export function episodePageName({
  showTitle,
  episodeTitle,
  code,
}: { showTitle?: unknown; episodeTitle?: unknown; code?: unknown } = {}): string {
  const show = String(showTitle || "").trim();
  const episode = String(episodeTitle || "").trim();
  const sxe = String(code || "").trim();
  if (show && sxe) return `${show} ${sxe}`;
  return show || episode;
}
