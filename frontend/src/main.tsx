import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import AppRoutes from "./AppRoutes";
import { BulkActionProgressProvider } from "./components/BulkActionProgress";
import { TitleDetailOverlayProvider } from "./components/TitleDetailOverlayProvider";
import WhatsNewGate from "./components/WhatsNewGate";
import LiveStickyOsd from "./components/LiveStickyOsd";
import InAppPlaybackHost from "./components/theater/InAppPlaybackHost";
import "./styles.css";

if (import.meta.env.PROD && "serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js", { type: "module" }).catch(() => {
      // Install still works from the browser when the worker cannot register.
    });
  });
}

const rootEl = document.getElementById("root");
if (!rootEl) throw new Error("Missing #root");
createRoot(rootEl).render(
  <React.StrictMode>
    <BrowserRouter>
      <BulkActionProgressProvider>
        <TitleDetailOverlayProvider>
          <WhatsNewGate />
          <LiveStickyOsd />
          <AppRoutes />
          <InAppPlaybackHost />
        </TitleDetailOverlayProvider>
      </BulkActionProgressProvider>
    </BrowserRouter>
  </React.StrictMode>,
);
