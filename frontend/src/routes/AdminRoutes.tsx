import { Navigate, Route, Routes } from "react-router-dom";
import ConfigPage from "../pages/ConfigPage";
import ScheduledTasksPage from "../pages/ScheduledTasksPage";
import AdminLayout from "../layouts/AdminLayout";
import HealthPage from "../pages/HealthPage";
import YouthReviewPage from "../pages/YouthReviewPage";
import MailSettingsPage from "../pages/MailSettingsPage";
import LobbyDisplayPage from "../pages/LobbyDisplayPage";
import NewslettersPage from "../pages/NewslettersPage";
import AccessRequestsPage from "../pages/AccessRequestsPage";
import LogsPage from "../pages/LogsPage";
import HolidaysPage from "../pages/HolidaysPage";
import StagedAugmentationsPage from "../pages/StagedAugmentationsPage";

/** Admin pages load only after an owner enters the admin route tree. */
export default function AdminRoutes() {
  return (
    <Routes>
      <Route element={<AdminLayout />}>
        <Route index element={<Navigate to="overview" replace />} />
        <Route path="health" element={<HealthPage />} />
        <Route path="dashboard" element={<Navigate to="/admin/health?tab=sync" replace />} />
        <Route path="usage" element={<Navigate to="/admin/health?tab=usage" replace />} />
        <Route path="issues" element={<Navigate to="/admin/health?tab=issues" replace />} />
        <Route path="tasks" element={<ScheduledTasksPage />} />
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
    </Routes>
  );
}
