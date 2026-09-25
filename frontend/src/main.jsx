import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import AppRoutes from "./AppRoutes";
import { BulkActionProgressProvider } from "./components/BulkActionProgress";
import { TitleDetailOverlayProvider } from "./components/TitleDetailOverlayProvider";
import WhatsNewGate from "./components/WhatsNewGate";
import LiveStickyOsd from "./components/LiveStickyOsd";
import "./styles.css";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter>
      <BulkActionProgressProvider>
        <TitleDetailOverlayProvider>
        <WhatsNewGate />
        <LiveStickyOsd />
        <AppRoutes />
        </TitleDetailOverlayProvider>
      </BulkActionProgressProvider>
    </BrowserRouter>
  </React.StrictMode>
);
