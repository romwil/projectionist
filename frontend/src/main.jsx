import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes, useLocation, useParams } from "react-router-dom";
import App from "./App";
import TitleDetailPage from "./pages/TitleDetailPage";
import ConfigPage from "./pages/ConfigPage";
import LoginPage from "./pages/LoginPage";
import PrivacyPage from "./pages/PrivacyPage";
import AboutPage from "./pages/AboutPage";
import HelpPage from "./pages/HelpPage";
import NotFoundPage from "./pages/NotFoundPage";
import DashboardPage from "./pages/DashboardPage";
import ScheduledTasksPage from "./pages/ScheduledTasksPage";
import AdminLayout from "./layouts/AdminLayout";
import SettingsLayout from "./layouts/SettingsLayout";
import ProfilePage from "./pages/settings/ProfilePage";
import VoicePage from "./pages/settings/VoicePage";
import WatchlistSettingsPage from "./pages/settings/WatchlistSettingsPage";
import ListsSettingsPage from "./pages/settings/ListsSettingsPage";
import TasteSettingsPage from "./pages/settings/TasteSettingsPage";
import NotificationsSettingsPage from "./pages/settings/NotificationsSettingsPage";
import LivePage from "./pages/LivePage";
import LiveWatchPage from "./pages/LiveWatchPage";
import ExplorePage from "./pages/ExplorePage";
import ExploreSectionPage from "./pages/ExploreSectionPage";
import MyJourneyPage from "./pages/MyJourneyPage";
import SearchPage from "./pages/SearchPage";
import InboxPage from "./pages/InboxPage";
import PersonPage from "./pages/PersonPage";
import TagPage from "./pages/TagPage";
import TagsPage from "./pages/TagsPage";
import RelatedTitlesPage from "./pages/RelatedTitlesPage";
import ListsPage from "./pages/ListsPage";
import CollectionsPage from "./pages/CollectionsPage";
import LibraryPage from "./pages/LibraryPage";
import LibraryHubPage from "./pages/LibraryHubPage";
import MediaIssuesPage from "./pages/MediaIssuesPage";
import YouthReviewPage from "./pages/YouthReviewPage";
import MailSettingsPage from "./pages/MailSettingsPage";
import LobbyDisplayPage from "./pages/LobbyDisplayPage";
import NewslettersPage from "./pages/NewslettersPage";
import AccessRequestsPage from "./pages/AccessRequestsPage";
import LogsPage from "./pages/LogsPage";
import HolidaysPage from "./pages/HolidaysPage";
import StagedAugmentationsPage from "./pages/StagedAugmentationsPage";
import LlmUsagePage from "./pages/LlmUsagePage";
import JoinPage from "./pages/JoinPage";
import SetupWizardPage from "./pages/SetupWizardPage";
import YearInReviewPage from "./pages/YearInReviewPage";
import { BulkActionProgressProvider } from "./components/BulkActionProgress";
import { TitleDetailOverlayProvider } from "./components/TitleDetailOverlayProvider";
import WhatsNewGate from "./components/WhatsNewGate";
import LiveStickyOsd from "./components/LiveStickyOsd";
import { libraryHubPath } from "./lib/libraryTabs.js";
import "./styles.css";

function RedirectLegacyLibraryPage() {
  const { pageId } = useParams();
  return <Navigate to={`/library/saved/${encodeURIComponent(pageId)}`} replace />;
}

function RedirectLegacyListDetail() {
  const { listId } = useParams();
  return <Navigate to={`/library/shelves/${encodeURIComponent(listId)}`} replace />;
}

function RedirectLegacyCollectionDetail() {
  const { listId } = useParams();
  return <Navigate to={`/library/collections/${encodeURIComponent(listId)}`} replace />;
}

function RedirectExploreBrowse() {
  const { search } = useLocation();
  const incoming = new URLSearchParams(search);
  const extra = {};
  const mediaType = incoming.get("media_type");
  const q = incoming.get("q");
  if (mediaType) extra.media_type = mediaType;
  if (q) extra.q = q;
  return <Navigate to={libraryHubPath("browse", extra)} replace />;
}

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter>
      <BulkActionProgressProvider>
        <TitleDetailOverlayProvider>
        <WhatsNewGate />
        <LiveStickyOsd />
        <Routes>
          <Route path="/" element={<Navigate to="/chat" replace />} />
          <Route path="/chat" element={<App />} />
          <Route path="/search" element={<SearchPage />} />
          <Route path="/inbox" element={<InboxPage />} />
          <Route path="/year-in-review/:year" element={<YearInReviewPage />} />
          <Route path="/my-journey" element={<MyJourneyPage />} />
          <Route path="/explore" element={<ExplorePage />} />
          <Route path="/explore/tags" element={<TagsPage />} />
          <Route path="/explore/related" element={<RelatedTitlesPage />} />
          <Route path="/explore/plot-lab" element={<Navigate to="/explore/related" replace />} />
          <Route path="/explore/browse" element={<RedirectExploreBrowse />} />
          <Route path="/explore/engagement" element={<Navigate to="/my-journey" replace />} />
          <Route path="/explore/section/:sectionId" element={<ExploreSectionPage />} />
          <Route path="/watchlist" element={<Navigate to="/library?tab=watchlist" replace />} />
          <Route path="/live" element={<LivePage />} />
          <Route path="/live/watch" element={<LiveWatchPage />} />
          <Route path="/live/popout" element={<LiveWatchPage />} />
          <Route path="/library" element={<LibraryHubPage />} />
          <Route path="/library/saved" element={<LibraryPage />} />
          <Route path="/library/saved/:pageId" element={<LibraryPage />} />
          <Route path="/library/shelves/:listId" element={<ListsPage />} />
          <Route path="/library/collections/:listId" element={<CollectionsPage />} />
          <Route path="/library/:pageId" element={<RedirectLegacyLibraryPage />} />
          <Route path="/lists" element={<Navigate to="/library" replace />} />
          <Route path="/lists/:listId" element={<RedirectLegacyListDetail />} />
          <Route path="/collections" element={<Navigate to="/library?tab=collections" replace />} />
          <Route path="/collections/:listId" element={<RedirectLegacyCollectionDetail />} />
          <Route path="/tour" element={<Navigate to="/login" replace />} />
          <Route path="/setup" element={<SetupWizardPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/join" element={<JoinPage />} />
          <Route path="/privacy" element={<PrivacyPage />} />
          <Route path="/about" element={<AboutPage />} />
          <Route path="/help" element={<HelpPage />} />
          <Route path="/config" element={<Navigate to="/admin" replace />} />
          <Route path="/admin" element={<AdminLayout />}>
            <Route index element={<Navigate to="overview" replace />} />
            <Route path="dashboard" element={<DashboardPage />} />
            <Route path="usage" element={<LlmUsagePage />} />
            <Route path="tasks" element={<ScheduledTasksPage />} />
            <Route path="issues" element={<MediaIssuesPage />} />
            <Route path="youth" element={<YouthReviewPage />} />
            <Route path="holidays" element={<HolidaysPage />} />
            <Route path="taxonomy" element={<StagedAugmentationsPage />} />
            <Route path="access" element={<AccessRequestsPage />} />
            <Route path="mail" element={<MailSettingsPage />} />
            <Route path="lobby" element={<LobbyDisplayPage />} />
            <Route path="newsletters" element={<NewslettersPage />} />
            <Route path="logs" element={<LogsPage />} />
            <Route path="scheduled-tasks" element={<Navigate to="/admin/tasks" replace />} />
            <Route path="sync" element={<Navigate to="/admin/libraries" replace />} />
            <Route path=":section" element={<ConfigPage />} />
          </Route>
          <Route path="/settings" element={<SettingsLayout />}>
            <Route index element={<Navigate to="profile" replace />} />
            <Route path="profile" element={<ProfilePage />} />
            <Route path="voice" element={<VoicePage />} />
            <Route path="taste" element={<TasteSettingsPage />} />
            <Route path="notifications" element={<NotificationsSettingsPage />} />
            <Route path="watchlist" element={<WatchlistSettingsPage />} />
            <Route path="lists" element={<ListsSettingsPage />} />
          </Route>
          <Route path="/title/:mediaType/:itemId" element={<TitleDetailPage />} />
          <Route path="/person/:tmdbPersonId" element={<PersonPage />} />
          <Route path="/tag/:tagName" element={<TagPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
        </TitleDetailOverlayProvider>
      </BulkActionProgressProvider>
    </BrowserRouter>
  </React.StrictMode>
);
