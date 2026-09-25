import { Link } from "react-router-dom";
import InlineAlert from "../../components/InlineAlert";
import SectionHelp from "../../components/SectionHelp";
import { buildHouseholdHealthChips } from "../../lib/householdHealth.js";
import { liveOnboardingTip, liveOverviewLine } from "../../lib/liveChannelsCopy.js";
import { LiveJobRail } from "./LiveChannelsSection";

/**
 * Admin Overview — household health, Live echo, taste export, snapshot.
 * Extracted from ConfigPage (H1 remaining carve after Household/Libraries).
 */
export default function OverviewSection({
  libraryHealth,
  libraryStats,
  verification,
  settings,
  sections,
  featureFlags,
  liveChannelsStatus,
  setShowWizard,
  handleExportTrainingCorpus,
  exportingCorpus,
  handleDownloadAdminSnapshot,
  exportingSnapshot,
  actionAlert,
}) {
  const liveOn = Boolean(settings?.features?.live_channels_enabled);
  const tip = liveOnboardingTip({
    liveEnabled: liveOn,
    libraryMapped: sections.length > 0,
    syncHealthy: Boolean(libraryStats?.last_sync),
  });

  return (
    <>
      <section className="config-section owner-health-hero" data-testid="household-health-hero">
        <div className="dashboard-header owner-health-hero-head">
          <div>
            <p className="eyebrow">At a glance</p>
            <h2 className="dash-title">
              Household health{" "}
              <SectionHelp glossaryKey="Setup" testId="household-health-help" />
            </h2>
            <p className="wizard-note">
              Stack readiness for the living room — Plex, library, and Live in one place.
            </p>
          </div>
          <button type="button" className="ghost" data-testid="rerun-wizard" onClick={() => setShowWizard(true)}>
            Re-run setup
          </button>
        </div>
        <div className="owner-health-grid" data-testid="household-health-grid">
          {buildHouseholdHealthChips({
            libraryHealth,
            libraryStats,
            plexConnected: Boolean(verification.plex || settings?.plex_token_set),
            sectionsCount: sections.length,
            liveEnabled: Boolean(settings?.features?.live_channels_enabled),
            liveReady: Boolean(featureFlags?.features?.live_channels_ready),
            stationCount: Number(liveChannelsStatus?.channel_count) || 0,
          }).map((chip) => (
            <Link
              key={chip.id}
              to={chip.to}
              className={`owner-health-tile tone-${chip.tone}`}
              data-testid={`household-health-chip-${chip.id}`}
            >
              <span className="owner-health-tile-value">{chip.value}</span>
              <span className="owner-health-tile-label">{chip.label}</span>
              <span className="owner-health-tile-detail">{chip.detail}</span>
            </Link>
          ))}
        </div>
      </section>

      {liveOn || tip ? (
        <section className="config-section" data-testid="live-channels-overview-echo">
          {liveOn ? (
            <>
              <h2>Live Channels</h2>
              <p data-testid="live-channels-overview-health">
                {liveOverviewLine(liveChannelsStatus)}
              </p>
              <LiveJobRail job={liveChannelsStatus?.job} compact />
              <div className="config-actions">
                <Link to="/admin/live-channels" className="btn-link" data-testid="live-overview-open">
                  Open Live Channels
                </Link>
              </div>
            </>
          ) : tip ? (
            <>
              <h2>{tip.title}</h2>
              <p>{tip.body}</p>
              <div className="config-actions">
                <Link to={tip.ctaTo} className="btn-link" data-testid="live-onboarding-cta">
                  {tip.ctaLabel}
                </Link>
              </div>
            </>
          ) : null}
        </section>
      ) : null}

      <section className="config-section" data-testid="training-corpus-export">
        <h2>Export taste data</h2>
        <p className="wizard-note">
          Download your chat reactions, saved preferences, and personal reviews as JSON — useful for
          backup or offline experiments.
        </p>
        <div className="config-actions">
          <button
            type="button"
            data-testid="training-corpus-export-button"
            className="primary"
            onClick={handleExportTrainingCorpus}
            disabled={exportingCorpus}
          >
            {exportingCorpus ? "Preparing export…" : "Download taste data"}
          </button>
        </div>
        <InlineAlert
          type={actionAlert?.area === "training-export" ? actionAlert.type : null}
          message={actionAlert?.area === "training-export" ? actionAlert.message : null}
        />
      </section>

      <section className="config-section" data-testid="admin-backup-snapshot">
        <h2>Settings + database snapshot</h2>
        <p className="wizard-note">
          Download a WAL-safe zip of <code>settings.json</code> and the library database for off-box
          backup. Keep your secrets key with the zip if fields are encrypted at rest.
        </p>
        <div className="config-actions">
          <button
            type="button"
            className="primary"
            data-testid="admin-backup-snapshot-button"
            onClick={handleDownloadAdminSnapshot}
            disabled={exportingSnapshot}
          >
            {exportingSnapshot ? "Preparing snapshot…" : "Download snapshot zip"}
          </button>
        </div>
        <InlineAlert
          type={actionAlert?.area === "admin-snapshot" ? actionAlert.type : null}
          message={actionAlert?.area === "admin-snapshot" ? actionAlert.message : null}
        />
      </section>
    </>
  );
}
