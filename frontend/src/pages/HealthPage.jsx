import { useSearchParams } from "react-router-dom";
import { HEALTH_TABS, resolveHealthTab } from "../lib/healthTabs.js";
import DashboardPage from "./DashboardPage";
import LlmUsagePage from "./LlmUsagePage";
import MediaIssuesPanel from "./MediaIssuesPanel";

export default function HealthPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = resolveHealthTab(searchParams.get("tab"));

  function selectTab(nextTab) {
    const resolved = resolveHealthTab(nextTab);
    if (resolved === "sync") {
      setSearchParams({}, { replace: true });
      return;
    }
    setSearchParams({ tab: resolved }, { replace: true });
  }

  return (
    <div className="admin-page health-page" data-testid="health-page">
      <header className="admin-page-header health-page-header">
        <div>
          <p className="eyebrow">Platform</p>
          <h1>Health</h1>
          <p className="muted">
            Library sync intelligence, LLM spend, and open media issues — one place for ongoing ops.
          </p>
        </div>
      </header>

      <div
        className="explore-media-tabs health-tabs"
        role="tablist"
        aria-label="Health sections"
        data-testid="health-tabs"
      >
        {HEALTH_TABS.map((entry) => (
          <button
            key={entry.id}
            type="button"
            role="tab"
            aria-selected={tab === entry.id}
            className={`explore-media-tab${tab === entry.id ? " is-active" : ""}`}
            data-testid={entry.testId}
            onClick={() => selectTab(entry.id)}
          >
            {entry.label}
          </button>
        ))}
      </div>

      <div className="health-tab-panel" data-testid={`health-panel-${tab}`}>
        {tab === "sync" ? <DashboardPage embedded /> : null}
        {tab === "usage" ? <LlmUsagePage embedded /> : null}
        {tab === "issues" ? <MediaIssuesPanel /> : null}
      </div>
    </div>
  );
}
