import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import App from "./App";
import TitleDetailPage from "./pages/TitleDetailPage";
import ConfigPage from "./pages/ConfigPage";
import LoginPage from "./pages/LoginPage";
import PrivacyPage from "./pages/PrivacyPage";
import AboutPage from "./pages/AboutPage";
import AdminLayout from "./layouts/AdminLayout";
import SettingsLayout from "./layouts/SettingsLayout";
import ProfilePage from "./pages/settings/ProfilePage";
import VoicePage from "./pages/settings/VoicePage";
import WatchlistSettingsPage from "./pages/settings/WatchlistSettingsPage";
import "./styles.css";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<App />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/privacy" element={<PrivacyPage />} />
        <Route path="/about" element={<AboutPage />} />
        <Route path="/config" element={<Navigate to="/admin" replace />} />
        <Route path="/admin" element={<AdminLayout />}>
          <Route index element={<Navigate to="overview" replace />} />
          <Route path=":section" element={<ConfigPage />} />
        </Route>
        <Route path="/settings" element={<SettingsLayout />}>
          <Route index element={<Navigate to="profile" replace />} />
          <Route path="profile" element={<ProfilePage />} />
          <Route path="voice" element={<VoicePage />} />
          <Route path="watchlist" element={<WatchlistSettingsPage />} />
        </Route>
        <Route path="/title/:mediaType/:itemId" element={<TitleDetailPage />} />
      </Routes>
    </BrowserRouter>
  </React.StrictMode>
);
