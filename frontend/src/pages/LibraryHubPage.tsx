import { Link, useNavigate, useSearchParams } from "react-router-dom";
import AppShell from "../layouts/AppShell";
import { ROUTES } from "../lib/backNav.js";
import {
  DEFAULT_LIBRARY_TAB,
  LIBRARY_TABS,
  librarySavedPath,
  parseLibraryTab,
} from "../lib/libraryTabs.js";
import ListsPage from "./ListsPage";
import WatchlistPage from "./WatchlistPage";
import CollectionsPage from "./CollectionsPage";
import LibraryBrowsePage from "./LibraryBrowsePage";

export default function LibraryHubPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const activeTab = parseLibraryTab(searchParams);

  function handleTabChange(tabId: string) {
    if (tabId === activeTab) return;
    const next = new URLSearchParams(searchParams);
    if (tabId === DEFAULT_LIBRARY_TAB) next.delete("tab");
    else next.set("tab", tabId);
    const qs = next.toString();
    navigate(qs ? `${ROUTES.library}?${qs}` : ROUTES.library, { replace: true });
  }

  return (
    <AppShell className="app-root library-hub-page" testId="library-hub-page" variant="topbar">
      <section className="explore-section-hero library-hub-hero" data-testid="library-hub-hero">
        <h1 data-testid="library-hub-title">Library</h1>
        <p className="explore-section-subtitle library-hub-lede">
          Lists, watchlist pins, published collections, and the full index — one place.
        </p>
        <p className="library-hub-saved-row">
          <Link to={librarySavedPath()} className="library-hub-saved-link" data-testid="library-hub-saved-link">Saved curator responses</Link>
        </p>
      </section>
      <div className="explore-media-tabs library-hub-tabs" role="tablist" aria-label="Library sections" data-testid="library-hub-tabs">
        {LIBRARY_TABS.map((tab) => (
          <button key={tab.id} type="button" role="tab" aria-selected={activeTab === tab.id} className={`explore-media-tab${activeTab === tab.id ? " is-active" : ""}`} data-testid={tab.testId} onClick={() => handleTabChange(tab.id)}>
            {tab.label}
          </button>
        ))}
      </div>
      {activeTab === "shelves" ? <div data-testid="library-hub-panel-shelves"><ListsPage embedded /></div> : null}
      {activeTab === "watchlist" ? <div data-testid="library-hub-panel-watchlist"><WatchlistPage embedded /></div> : null}
      {activeTab === "collections" ? <div data-testid="library-hub-panel-collections"><CollectionsPage embedded /></div> : null}
      {activeTab === "browse" ? <div data-testid="library-hub-panel-browse"><LibraryBrowsePage embedded /></div> : null}
    </AppShell>
  );
}
