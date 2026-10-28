import { Navigate } from "react-router-dom";
import { healthTabHref } from "../lib/healthTabs.js";

/** @deprecated Use `/admin/health?tab=issues` — kept for imports; route redirects in main.jsx. */
export default function MediaIssuesPage() {
  return <Navigate to={healthTabHref("issues")} replace />;
}
