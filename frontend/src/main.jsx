import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
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
import WatchlistPage from "./pages/WatchlistPage";
import ExplorePage from "./pages/ExplorePage";
import ExploreSectionPage from "./pages/ExploreSectionPage";
import EngagementPage from "./pages/EngagementPage";
import LibraryBrowsePage from "./pages/LibraryBrowsePage";
import PersonPage from "./pages/PersonPage";
import TagPage from "./pages/TagPage";
import TagsPage from "./pages/TagsPage";
import PlotLabPage from "./pages/PlotLabPage";
import ListsPage from "./pages/ListsPage";
import CollectionsPage from "./pages/CollectionsPage";
import LibraryPage from "./pages/LibraryPage";
import MediaIssuesPage from "./pages/MediaIssuesPage";
import YouthReviewPage from "./pages/YouthReviewPage";
import MailSettingsPage from "./pages/MailSettingsPage";
import AccessRequestsPage from "./pages/AccessRequestsPage";
import GuestTourPage from "./pages/GuestTourPage";
import { BulkActionProgressProvider } from "./components/BulkActionProgress";
import WhatsNewGate from "./components/WhatsNewGate";
import "./styles.css";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter>
      <BulkActionProgressProvider>
        <WhatsNewGate />
        <Routes>
          <Route path="/" element={<App />} />
          <Route path="/explore" element={<ExplorePage />} />
          <Route path="/explore/tags" element={<TagsPage />} />
          <Route path="/explore/plot-lab" element={<PlotLabPage />} />
          <Route path="/explore/browse" element={<LibraryBrowsePage />} />
          <Route path="/explore/engagement" element={<EngagementPage />} />
          <Route path="/explore/section/:sectionId" element={<ExploreSectionPage />} />
          <Route path="/watchlist" element={<WatchlistPage />} />
          <Route path="/library" element={<LibraryPage />} />
          <Route path="/library/:pageId" element={<LibraryPage />} />
          <Route path="/lists" element={<ListsPage />} />
          <Route path="/lists/:listId" element={<ListsPage />} />
          <Route path="/collections" element={<CollectionsPage />} />
          <Route path="/collections/:listId" element={<CollectionsPage />} />
          <Route path="/tour" element={<GuestTourPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/privacy" element={<PrivacyPage />} />
          <Route path="/about" element={<AboutPage />} />
          <Route path="/help" element={<HelpPage />} />
          <Route path="/config" element={<Navigate to="/admin" replace />} />
          <Route path="/admin" element={<AdminLayout />}>
            <Route index element={<Navigate to="overview" replace />} />
            <Route path="dashboard" element={<DashboardPage />} />
            <Route path="tasks" element={<ScheduledTasksPage />} />
            <Route path="issues" element={<MediaIssuesPage />} />
            <Route path="youth" element={<YouthReviewPage />} />
            <Route path="access" element={<AccessRequestsPage />} />
            <Route path="mail" element={<MailSettingsPage />} />
            <Route path="scheduled-tasks" element={<Navigate to="/admin/tasks" replace />} />
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
      </BulkActionProgressProvider>
    </BrowserRouter>
  </React.StrictMode>
);
