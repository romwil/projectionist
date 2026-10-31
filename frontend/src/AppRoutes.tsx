import { lazy, Suspense } from "react";
import { Navigate, Route, Routes, useLocation, useParams } from "react-router-dom";
import { libraryHubPath } from "./lib/libraryTabs.js";

const App = lazy(() => import("./App"));
const AdminRoutes = lazy(() => import("./routes/AdminRoutes"));
const TitleDetailPage = lazy(() => import("./pages/TitleDetailPage"));
const LoginPage = lazy(() => import("./pages/LoginPage"));
const PrivacyPage = lazy(() => import("./pages/PrivacyPage"));
const AboutPage = lazy(() => import("./pages/AboutPage"));
const HelpPage = lazy(() => import("./pages/HelpPage"));
const NotFoundPage = lazy(() => import("./pages/NotFoundPage"));
const SettingsLayout = lazy(() => import("./layouts/SettingsLayout"));
const ProfilePage = lazy(() => import("./pages/settings/ProfilePage"));
const VoicePage = lazy(() => import("./pages/settings/VoicePage"));
const WatchlistSettingsPage = lazy(() => import("./pages/settings/WatchlistSettingsPage"));
const ListsSettingsPage = lazy(() => import("./pages/settings/ListsSettingsPage"));
const TasteSettingsPage = lazy(() => import("./pages/settings/TasteSettingsPage"));
const NotificationsSettingsPage = lazy(() => import("./pages/settings/NotificationsSettingsPage"));
const LivePage = lazy(() => import("./pages/LivePage"));
const LiveWatchPage = lazy(() => import("./pages/LiveWatchPage"));
const LibraryWatchPage = lazy(() => import("./pages/LibraryWatchPage"));
const EpisodeDetailPage = lazy(() => import("./pages/EpisodeDetailPage"));
const ExplorePage = lazy(() => import("./pages/ExplorePage"));
const ExploreSectionPage = lazy(() => import("./pages/ExploreSectionPage"));
const MyJourneyPage = lazy(() => import("./pages/MyJourneyPage"));
const SearchPage = lazy(() => import("./pages/SearchPage"));
const InboxPage = lazy(() => import("./pages/InboxPage"));
const WhisperInboxPage = lazy(() => import("./pages/WhisperInboxPage"));
const PersonPage = lazy(() => import("./pages/PersonPage"));
const TagPage = lazy(() => import("./pages/TagPage"));
const TagsPage = lazy(() => import("./pages/TagsPage"));
const RelatedTitlesPage = lazy(() => import("./pages/RelatedTitlesPage"));
const ListsPage = lazy(() => import("./pages/ListsPage"));
const CollectionsPage = lazy(() => import("./pages/CollectionsPage"));
const LibraryPage = lazy(() => import("./pages/LibraryPage"));
const LibraryHubPage = lazy(() => import("./pages/LibraryHubPage"));
const JoinPage = lazy(() => import("./pages/JoinPage"));
const SetupWizardPage = lazy(() => import("./pages/SetupWizardPage"));
const YearInReviewPage = lazy(() => import("./pages/YearInReviewPage"));

/**
 * SPA route table — extracted from main.jsx (H1 remaining shell carve).
 */
function RedirectLegacyLibraryPage() {
  const { pageId } = useParams();
  return <Navigate to={`/library/saved/${encodeURIComponent(pageId || "")}`} replace />;
}

function RedirectLegacyListDetail() {
  const { listId } = useParams();
  return <Navigate to={`/library/shelves/${encodeURIComponent(listId || "")}`} replace />;
}

function RedirectLegacyCollectionDetail() {
  const { listId } = useParams();
  return <Navigate to={`/library/collections/${encodeURIComponent(listId || "")}`} replace />;
}

function RedirectExploreBrowse() {
  const { search } = useLocation();
  const incoming = new URLSearchParams(search);
  const extra: Record<string, string> = {};
  const mediaType = incoming.get("media_type");
  const q = incoming.get("q");
  if (mediaType) extra.media_type = mediaType;
  if (q) extra.q = q;
  return <Navigate to={libraryHubPath("browse", extra)} replace />;
}

export default function AppRoutes() {
  return (
    <Suspense fallback={<main className="app-loading">Loading…</main>}>
      <Routes>
      <Route path="/" element={<Navigate to="/chat" replace />} />
      <Route path="/chat" element={<App />} />
      <Route path="/search" element={<SearchPage />} />
      <Route path="/inbox" element={<InboxPage />} />
      <Route path="/whisper" element={<WhisperInboxPage />} />
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
      <Route path="/watch/:ratingKey/popout" element={<LibraryWatchPage popout />} />
      <Route path="/watch/:ratingKey" element={<LibraryWatchPage />} />
      <Route path="/title/episode/:ratingKey" element={<EpisodeDetailPage />} />
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
      <Route path="/admin/*" element={<AdminRoutes />} />
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
    </Suspense>
  );
}
