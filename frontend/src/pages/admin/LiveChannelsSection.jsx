import { useState } from "react";
import InlineAlert from "../../components/InlineAlert";
import OwnerNowPlayingBreakdown from "../../components/OwnerNowPlayingBreakdown";
import SectionHelp from "../../components/SectionHelp";
import {
  deleteLiveChannelsChannel,
  getLiveChannelsCraftOptions,
  getLiveChannelsPlexAttach,
  getLiveChannelsStarterPack,
  getLiveChannelsStatus,
  patchLiveChannelsEngineSettings,
  patchLiveChannelsStationSettings,
  postLiveChannelsPlexAttachGuide,
  postLiveChannelsPlexRepair,
  postLiveChannelsPreflight,
  previewLiveChannelsCraft,
  publishLiveChannelsChannel,
  publishLiveChannelsFromCollection,
  publishLiveChannelsStarters,
  refillLiveChannelsChannel,
} from "../../api/client";
import {
  buildCraftFiltersPayload,
  craftDraftFromStation,
} from "../../lib/liveChannelsCraft.js";
import {
  CREATE_STATION_MODES,
  craftSoftCapHonestyNote,
  liveHealthSentence,
  liveSetupStepNumbers,
} from "../../lib/liveChannelsCopy.js";

export { buildCraftFiltersPayload, craftDraftFromStation };

export function isLiveChannelsLaunched(status, engineProgress) {
  const engineUp = Boolean(
    status?.broadcast?.sidecar_up || engineProgress?.ready || engineProgress?.http_ready,
  );
  return engineUp && Number(status?.channel_count ?? 0) > 0;
}

export function LiveStatusCheck({ ok, soft = false, children, testId }) {
  const mark = ok ? "✓" : soft ? "○" : "✗";
  const tone = ok ? "ok" : soft ? "soft" : "fail";
  return (
    <li
      className={`live-channels-check live-channels-check-${tone}`}
      data-testid={testId}
    >
      <span className="live-channels-check-mark" aria-hidden="true">
        {mark}
      </span>
      <span className="live-channels-check-body">{children}</span>
    </li>
  );
}

export function LiveReadyBadge({ ready, label = "Ready", testId }) {
  if (!ready) return null;
  return (
    <span className="certified-badge certified-badge-ok" data-testid={testId}>
      ✓ {label}
    </span>
  );
}

/**
 * Admin Live Channels section — Stations | Setup journey + craft.
 * Extracted from ConfigPage (persona UX Phase 1); APIs unchanged.
 */
export default function LiveChannelsSection({
  settings,
  persistSettings,
  updateTunarrSettings,
  updateFeatureFlags,
  testing,
  testResults,
  certifications,
  runTest,
  actionAlert,
  setActionFeedback,
  clearActionFeedback,
  CertifiedBadge,
  liveChannelsStatus,
  setLiveChannelsStatus,
  livePreflight,
  setLivePreflight,
  liveCraftOptions,
  setLiveCraftOptions,
  liveCraft,
  setLiveCraft,
  liveCraftPreview,
  setLiveCraftPreview,
  liveCraftPreviewBusy,
  setLiveCraftPreviewBusy,
  fillerPathDraft,
  setFillerPathDraft,
  padFlexDraft,
  setPadFlexDraft,
  exclusionNameDraft,
  setExclusionNameDraft,
  liveAttach,
  setLiveAttach,
  liveBusy,
  setLiveBusy,
  liveEngineProgress,
  liveEngineError,
  liveContinuityProgress,
  livePublishProgress,
  liveStarters,
  setLiveStarters,
  selectedStarters,
  setSelectedStarters,
  tunarrLogsOpen,
  setTunarrLogsOpen,
  tunarrLogs,
  tunarrLogsBusy,
  liveChannelsTab,
  setLiveChannelsTab,
  stationSettingsOpen,
  setStationSettingsOpen,
  collectionFilter,
  setCollectionFilter,
  filteredLiveCollections,
  liveLaunched,
  effectiveLiveTab,
  fillerBinds,
  handleLiveChannelsEnabled,
  renderLiveBlockAlert,
  renderPublishProgress,
  renderContinuityProgress,
  startBroadcastEngine,
  runContinuityJob,
  runPublishJob,
  refreshTunarrLogs,
  formatPublishFeedback,
}) {
  const [stationCraftDraft, setStationCraftDraft] = useState(null);
  const [stationSettingsSavedId, setStationSettingsSavedId] = useState(null);
  const dockerOrchestration = Boolean(settings?.tunarr?.docker_orchestration);
  const setupSteps = liveSetupStepNumbers({ dockerOrchestration });
  const [createStationMode, setCreateStationMode] = useState("custom");
  const [healthDetailsOpen, setHealthDetailsOpen] = useState(false);

  return (
<section
            className="config-section live-channels-section"
            data-testid="live-channels-settings"
            data-enabled={settings?.features?.live_channels_enabled ? "true" : "false"}
          >
            {!settings?.features?.live_channels_enabled ? (
              <div className="live-channels-hero" data-testid="live-channels-enabled-toggle">
                <p className="eyebrow">Live Channels</p>
                <h2>Your library, on the air</h2>
                <p className="live-channels-hero-lede">
                  Projectionist builds stations from titles you already own and adds them to Plex Live TV
                  as another tuner — alongside any OTA antenna setup you already have. The household
                  watches where they already do.
                </p>
                <div className="wizard-actions">
                  <button
                    type="button"
                    data-testid="live-channels-enable-cta"
                    disabled={liveBusy === "enable" || liveBusy === "disable"}
                    aria-busy={liveBusy === "enable"}
                    onClick={() => handleLiveChannelsEnabled(true)}
                  >
                    {liveBusy === "enable" ? "Turning on…" : "Let's go"}
                  </button>
                </div>
                {renderLiveBlockAlert("hero")}
              </div>
            ) : (
              <>
                <div
                  className="live-channels-on-banner"
                  data-testid="live-channels-enabled-toggle"
                  role="status"
                  aria-live="polite"
                >
                  <div className="live-channels-on-copy">
                    <p className="eyebrow">Live Channels</p>
                    <h2>{liveLaunched ? "Stations on the air" : "Live Channels is on"}</h2>
                    <p className="live-channels-hero-lede">
                      {liveLaunched
                        ? "Craft, refill, and check health here. Engine, breaks, and Plex attach live under Setup."
                        : "Finish the steps below to put stations on the air beside any existing OTA tuner in Plex Live TV. Watching stays in Plex — nothing replaces your antenna DVR."}
                    </p>
                  </div>
                  <button
                    type="button"
                    className="ghost"
                    data-testid="live-channels-disable-cta"
                    disabled={liveBusy === "enable" || liveBusy === "disable"}
                    aria-busy={liveBusy === "disable"}
                    onClick={() => handleLiveChannelsEnabled(false)}
                  >
                    {liveBusy === "disable" ? "Turning off…" : "Turn off"}
                  </button>
                </div>
                {renderLiveBlockAlert("hero")}

                {liveLaunched ? (
                  <div
                    className="live-channels-tabs"
                    role="tablist"
                    aria-label="Live Channels sections"
                    data-testid="live-channels-tabs"
                  >
                    <button
                      type="button"
                      role="tab"
                      aria-selected={effectiveLiveTab === "stations"}
                      className={
                        effectiveLiveTab === "stations"
                          ? "live-channels-tab is-active"
                          : "live-channels-tab"
                      }
                      data-testid="live-channels-tab-stations"
                      onClick={() => setLiveChannelsTab("stations")}
                    >
                      Stations
                    </button>
                    <button
                      type="button"
                      role="tab"
                      aria-selected={effectiveLiveTab === "setup"}
                      className={
                        effectiveLiveTab === "setup"
                          ? "live-channels-tab is-active"
                          : "live-channels-tab"
                      }
                      data-testid="live-channels-tab-installation"
                      onClick={() => setLiveChannelsTab("setup")}
                    >
                      Setup
                    </button>
                  </div>
                ) : null}

                <div
                  className="live-channels-journey"
                  data-live-mode={liveLaunched ? "maintenance" : "setup"}
                >
                  {!liveLaunched || effectiveLiveTab === "stations" ? (
                  <div
                    className={`service-card${
                      liveChannelsStatus?.broadcast?.sidecar_up ? " service-ok" : ""
                    }`}
                    data-testid="live-channels-health-strip"
                  >
                    <div className="service-card-header">
                      <div className="service-card-title">
                        <h3>What's on the air</h3>
                        <LiveReadyBadge
                          ready={Boolean(liveChannelsStatus?.broadcast?.sidecar_up)}
                          label="TV healthy"
                          testId="live-channels-health-ready"
                        />
                      </div>
                      <button
                        type="button"
                        className="ghost"
                        data-testid="live-channels-refresh-status"
                        disabled={liveBusy === "status"}
                        onClick={() => {
                          setLiveBusy("status");
                          getLiveChannelsStatus()
                            .then(setLiveChannelsStatus)
                            .catch((error) => setActionFeedback("live-channels", "error", error.message, { block: "health" }))
                            .finally(() => setLiveBusy(null));
                        }}
                      >
                        Refresh
                      </button>
                    </div>
                    <p className="wizard-note">
                      A quick pulse on stations and anything airing right now.
                    </p>
                    <p className="wizard-note" data-testid="live-channels-health-summary">
                      {liveHealthSentence(liveChannelsStatus)}
                    </p>
                    {renderLiveBlockAlert("health")}
                    {liveChannelsStatus?.guide_index ? (
                      <details
                        className="live-channels-advanced"
                        data-testid="live-channels-guide-index"
                        open={healthDetailsOpen}
                        onToggle={(event) => setHealthDetailsOpen(event.currentTarget.open)}
                      >
                        <summary data-testid="live-channels-health-details">Details</summary>
                        <p className="wizard-note">
                          {liveChannelsStatus.guide_index.owner_hint ||
                            "Refresh after publish or attach."}
                        </p>
                        <ul data-testid="live-channels-guide-index-list">
                          <li>
                            Media libraries enabled:{" "}
                            {liveChannelsStatus.guide_index.media_libraries?.enabled_count ?? 0}
                            {liveChannelsStatus.guide_index.media_libraries?.scanning_count
                              ? ` · scanning ${liveChannelsStatus.guide_index.media_libraries.scanning_count}`
                              : ""}
                          </li>
                          <li>
                            Lineups playable:{" "}
                            {liveChannelsStatus.guide_index.lineup?.playable ? "yes" : "no"}
                            {liveChannelsStatus.guide_index.lineup?.empty_count
                              ? ` (${liveChannelsStatus.guide_index.lineup.empty_count} empty)`
                              : ""}
                          </li>
                          <li>
                            Guide programmes:{" "}
                            {liveChannelsStatus.guide_index.xmltv?.programme_count ?? 0}
                            {" · "}
                            titled content:{" "}
                            {liveChannelsStatus.guide_index.xmltv?.content_programme_count ?? 0}
                          </li>
                          <li>
                            Last Plex guide attach:{" "}
                            {liveChannelsStatus.guide_index.last_attach?.at
                              ? `${liveChannelsStatus.guide_index.last_attach.ok ? "ok" : "failed"} · ${liveChannelsStatus.guide_index.last_attach.at}${
                                  liveChannelsStatus.guide_index.last_attach.dvr_key
                                    ? ` · DVR ${liveChannelsStatus.guide_index.last_attach.dvr_key}`
                                    : ""
                                }`
                              : "not run yet — use Attach guide in Plex under Setup"}
                          </li>
                          <li data-testid="live-channels-plex-mapped">
                            Plex channel map:{" "}
                            {liveChannelsStatus.guide_index.plex_livetv?.expected != null
                              ? `${liveChannelsStatus.guide_index.plex_livetv?.mapped ?? 0}/${liveChannelsStatus.guide_index.plex_livetv.expected}`
                              : "—"}
                            {liveChannelsStatus.guide_index.plex_livetv?.device_present
                              ? ` · device ${liveChannelsStatus.guide_index.plex_livetv.device_status || "present"}`
                              : " · device missing"}
                            {liveChannelsStatus.guide_index.plex_livetv?.hdhr_ok === false
                              ? " · TV engine HDHR unreachable"
                              : ""}
                            {liveChannelsStatus.guide_index.plex_livetv?.mapping_message
                              ? ` — ${liveChannelsStatus.guide_index.plex_livetv.mapping_message}`
                              : ""}
                          </li>
                          {liveChannelsStatus.icon_probe ? (
                            <li data-testid="live-channels-icon-probe">
                              Channel icon probe:{" "}
                              {liveChannelsStatus.icon_probe.ok
                                ? `ok · ${liveChannelsStatus.icon_probe.url || ""}`
                                : liveChannelsStatus.icon_probe.message || "unreachable"}
                            </li>
                          ) : null}
                        </ul>
                      </details>
                    ) : null}
                    {liveChannelsStatus?.last_error && actionAlert?.area !== "live-channels" ? (
                      <InlineAlert
                        type="error"
                        message={liveChannelsStatus.last_error}
                        testId="live-channels-last-error"
                      />
                    ) : null}
                  </div>
                  ) : null}

                  {!liveLaunched || effectiveLiveTab === "stations" ? (
                    <OwnerNowPlayingBreakdown
                      status={liveChannelsStatus}
                      compact
                      onRefreshStatus={async () => {
                        setLiveBusy("status");
                        try {
                          const next = await getLiveChannelsStatus();
                          setLiveChannelsStatus(next);
                        } finally {
                          setLiveBusy(null);
                        }
                      }}
                      onOpenStationSettings={(channelId) => {
                        setStationSettingsOpen(channelId);
                        setLiveChannelsTab("stations");
                      }}
                    />
                  ) : null}

                  {!liveLaunched || effectiveLiveTab === "setup" ? (
                  <>
                  <div
                    className={`service-card ${
                      testResults.tunarr?.state === "success" ||
                      liveChannelsStatus?.broadcast?.sidecar_up ||
                      liveEngineProgress?.ready
                        ? "service-ok"
                        : ""
                    } ${testing === "tunarr" ? "service-loading" : ""} ${testResults.tunarr?.state === "error" ? "service-error" : ""}`}
                  >
                    <div className="service-card-header">
                      <div className="service-card-title">
                        {!liveLaunched ? (
                          <p className="live-channels-step-label">Connection</p>
                        ) : null}
                        <h3>
                          TV engine connection{" "}
                          <SectionHelp glossaryKey="Broadcast engine" testId="live-tv-engine-help" />
                        </h3>
                        <CertifiedBadge
                          certified={
                            certifications.tunarr?.certified ||
                            testResults.tunarr?.state === "success" ||
                            liveChannelsStatus?.broadcast?.sidecar_up
                          }
                          testing={testing === "tunarr"}
                          serviceId="tunarr"
                        />
                        <LiveReadyBadge
                          ready={Boolean(
                            liveEngineProgress?.ready || liveChannelsStatus?.broadcast?.sidecar_up,
                          )}
                          label="Engine ready"
                          testId="live-channels-engine-ready-badge"
                        />
                      </div>
                      <button
                        type="button"
                        data-testid="verify-tunarr"
                        onClick={async () => {
                          clearActionFeedback("live-channels");
                          await runTest("tunarr");
                        }}
                        disabled={testing === "tunarr" || !settings?.tunarr?.url}
                      >
                        {testing === "tunarr" ? "Testing…" : "Test connection"}
                      </button>
                    </div>
                    <p className="wizard-note">
                      Point Projectionist at the TV engine (powered by Tunarr). Most owners leave the URL
                      as-is once Docker has started it.
                    </p>
                    <div className="service-fields">
                      <label>
                        <span>TV engine base URL</span>
                        <input
                          type="text"
                          data-testid="tunarr-url"
                          value={settings?.tunarr?.url ?? ""}
                          placeholder="http://host.docker.internal:8000"
                          onChange={(event) => updateTunarrSettings({ url: event.target.value })}
                          onBlur={() =>
                            persistSettings({
                              tunarr: { ...(settings.tunarr || {}), url: settings?.tunarr?.url ?? "" },
                            }).catch((error) => setActionFeedback("live-channels", "error", error.message, { block: "connection" }))
                          }
                        />
                      </label>
                    </div>
                    <details className="live-channels-advanced">
                      <summary>Advanced</summary>
                      <div className="service-fields">
                        <label>
                          <span>Pinned image tag</span>
                          <input
                            type="text"
                            data-testid="tunarr-image-tag"
                            value={settings?.tunarr?.image_tag ?? "chrisbenincasa/tunarr:1.3.9"}
                            onChange={(event) => updateTunarrSettings({ image_tag: event.target.value })}
                            onBlur={() =>
                              persistSettings({
                                tunarr: {
                                  ...(settings.tunarr || {}),
                                  image_tag:
                                    settings?.tunarr?.image_tag ?? "chrisbenincasa/tunarr:1.3.9",
                                },
                              }).catch((error) =>
                                setActionFeedback("live-channels", "error", error.message, { block: "connection" }),
                              )
                            }
                          />
                        </label>
                      </div>
                      <label className="config-toggle" data-testid="tunarr-docker-orchestration">
                        <input
                          type="checkbox"
                          checked={Boolean(settings?.tunarr?.docker_orchestration)}
                          onChange={(event) => {
                            const orchEnabled = event.target.checked;
                            updateTunarrSettings({ docker_orchestration: orchEnabled });
                            persistSettings({
                              tunarr: { ...(settings.tunarr || {}), docker_orchestration: orchEnabled },
                            }).catch((error) =>
                              setActionFeedback("live-channels", "error", error.message, { block: "connection" }),
                            );
                          }}
                        />
                        <span>
                          Let Projectionist start and stop the TV engine with Docker (needs the Docker socket on the host).
                        </span>
                      </label>
                      <p className="wizard-note">
                        Host flag: <code>PROJECTIONIST_DOCKER_ORCHESTRATION=1</code>
                      </p>
                    </details>
                    {testResults.tunarr?.message &&
                    actionAlert?.area !== "live-channels" &&
                    actionAlert?.area !== "tunarr" ? (
                      <InlineAlert
                        type={testResults.tunarr.state}
                        message={testResults.tunarr.message}
                        testId="live-channels-tunarr-test-alert"
                      />
                    ) : null}
                    {actionAlert?.area === "tunarr" ? (
                      <InlineAlert
                        type={actionAlert.type}
                        message={actionAlert.message}
                        details={actionAlert.details}
                        testId="live-channels-tunarr-action-alert"
                      />
                    ) : null}
                    {renderLiveBlockAlert("connection")}
                  </div>

                  <div
                    className={`service-card${livePreflight?.ready ? " service-ok" : ""}`}
                    data-testid="live-channels-preflight"
                  >
                    <div className="service-card-header">
                      <div className="service-card-title">
                        {!liveLaunched ? (
                          <p className="live-channels-step-label">Step {setupSteps.ready}</p>
                        ) : null}
                        <h3>Check you're ready</h3>
                        <LiveReadyBadge
                          ready={Boolean(livePreflight?.ready)}
                          label="Ready"
                          testId="live-channels-preflight-ready"
                        />
                      </div>
                      <button
                        type="button"
                        data-testid="live-channels-run-preflight"
                        disabled={liveBusy === "preflight"}
                        onClick={async () => {
                          setLiveBusy("preflight");
                          try {
                            const result = await postLiveChannelsPreflight({
                              plex_pass_confirmed: Boolean(settings?.tunarr?.plex_pass_confirmed),
                            });
                            setLivePreflight(result);
                            const hardFails = (result.checks || [])
                              .filter((check) => !check.ok && !check.soft)
                              .map((check) => `${check.label}: ${check.message}`);
                            setActionFeedback("live-channels",
                              result.ready ? "success" : "error",
                              result.summary || "Ready check finished.", { block: "preflight",  details: hardFails },
                            );
                          } catch (error) {
                            setActionFeedback("live-channels", "error", error.message, { block: "preflight" });
                          } finally {
                            setLiveBusy(null);
                          }
                        }}
                      >
                        {liveBusy === "preflight" ? "Checking…" : "Run ready check"}
                      </button>
                    </div>
                    {renderLiveBlockAlert("preflight")}
                    <label className="config-toggle" data-testid="live-channels-plex-pass-confirm">
                      <input
                        type="checkbox"
                        checked={Boolean(settings?.tunarr?.plex_pass_confirmed)}
                        onChange={(event) => {
                          const confirmed = event.target.checked;
                          updateTunarrSettings({ plex_pass_confirmed: confirmed });
                          persistSettings({
                            tunarr: { ...(settings.tunarr || {}), plex_pass_confirmed: confirmed },
                          }).catch((error) => setActionFeedback("live-channels", "error", error.message, { block: "preflight" }));
                        }}
                      />
                      <span>
                        I have an active Plex Pass (needed for Live TV / DVR). Projectionist can't check this
                        for you.
                      </span>
                    </label>
                    {livePreflight?.checks?.length ? (
                      <ul className="live-channels-check-list" data-testid="live-channels-preflight-list">
                        {livePreflight.checks.map((check) => (
                          <LiveStatusCheck key={check.id} ok={check.ok} soft={check.soft}>
                            {check.label}: {check.message}
                          </LiveStatusCheck>
                        ))}
                      </ul>
                    ) : (
                      <p className="wizard-note">
                        Looks for Docker, free disk, a reachable Plex, your Tunarr URL, and the Plex Pass
                        confirmation above.
                      </p>
                    )}
                  </div>

                  {settings?.tunarr?.docker_orchestration ? (
                    <div
                      className={`service-card${liveEngineProgress?.ready ? " service-ok" : ""}`}
                      data-testid="live-channels-lifecycle"
                    >
                      <div className="service-card-header">
                        <div className="service-card-title">
                          {!liveLaunched && setupSteps.engine != null ? (
                            <p className="live-channels-step-label">Step {setupSteps.engine}</p>
                          ) : null}
                          <h3>Start the TV engine</h3>
                          <LiveReadyBadge
                            ready={Boolean(liveEngineProgress?.ready)}
                            label="TV engine ready"
                            testId="live-channels-engine-ready"
                          />
                        </div>
                        <button
                          type="button"
                          data-testid="live-channels-ensure-running"
                          disabled={liveBusy === "lifecycle"}
                          onClick={() => {
                            startBroadcastEngine().catch(() => {});
                          }}
                        >
                          {liveBusy === "lifecycle"
                            ? "Starting…"
                            : liveEngineProgress?.ready
                              ? "Restart engine"
                              : "Start engine"}
                        </button>
                      </div>
                      <p className="wizard-note">
                        Pulls the pinned Docker image and starts the TV engine with a config volume under your data
                        directory. Turning Live Channels off later stops the container but keeps that volume.
                      </p>
                      {liveBusy === "lifecycle" ||
                      (liveEngineProgress &&
                        liveEngineProgress.phase &&
                        liveEngineProgress.phase !== "idle" &&
                        !liveEngineProgress.ready) ||
                      liveEngineProgress?.ready ? (
                        <div
                          className="live-channels-engine-progress"
                          data-testid="live-channels-engine-progress"
                        >
                          {liveEngineProgress?.ready ? (
                            <ul
                              className="live-channels-check-list"
                              data-testid="live-channels-engine-ready-list"
                            >
                              <LiveStatusCheck ok>TV engine ready</LiveStatusCheck>
                              {liveEngineProgress.http_ready ? (
                                <LiveStatusCheck ok>API health: responding</LiveStatusCheck>
                              ) : (
                                <LiveStatusCheck soft>API health: waiting</LiveStatusCheck>
                              )}
                              {liveEngineProgress.logs_ready ? (
                                <LiveStatusCheck ok>Startup log: ready</LiveStatusCheck>
                              ) : (
                                <LiveStatusCheck soft>Startup log: waiting</LiveStatusCheck>
                              )}
                            </ul>
                          ) : (
                            <>
                              <p className="live-channels-engine-progress-headline">
                                {liveEngineProgress?.message ||
                                  (liveBusy === "lifecycle" ? "Starting TV engine…" : "Working…")}
                              </p>
                              <div
                                className={`live-channels-engine-progress-bar${
                                  liveBusy === "lifecycle" &&
                                  !(liveEngineProgress?.percent > 0)
                                    ? " is-indeterminate"
                                    : ""
                                }`}
                                role="progressbar"
                                aria-valuemin={0}
                                aria-valuemax={100}
                                aria-valuenow={
                                  Number.isFinite(liveEngineProgress?.percent)
                                    ? liveEngineProgress.percent
                                    : undefined
                                }
                                aria-label="TV engine start progress"
                              >
                                <span
                                  className="live-channels-engine-progress-fill"
                                  style={{
                                    width: `${Math.max(
                                      8,
                                      Math.min(100, Number(liveEngineProgress?.percent) || 15),
                                    )}%`,
                                  }}
                                />
                              </div>
                              <p className="wizard-note live-channels-engine-phase">
                                {liveEngineProgress?.phase === "pulling"
                                  ? "Pulling image"
                                  : liveEngineProgress?.phase === "creating"
                                    ? "Creating container"
                                    : liveEngineProgress?.phase === "starting"
                                      ? "Starting"
                                      : liveEngineProgress?.phase === "waiting_ready"
                                        ? "Waiting for TV engine ready"
                                        : liveEngineProgress?.phase === "error"
                                          ? "Failed"
                                          : "Working…"}
                                {Number.isFinite(liveEngineProgress?.percent)
                                  ? ` · ${liveEngineProgress.percent}%`
                                  : ""}
                              </p>
                            </>
                          )}
                          {liveEngineError ? (
                            <div
                              className="inline-alert inline-alert-error"
                              data-testid="live-channels-engine-error"
                              role="alert"
                            >
                              <span className="inline-alert-message">{liveEngineError}</span>
                            </div>
                          ) : null}
                        </div>
                      ) : liveEngineError ? (
                        <div
                          className="inline-alert inline-alert-error"
                          data-testid="live-channels-engine-error"
                          role="alert"
                        >
                          <span className="inline-alert-message">{liveEngineError}</span>
                        </div>
                      ) : null}
                      {renderLiveBlockAlert("engine")}
                    </div>
                  ) : null}

                  <div
                    className={`service-card${
                      liveChannelsStatus?.continuity?.ok ? " service-ok" : ""
                    }`}
                    data-testid="live-channels-filler-paths"
                  >
                    <div className="service-card-header">
                      <div className="service-card-title">
                        {!liveLaunched ? (
                          <p className="live-channels-step-label">Step {setupSteps.breaks}</p>
                        ) : null}
                        <h3>
                          Between-show breaks{" "}
                          <SectionHelp
                            glossaryKey="Filler programming paths"
                            testId="live-breaks-help"
                          />
                        </h3>
                        <LiveReadyBadge
                          ready={Boolean(liveChannelsStatus?.continuity?.ok)}
                          label="Breaks ready"
                          testId="live-channels-continuity-ready"
                        />
                      </div>
                      <button
                        type="button"
                        className="ghost"
                        data-testid="live-channels-rescan-filler"
                        disabled={liveBusy === "continuity-repair"}
                        onClick={async () => {
                          if (
                            !window.confirm(
                              "Rescan filler and repair continuity? This remounts filler paths if needed, force-scans the local filler library, attaches the shared list, and warms streams. Active Live TV sessions may briefly drop while the TV engine restarts.",
                            )
                          ) {
                            return;
                          }
                          try {
                            await runContinuityJob(
                              {
                                rescan: true,
                                repair: true,
                                refill_lineups: true,
                              },
                              { successFallback: "Filler rescan finished.", block: "filler" },
                            );
                          } catch {
                            /* feedback already set */
                          }
                        }}
                      >
                        {liveBusy === "continuity-repair" ? "Working…" : "Rescan filler"}
                      </button>
                    </div>
                    <p className="wizard-note">
                      Commercial-cut shows often need a few minutes of bumpers between episodes.
                      Add host folders of trailers / shorts — Projectionist mounts each path into the
                      TV engine and builds one randomized break list for every station. Gap fill
                      caps pads toward :00/:30 (0 = back-to-back). Exclusion skips a named Plex
                      collection (default NoLive) during station fill.
                    </p>
                    {!liveLaunched || effectiveLiveTab === "setup"
                      ? renderContinuityProgress()
                      : null}
                    {renderLiveBlockAlert("filler")}
                    <ul
                      className="live-channels-check-list"
                      data-testid="live-channels-continuity-checks"
                    >
                      {(liveChannelsStatus?.continuity?.checks || []).map((check) => (
                        <LiveStatusCheck
                          key={check.id}
                          ok={check.ok}
                          soft={check.soft}
                          testId={`live-channels-install-continuity-${check.id}`}
                        >
                          {check.label}: {check.message}
                        </LiveStatusCheck>
                      ))}
                    </ul>
                    <div className="service-fields" data-testid="live-channels-filler-editor">
                      {(fillerBinds || []).map((bind, index) => (
                        <div
                          key={`${bind}-${index}`}
                          className="live-channels-filler-row"
                          data-testid={`live-channels-filler-row-${index}`}
                        >
                          <code>{bind}</code>
                          <button
                            type="button"
                            className="ghost"
                            data-testid={`live-channels-filler-remove-${index}`}
                            onClick={() => {
                              const next = fillerBinds.filter((_, i) => i !== index);
                              updateTunarrSettings({ filler_binds: next });
                              persistSettings({
                                tunarr: { ...(settings.tunarr || {}), filler_binds: next },
                              }).catch((error) =>
                                setActionFeedback("live-channels", "error", error.message, { block: "filler" }),
                              );
                            }}
                          >
                            Remove
                          </button>
                        </div>
                      ))}
                      <label>
                        Add host folder
                        <input
                          type="text"
                          data-testid="live-channels-filler-path-input"
                          placeholder="/mnt/user/media/bumpers"
                          value={fillerPathDraft}
                          onChange={(event) => setFillerPathDraft(event.target.value)}
                        />
                      </label>
                      <button
                        type="button"
                        data-testid="live-channels-filler-add"
                        disabled={!fillerPathDraft.trim()}
                        onClick={() => {
                          const path = fillerPathDraft.trim();
                          if (!path) return;
                          const next = [...fillerBinds, path];
                          updateTunarrSettings({ filler_binds: next });
                          setFillerPathDraft("");
                          persistSettings({
                            tunarr: { ...(settings.tunarr || {}), filler_binds: next },
                          })
                            .then(() =>
                              setActionFeedback("live-channels",
                                "success",
                                "Filler path saved. Restart the broadcast engine if it is already running so Tunarr picks up the new mount, then Rescan filler.",
                              { block: "filler" },
                              ),
                            )
                            .catch((error) =>
                              setActionFeedback("live-channels", "error", error.message, { block: "filler" }),
                            );
                        }}
                      >
                        Add path
                      </button>
                    </div>
                    <div className="service-fields" data-testid="live-channels-schedule-settings">
                      <label>
                        Gap fill (minutes)
                        <input
                          type="number"
                          min={0}
                          max={30}
                          data-testid="live-channels-pad-flex"
                          value={padFlexDraft}
                          placeholder={String(
                            liveCraftOptions?.pad_flex_max_minutes ??
                              settings?.tunarr?.pad_flex_max_minutes ??
                              15,
                          )}
                          onChange={(event) => setPadFlexDraft(event.target.value)}
                        />
                      </label>
                      <label>
                        Exclusion collection name
                        <input
                          type="text"
                          data-testid="live-channels-exclusion-name"
                          value={exclusionNameDraft}
                          placeholder="NoLive"
                          onChange={(event) => setExclusionNameDraft(event.target.value)}
                        />
                      </label>
                      <label>
                        Preferred subtitle language
                        <input
                          type="text"
                          data-testid="live-channels-subtitle-lang-primary"
                          defaultValue={settings?.tunarr?.subtitle_language_primary || "en"}
                          placeholder="en"
                          maxLength={8}
                          name="subtitle_language_primary"
                        />
                      </label>
                      <label>
                        Fallback language (optional)
                        <input
                          type="text"
                          data-testid="live-channels-subtitle-lang-fallback"
                          defaultValue={settings?.tunarr?.subtitle_language_fallback || ""}
                          placeholder="es"
                          maxLength={8}
                          name="subtitle_language_fallback"
                        />
                      </label>
                      <label className="live-channels-checkbox">
                        <input
                          type="checkbox"
                          data-testid="live-channels-subtitles-default"
                          defaultChecked={Boolean(settings?.tunarr?.subtitles_enabled_default)}
                          name="subtitles_enabled_default"
                        />
                        New stations: show captions when available
                      </label>
                    </div>
                    <p className="wizard-note">
                      Language prefs guide “Ask Plex for subtitles” and the Live CC picker.
                      Projectionist never pulls from an outside subtitle marketplace — only Plex’s
                      own agents.
                    </p>
                    <div className="wizard-actions">
                      <button
                        type="button"
                        className="ghost"
                        data-testid="live-channels-save-schedule-settings"
                        disabled={liveBusy === "engine-settings"}
                        onClick={async () => {
                          setLiveBusy("engine-settings");
                          try {
                            const minutes = Number(padFlexDraft);
                            const root = document.querySelector(
                              '[data-testid="live-channels-schedule-settings"]',
                            );
                            const primary =
                              root?.querySelector('[name="subtitle_language_primary"]')?.value ||
                              "en";
                            const fallback =
                              root?.querySelector('[name="subtitle_language_fallback"]')?.value ||
                              "";
                            const captionsDefault = Boolean(
                              root?.querySelector('[name="subtitles_enabled_default"]')?.checked,
                            );
                            const result = await patchLiveChannelsEngineSettings({
                              pad_flex_max_minutes: Number.isFinite(minutes) ? minutes : 15,
                              exclusion_collection_name: exclusionNameDraft || "NoLive",
                              auto_refresh_stations_after_sync: true,
                              subtitle_language_primary: primary,
                              subtitle_language_fallback: fallback,
                              subtitles_enabled_default: captionsDefault,
                            });
                            setPadFlexDraft(String(result.pad_flex_max_minutes ?? minutes));
                            setExclusionNameDraft(
                              result.exclusion_collection_name || exclusionNameDraft || "NoLive",
                            );
                            updateTunarrSettings({
                              pad_flex_max_minutes: result.pad_flex_max_minutes,
                              exclusion_collection_name: result.exclusion_collection_name,
                              auto_refresh_stations_after_sync:
                                result.auto_refresh_stations_after_sync,
                              subtitle_language_primary: result.subtitle_language_primary,
                              subtitle_language_fallback: result.subtitle_language_fallback,
                              subtitles_enabled_default: result.subtitles_enabled_default,
                            });
                            setActionFeedback(
                              "live-channels",
                              "success",
                              `Saved gap fill ${result.pad_flex_max_minutes}m · exclusion “${result.exclusion_collection_name}” · captions ${result.subtitle_language_primary || "en"}.`,
                              { block: "filler" },
                            );
                          } catch (error) {
                            setActionFeedback("live-channels", "error", error.message, {
                              block: "filler",
                            });
                          } finally {
                            setLiveBusy(null);
                          }
                        }}
                      >
                        {liveBusy === "engine-settings" ? "Saving…" : "Save gap fill, exclusion & captions"}
                      </button>
                    </div>
                  </div>

                  
                  </>
                  ) : null}

                  {!liveLaunched || effectiveLiveTab === "stations" ? (
                  <>
                  <div className="service-card" data-testid="live-channels-starters">
                    <div className="service-card-header">
                      <div className="service-card-title">
                        {!liveLaunched ? (
                          <p className="live-channels-step-label">
                            Step {setupSteps.create}
                          </p>
                        ) : null}
                        <h3>Create a station</h3>
                      </div>
                      {createStationMode === "starters" || !liveLaunched ? (
                      <button
                        type="button"
                        className="ghost"
                        data-testid="live-channels-load-starters"
                        disabled={liveBusy === "starters"}
                        onClick={async () => {
                          setCreateStationMode("starters");
                          setLiveBusy("starters");
                          try {
                            const pack = await getLiveChannelsStarterPack();
                            setLiveStarters(pack);
                            const next = {};
                            for (const proposal of pack.proposals || []) {
                              next[`${proposal.number}:${proposal.name}`] = true;
                            }
                            setSelectedStarters(next);
                          } catch (error) {
                            setActionFeedback("live-channels", "error", error.message, { block: "connection" });
                          } finally {
                            setLiveBusy(null);
                          }
                        }}
                      >
                        {liveBusy === "starters" ? "Loading…" : "Propose starters"}
                      </button>
                      ) : null}
                    </div>
                    <p className="wizard-note">
                      Pick how to build a station. Publish fills lineups from your library and skips
                      channel numbers that already exist (Refill refreshes empty lineups).
                    </p>
                    {renderLiveBlockAlert("starters")}

                    <div
                      className="live-mode-toggle live-channels-create-modes"
                      role="group"
                      aria-label="Create station mode"
                      data-testid="live-channels-create-modes"
                    >
                      {CREATE_STATION_MODES.map((mode) => (
                        <button
                          key={mode.id}
                          type="button"
                          className={createStationMode === mode.id ? "is-active" : ""}
                          data-testid={`live-channels-create-mode-${mode.id}`}
                          onClick={() => {
                            setCreateStationMode(mode.id);
                            if (mode.id === "collection") {
                              setLiveCraft((prev) => ({
                                ...prev,
                                source: "collection",
                                programming_mode:
                                  prev.programming_mode === "shuffle" ? "shuffle" : "sequential",
                              }));
                            } else if (mode.id === "custom" && liveCraft.source === "collection") {
                              setLiveCraft((prev) => ({
                                ...prev,
                                source: "motif",
                                programming_mode: "shuffle",
                              }));
                            }
                          }}
                        >
                          {mode.label}
                        </button>
                      ))}
                    </div>

                    {createStationMode === "custom" ? (
                    <div className="live-channels-craft-block" data-testid="live-channels-craft">
                      <p className="wizard-note">
                        {liveCraftOptions?.hint ||
                          "Name the station, pick a motif / taste cluster / youth-safe source, then publish."}
                      </p>
                      <div className="service-fields live-channels-craft-fields">
                        <label>
                          Station name
                          <input
                            type="text"
                            data-testid="live-channels-craft-name"
                            value={liveCraft.name}
                            placeholder="e.g. Midnight Mystery"
                            onChange={(event) =>
                              setLiveCraft((prev) => ({ ...prev, name: event.target.value }))
                            }
                          />
                        </label>
                        <label>
                          Channel number
                          <input
                            type="number"
                            min={1}
                            data-testid="live-channels-craft-number"
                            value={liveCraft.number}
                            onChange={(event) =>
                              setLiveCraft((prev) => ({ ...prev, number: event.target.value }))
                            }
                          />
                        </label>
                        <label>
                          Station source
                          <select
                            data-testid="live-channels-craft-source"
                            value={liveCraft.source}
                            onChange={(event) => {
                              const source = event.target.value;
                              setLiveCraft((prev) => ({
                                ...prev,
                                source,
                                programming_mode:
                                  source === "collection" ? "sequential" : "shuffle",
                                youth_safe: source === "youth",
                              }));
                            }}
                          >
                            {(liveCraftOptions?.sources || [
                              { id: "motif", label: "Plot motif" },
                              { id: "taste_cluster", label: "Taste cluster" },
                              { id: "collection", label: "Collection / list" },
                              { id: "youth", label: "Youth-safe" },
                            ]).map((src) => (
                              <option key={src.id} value={src.id}>
                                {src.label}
                              </option>
                            ))}
                          </select>
                        </label>
                        <label>
                          Play order
                          <select
                            data-testid="live-channels-craft-mode"
                            value={liveCraft.programming_mode}
                            onChange={(event) =>
                              setLiveCraft((prev) => ({
                                ...prev,
                                programming_mode: event.target.value,
                              }))
                            }
                          >
                            {(liveCraftOptions?.programming_modes || [
                              { id: "shuffle", label: "Shuffle" },
                              { id: "sequential", label: "Sequential" },
                            ]).map((mode) => (
                              <option key={mode.id} value={mode.id}>
                                {mode.label}
                              </option>
                            ))}
                          </select>
                        </label>
                        <label>
                          Media
                          <select
                            data-testid="live-channels-craft-media-scope"
                            value={liveCraft.media_scope || "both"}
                            onChange={(event) =>
                              setLiveCraft((prev) => ({
                                ...prev,
                                media_scope: event.target.value,
                                collection_id: "",
                                collection_title: "",
                              }))
                            }
                          >
                            {(liveCraftOptions?.media_scopes || [
                              { id: "tv", label: "TV" },
                              { id: "movies", label: "Movies" },
                              { id: "both", label: "Both" },
                            ]).map((scope) => (
                              <option key={scope.id} value={scope.id}>
                                {scope.label}
                              </option>
                            ))}
                          </select>
                        </label>
                        {liveCraft.source === "motif" ? (
                          <label>
                            Motif
                            <select
                              data-testid="live-channels-craft-motif"
                              value={liveCraft.motif}
                              onChange={(event) =>
                                setLiveCraft((prev) => ({
                                  ...prev,
                                  motif: event.target.value,
                                  name: prev.name || event.target.value,
                                }))
                              }
                            >
                              <option value="">Select a motif…</option>
                              {(liveCraftOptions?.motifs || []).map((motif) => (
                                <option key={motif.value} value={motif.value}>
                                  {motif.label}
                                  {motif.count ? ` (${motif.count})` : ""}
                                </option>
                              ))}
                            </select>
                          </label>
                        ) : null}
                        {liveCraft.source === "taste_cluster" ? (
                          <label>
                            Taste cluster
                            <select
                              data-testid="live-channels-craft-cluster"
                              value={liveCraft.cluster_tag}
                              onChange={(event) =>
                                setLiveCraft((prev) => ({
                                  ...prev,
                                  cluster_tag: event.target.value,
                                  name: prev.name || event.target.value,
                                }))
                              }
                            >
                              <option value="">Select a cluster…</option>
                              {(liveCraftOptions?.taste_clusters || []).map((cluster) => (
                                <option key={cluster.cluster_tag} value={cluster.cluster_tag}>
                                  {cluster.label}
                                </option>
                              ))}
                            </select>
                          </label>
                        ) : null}
                        {liveCraft.source === "collection" ? (
                          <label className="live-channels-craft-collection">
                            Collection
                            <input
                              type="search"
                              className="live-channels-collection-filter"
                              data-testid="live-channels-craft-collection-filter"
                              placeholder="Search collections…"
                              value={collectionFilter}
                              onChange={(event) => setCollectionFilter(event.target.value)}
                              autoComplete="off"
                            />
                            <select
                              data-testid="live-channels-craft-collection"
                              className="live-channels-collection-select"
                              value={liveCraft.collection_id}
                              onChange={(event) => {
                                const id = event.target.value;
                                const match = (liveCraftOptions?.collections || []).find(
                                  (row) => row.id === id,
                                );
                                setLiveCraft((prev) => ({
                                  ...prev,
                                  collection_id: id,
                                  collection_title: match?.title || "",
                                  name: prev.name || match?.title || "",
                                }));
                              }}
                            >
                              <option value="">Select a collection…</option>
                              {filteredLiveCollections.map((row) => (
                                <option key={row.id || row.title} value={row.id} title={row.label}>
                                  {row.label}
                                  {row.source === "plex" ? " · Plex" : ""}
                                  {row.source === "published" ? " · Published" : ""}
                                  {row.item_count ? ` (${row.item_count})` : ""}
                                </option>
                              ))}
                            </select>
                            {!(liveCraftOptions?.collections || []).length ? (
                              <p
                                className="wizard-note"
                                data-testid="live-channels-craft-collections-empty"
                              >
                                {liveCraftOptions?.collections_empty_hint ||
                                  liveCraftOptions?.collections_error ||
                                  "No collections loaded. Create one in Plex, or publish a Projectionist list."}
                              </p>
                            ) : (
                              <p
                                className="wizard-note live-channels-collection-count"
                                data-testid="live-channels-craft-collections-count"
                              >
                                {collectionFilter.trim()
                                  ? `${filteredLiveCollections.length} match${
                                      filteredLiveCollections.length === 1 ? "" : "es"
                                    } of ${liveCraftOptions.collections_total} collections`
                                  : `${liveCraftOptions.collections_total} collection${
                                      liveCraftOptions.collections_total === 1 ? "" : "s"
                                    } available`}
                              </p>
                            )}
                          </label>
                        ) : null}
                        <details
                          className="live-channels-craft-filters live-channels-advanced"
                          data-testid="live-channels-craft-filters"
                        >
                          <summary>Narrow the pool</summary>
                          <p className="wizard-note">
                            Additive filters (AND) — e.g. 1970s ∩ Action ∩ martial-arts theme ∩ Movies.
                            Titles in the “{liveCraftOptions?.exclusion_collection_name || "NoLive"}”
                            Plex collection are skipped.
                          </p>
                          <label>
                            Genre
                            <select
                              data-testid="live-channels-craft-genre"
                              value={liveCraft.genres?.[0] || ""}
                              onChange={(event) =>
                                setLiveCraft((prev) => ({
                                  ...prev,
                                  genres: event.target.value ? [event.target.value] : [],
                                }))
                              }
                            >
                              <option value="">Any genre</option>
                              {(liveCraftOptions?.filter_options?.genres || []).map((row) => (
                                <option key={row.value} value={row.value}>
                                  {row.label}
                                  {row.count ? ` (${row.count})` : ""}
                                </option>
                              ))}
                            </select>
                          </label>
                          <label>
                            Decade
                            <select
                              data-testid="live-channels-craft-decade"
                              value={liveCraft.decade === "" || liveCraft.decade == null ? "" : String(liveCraft.decade)}
                              onChange={(event) =>
                                setLiveCraft((prev) => ({
                                  ...prev,
                                  decade: event.target.value,
                                }))
                              }
                            >
                              <option value="">Any decade</option>
                              {(liveCraftOptions?.filter_options?.decades || []).map((row) => (
                                <option key={row.value} value={String(row.value)}>
                                  {row.label}
                                  {row.count ? ` (${row.count})` : ""}
                                </option>
                              ))}
                            </select>
                          </label>
                          <label>
                            Theme
                            <select
                              data-testid="live-channels-craft-theme"
                              value={liveCraft.theme || ""}
                              onChange={(event) =>
                                setLiveCraft((prev) => ({
                                  ...prev,
                                  theme: event.target.value,
                                }))
                              }
                            >
                              <option value="">Any theme</option>
                              {(liveCraftOptions?.filter_options?.themes || []).map((row) => (
                                <option key={row.value} value={row.value}>
                                  {row.label}
                                  {row.count ? ` (${row.count})` : ""}
                                </option>
                              ))}
                            </select>
                          </label>
                          <label>
                            Rating
                            <select
                              data-testid="live-channels-craft-rating"
                              value={liveCraft.content_rating || ""}
                              onChange={(event) =>
                                setLiveCraft((prev) => ({
                                  ...prev,
                                  content_rating: event.target.value,
                                }))
                              }
                            >
                              <option value="">Any rating</option>
                              {(liveCraftOptions?.filter_options?.content_ratings || []).map(
                                (row) => (
                                  <option key={row.value} value={row.value}>
                                    {row.label}
                                    {row.count ? ` (${row.count})` : ""}
                                  </option>
                                ),
                              )}
                            </select>
                          </label>
                          <div className="wizard-actions">
                            <button
                              type="button"
                              className="ghost"
                              data-testid="live-channels-craft-preview"
                              disabled={liveCraftPreviewBusy}
                              onClick={async () => {
                                setLiveCraftPreviewBusy(true);
                                try {
                                  const result = await previewLiveChannelsCraft({
                                    media_scope: liveCraft.media_scope || "both",
                                    source: liveCraft.source || "",
                                    collection_id:
                                      liveCraft.source === "collection"
                                        ? liveCraft.collection_id
                                        : "",
                                    craft_filters: buildCraftFiltersPayload(liveCraft),
                                  });
                                  setLiveCraftPreview(result);
                                } catch (error) {
                                  setLiveCraftPreview({
                                    matched: 0,
                                    note: error.message || "Preview failed.",
                                  });
                                } finally {
                                  setLiveCraftPreviewBusy(false);
                                }
                              }}
                            >
                              {liveCraftPreviewBusy ? "Counting…" : "Preview match count"}
                            </button>
                            {liveCraftPreview ? (
                              <p
                                className="wizard-note"
                                data-testid="live-channels-craft-preview-result"
                                data-fill-mode={liveCraftPreview.fill_mode || ""}
                                data-soft-capped={
                                  liveCraftPreview.soft_capped ? "true" : "false"
                                }
                              >
                                {craftSoftCapHonestyNote(liveCraftPreview)
                                  || liveCraftPreview.note
                                  || `Matched ${liveCraftPreview.matched ?? 0}`
                                    + (liveCraftPreview.match_total
                                      ? ` / ${liveCraftPreview.match_total}`
                                      : "")}
                              </p>
                            ) : null}
                          </div>
                        </details>
                      </div>
                      <div className="wizard-actions">
                        <button
                          type="button"
                          className="primary"
                          data-testid="live-channels-craft-publish"
                          disabled={liveBusy === "craft"}
                          onClick={async () => {
                            if (
                              !window.confirm(
                                "Publish this station to Tunarr? New channel numbers are remapped into Plex Live TV after publish.",
                              )
                            ) {
                              return;
                            }
                            const number = Number(liveCraft.number);
                            const craftFilters = buildCraftFiltersPayload(liveCraft);
                            await runPublishJob(
                              () =>
                                publishLiveChannelsChannel({
                                  name: liveCraft.name,
                                  number: Number.isFinite(number) ? number : 0,
                                  source: liveCraft.source,
                                  programming_mode: liveCraft.programming_mode,
                                  media_scope: liveCraft.media_scope || "both",
                                  motif: liveCraft.motif,
                                  cluster_tag: liveCraft.cluster_tag,
                                  collection_id: liveCraft.collection_id,
                                  collection_title: liveCraft.collection_title,
                                  youth_safe:
                                    liveCraft.youth_safe || liveCraft.source === "youth",
                                  craft_filters: craftFilters,
                                  fill_programming: true,
                                }),
                              {
                                busyKey: "craft",
                                block: "craft",
                                successFallback: "Station published.",
                              },
                            );
                            try {
                              const opts = await getLiveChannelsCraftOptions();
                              setLiveCraftOptions(opts);
                              setLiveCraft((prev) => ({
                                ...prev,
                                name: "",
                                number: String(opts.next_channel_number || 100),
                              }));
                            } catch {
                              /* ignore */
                            }
                          }}
                        >
                          {liveBusy === "craft" ? "Publishing…" : "Publish station"}
                        </button>
                      </div>
                      {renderPublishProgress("craft")}
                      {renderLiveBlockAlert("craft")}
                    </div>
                    ) : null}

                    {createStationMode === "collection" ? (
                    <div
                      className="live-channels-craft-block"
                      data-testid="live-channels-from-collection"
                    >
                      <p className="wizard-note">
                        One-tap station from a Plex collection or published Projectionist
                        list. Sequential keeps collection order; Shuffle randomizes the
                        full resolved pool.
                      </p>
                      {liveCraftOptions?.collections_error ? (
                        <p
                          className="wizard-note"
                          data-testid="live-channels-collections-error"
                        >
                          {liveCraftOptions.collections_error}
                        </p>
                      ) : null}
                      {!(liveCraftOptions?.collections || []).length ? (
                        <p
                          className="wizard-note"
                          data-testid="live-channels-collections-empty"
                        >
                          {liveCraftOptions?.collections_empty_hint ||
                            "No collections available yet. Create one in Plex, or publish a list under Collections."}
                        </p>
                      ) : null}
                      <label className="field">
                        <span>Play order</span>
                        <select
                          data-testid="live-channels-collection-mode"
                          value={liveCraft.programming_mode || "sequential"}
                          onChange={(event) =>
                            setLiveCraft((prev) => ({
                              ...prev,
                              programming_mode: event.target.value,
                            }))
                          }
                        >
                          <option value="sequential">Sequential — collection order</option>
                          <option value="shuffle">Shuffle — full pool of this collection</option>
                        </select>
                      </label>
                      <div className="wizard-actions">
                        <button
                          type="button"
                          className="ghost"
                          data-testid="live-channels-publish-collection"
                          disabled={
                            liveBusy === "collection" ||
                            !(liveCraftOptions?.collections || []).length
                          }
                          onClick={async () => {
                            const first = (liveCraftOptions?.collections || [])[0];
                            if (!first) return;
                            const picked =
                              (liveCraft.collection_id &&
                                (liveCraftOptions?.collections || []).find(
                                  (row) => row.id === liveCraft.collection_id,
                                )) ||
                              first;
                            const mode =
                              liveCraft.programming_mode === "shuffle"
                                ? "shuffle"
                                : "sequential";
                            const modeLabel =
                              mode === "shuffle" ? "Shuffle" : "Sequential";
                            if (
                              !window.confirm(
                                `Publish “${picked.title}” as a ${modeLabel} Live Channel station?`,
                              )
                            ) {
                              return;
                            }
                            await runPublishJob(
                              () =>
                                publishLiveChannelsFromCollection({
                                  collection_id: picked.id,
                                  collection_title: picked.title,
                                  name: picked.title,
                                  programming_mode: mode,
                                  media_scope: liveCraft.media_scope || "both",
                                  craft_filters: buildCraftFiltersPayload(liveCraft),
                                }),
                              {
                                busyKey: "collection",
                                block: "collection",
                                successFallback: `Published “${picked.title}”.`,
                              },
                            );
                          }}
                        >
                          {liveBusy === "collection"
                            ? "Publishing…"
                            : (liveCraftOptions?.collections || []).length
                              ? `Publish “${
                                  (
                                    (liveCraft.collection_id &&
                                      (liveCraftOptions?.collections || []).find(
                                        (row) => row.id === liveCraft.collection_id,
                                      )) ||
                                    liveCraftOptions.collections[0]
                                  )?.title
                                }”`
                              : "No collections available"}
                        </button>
                      </div>
                      {renderPublishProgress("collection")}
                      {renderLiveBlockAlert("collection")}
                    </div>
                    ) : null}

                    {createStationMode === "starters" ? (
                    <div className="live-channels-craft-block" data-testid="live-channels-starter-pack">
                      <p className="wizard-note">
                        Propose 2–4 library-aware stations, then publish the ones you want.
                        Re-running is additive — existing channel numbers keep their stations.
                      </p>
                    {liveStarters?.proposals?.length ? (
                      <>
                        <ul className="wizard-note" data-testid="live-channels-starter-list">
                          {liveStarters.proposals.map((proposal) => {
                            const key = `${proposal.number}:${proposal.name}`;
                            return (
                              <li key={key}>
                                <label className="config-toggle">
                                  <input
                                    type="checkbox"
                                    checked={Boolean(selectedStarters[key])}
                                    onChange={(event) =>
                                      setSelectedStarters((prev) => ({
                                        ...prev,
                                        [key]: event.target.checked,
                                      }))
                                    }
                                  />
                                  <span>
                                    {proposal.number} · {proposal.name}
                                    {proposal.summary ? ` — ${proposal.summary}` : ""}
                                  </span>
                                </label>
                              </li>
                            );
                          })}
                        </ul>
                        <div className="wizard-actions">
                          <button
                            type="button"
                            data-testid="live-channels-publish-starters"
                            disabled={liveBusy === "publish"}
                            onClick={async () => {
                              if (
                                !window.confirm(
                                  "Create / publish the selected starter stations? Existing channel numbers keep their stations; empty lineups are filled from your Plex library.",
                                )
                              ) {
                                return;
                              }
                              setLiveBusy("publish");
                              try {
                                const recipes = (liveStarters.proposals || []).filter((proposal) => {
                                  const key = `${proposal.number}:${proposal.name}`;
                                  return selectedStarters[key];
                                });
                                const result = await publishLiveChannelsStarters({
                                  recipes,
                                  fill_programming: true,
                                });
                                const feedback = formatPublishFeedback(result);
                                setActionFeedback("live-channels",
                                  feedback.type,
                                  feedback.summary, { block: "publish",  details: feedback.details },
                                );
                                const status = await getLiveChannelsStatus();
                                setLiveChannelsStatus(status);
                              } catch (error) {
                                setActionFeedback("live-channels", "error", error.message, { block: "publish" });
                              } finally {
                                setLiveBusy(null);
                              }
                            }}
                          >
                            {liveBusy === "publish" ? "Publishing…" : "Publish selected starters"}
                          </button>
                        </div>
                        {renderLiveBlockAlert("publish")}
                      </>
                    ) : (
                      <p className="wizard-note">
                        Click Propose starters above for 2–4 stations from your library signals.
                      </p>
                    )}
                    </div>
                    ) : null}
                  </div>

                  <div className="service-card" data-testid="live-channels-manage">
                    <div className="service-card-header">
                      <div className="service-card-title">
                        <h3>Your stations</h3>
                      </div>
                      <div className="service-card-actions">
                        <button
                          type="button"
                          className="ghost"
                          data-testid="live-channels-repair-continuity"
                          disabled={liveBusy === "continuity-repair"}
                          onClick={async () => {
                            if (
                              !window.confirm(
                                "Repair continuity on all stations? This remounts filler paths if needed, attaches the shared filler list, pads commercial-cut gaps (up to 15 minutes), and warms streams. Active Live TV sessions may briefly drop while the TV engine restarts.",
                              )
                            ) {
                              return;
                            }
                            try {
                              await runContinuityJob(
                                {
                                  rescan: true,
                                  repair: true,
                                  refill_lineups: true,
                                },
                                { successFallback: "Continuity repair finished.", block: "stations" },
                              );
                            } catch {
                              /* feedback already set */
                            }
                          }}
                        >
                          {liveBusy === "continuity-repair"
                            ? "Repairing…"
                            : "Repair continuity"}
                        </button>
                        <button
                          type="button"
                          className="ghost"
                          data-testid="live-channels-refresh-manage"
                          disabled={liveBusy === "manage-refresh"}
                          onClick={async () => {
                            setLiveBusy("manage-refresh");
                            try {
                              setLiveChannelsStatus(await getLiveChannelsStatus());
                            } catch (error) {
                              setActionFeedback("live-channels", "error", error.message, { block: "stations" });
                            } finally {
                              setLiveBusy(null);
                            }
                          }}
                        >
                          Refresh
                        </button>
                      </div>
                    </div>
                    <p className="wizard-note">
                      Lineup depth, media scope, and continuity show here. Refill re-pulls titles;
                      Settings sets TV / Movies / Both; Repair continuity fixes jump-start stations
                      in place.
                    </p>
                    {liveLaunched && effectiveLiveTab === "stations"
                      ? renderContinuityProgress()
                      : null}
                    {renderLiveBlockAlert("stations")}
                    {(liveChannelsStatus?.continuity?.checks || []).length ? (
                      <ul
                        className="live-channels-check-list"
                        data-testid="live-channels-continuity-checks-stations"
                      >
                        {liveChannelsStatus.continuity.checks.map((check) => (
                          <LiveStatusCheck
                            key={check.id}
                            ok={check.ok}
                            soft={check.soft}
                            testId={`live-channels-continuity-${check.id}`}
                          >
                            {check.label}: {check.message}
                          </LiveStatusCheck>
                        ))}
                      </ul>
                    ) : null}
                    {(liveChannelsStatus?.guide_index?.lineup?.channels ||
                      liveChannelsStatus?.channels ||
                      []).length ? (
                      <ul className="wizard-note live-channels-manage-list" data-testid="live-channels-manage-list">
                        {(
                          liveChannelsStatus?.guide_index?.lineup?.channels ||
                          liveChannelsStatus?.channels ||
                          []
                        ).map((ch) => {
                          const id = ch.id || ch.channel_id;
                          const programs =
                            ch.total_programs != null ? Number(ch.total_programs) : null;
                          const statusRow = (liveChannelsStatus?.channels || []).find(
                            (row) => (row.id || row.channel_id) === id,
                          );
                          const mediaScope =
                            statusRow?.media_scope || ch.media_scope || "both";
                          const hasContinuity = Boolean(
                            statusRow?.has_continuity ?? ch.has_continuity,
                          );
                          return (
                            <li key={id || `${ch.number}:${ch.name}`}>
                              <div className="live-channels-manage-row">
                                <span>
                                  {ch.number != null ? `${ch.number} · ` : ""}
                                  {ch.name || "Station"}
                                  {programs != null
                                    ? programs > 0
                                      ? ` — ${programs} titles in lineup`
                                      : " — empty lineup (refill after scan)"
                                    : ""}
                                  {` · ${mediaScope === "tv" ? "TV" : mediaScope === "movies" ? "Movies" : "Both"}`}
                                  {hasContinuity ? " · continuity ✓" : " · continuity needed"}
                                </span>
                                <span className="live-channels-manage-actions">
                                  <button
                                    type="button"
                                    className="ghost"
                                    data-testid={`live-channels-settings-${id}`}
                                    disabled={!id}
                                    onClick={() => {
                                      if (stationSettingsOpen === id) {
                                        setStationSettingsOpen(null);
                                        setStationCraftDraft(null);
                                        setStationSettingsSavedId(null);
                                        return;
                                      }
                                      const row =
                                        (liveChannelsStatus?.channels || []).find(
                                          (c) => (c.id || c.channel_id) === id,
                                        ) || ch;
                                      setStationCraftDraft(craftDraftFromStation(row));
                                      setStationSettingsSavedId(null);
                                      setStationSettingsOpen(id);
                                    }}
                                  >
                                    Settings
                                  </button>
                                  <button
                                    type="button"
                                    className="ghost"
                                    data-testid={`live-channels-refill-${id}`}
                                    disabled={!id || liveBusy === `refill-${id}`}
                                    onClick={async () => {
                                      if (!id) return;
                                      if (!window.confirm(`Refill lineup for ${ch.name}?`)) return;
                                      setLiveBusy(`refill-${id}`);
                                      try {
                                        // Omit partial recipe overlays — backend
                                        // refills from station_meta (decade/genre).
                                        const result = await refillLiveChannelsChannel(id);
                                        setActionFeedback("live-channels",
                                          result.ok ? "success" : "error",
                                          result.note || "Refill finished.",
                                          { block: "stations" },
                                        );
                                        setLiveChannelsStatus(await getLiveChannelsStatus());
                                      } catch (error) {
                                        setActionFeedback("live-channels", "error", error.message, { block: "stations" });
                                      } finally {
                                        setLiveBusy(null);
                                      }
                                    }}
                                  >
                                    {liveBusy === `refill-${id}` ? "Refilling…" : "Refill"}
                                  </button>
                                  <button
                                    type="button"
                                    className="ghost"
                                    data-testid={`live-channels-delete-${id}`}
                                    disabled={!id || liveBusy === `delete-${id}`}
                                    onClick={async () => {
                                      if (!id) return;
                                      if (
                                        !window.confirm(
                                          `Delete station ${ch.number != null ? ch.number + " · " : ""}${ch.name}? This cannot be undone.`,
                                        )
                                      ) {
                                        return;
                                      }
                                      setLiveBusy(`delete-${id}`);
                                      try {
                                        await deleteLiveChannelsChannel(id);
                                        setActionFeedback("live-channels",
                                          "success",
                                          `Deleted ${ch.name}.`,
                                          { block: "stations" },
                                        );
                                        setLiveChannelsStatus(await getLiveChannelsStatus());
                                        setLiveCraftOptions(await getLiveChannelsCraftOptions());
                                      } catch (error) {
                                        setActionFeedback("live-channels", "error", error.message, { block: "stations" });
                                      } finally {
                                        setLiveBusy(null);
                                      }
                                    }}
                                  >
                                    {liveBusy === `delete-${id}` ? "Deleting…" : "Delete"}
                                  </button>
                                </span>
                              </div>
                              {stationSettingsOpen === id && stationCraftDraft ? (
                                <div
                                  className="live-channels-station-settings"
                                  data-testid={`live-channels-station-settings-${id}`}
                                >
                                  <p className="wizard-note" data-testid={`live-channels-station-name-${id}`}>
                                    <strong>{ch.name || "Station"}</strong>
                                    {stationCraftDraft.source
                                      ? ` · ${stationCraftDraft.source === "collection"
                                        ? "Collection"
                                        : stationCraftDraft.source === "taste_cluster"
                                          ? "Taste"
                                          : stationCraftDraft.source === "youth"
                                            ? "Youth safe"
                                            : "Motif"}`
                                      : ""}
                                    {stationCraftDraft.collection_title
                                      ? ` · ${stationCraftDraft.collection_title}`
                                      : ""}
                                  </p>
                                  {stationCraftDraft.source === "motif" ||
                                  stationCraftDraft.motif ||
                                  (liveCraftOptions?.motifs || []).length ? (
                                    <label>
                                      Motif
                                      <select
                                        data-testid={`live-channels-station-motif-${id}`}
                                        value={stationCraftDraft.motif || ""}
                                        onChange={(event) =>
                                          setStationCraftDraft((prev) => ({
                                            ...prev,
                                            motif: event.target.value,
                                          }))
                                        }
                                      >
                                        <option value="">No motif</option>
                                        {(liveCraftOptions?.motifs || []).map((motif) => (
                                          <option key={motif.value} value={motif.value}>
                                            {motif.label || motif.value}
                                          </option>
                                        ))}
                                        {stationCraftDraft.motif &&
                                        !(liveCraftOptions?.motifs || []).some(
                                          (m) => m.value === stationCraftDraft.motif,
                                        ) ? (
                                          <option value={stationCraftDraft.motif}>
                                            {stationCraftDraft.motif}
                                          </option>
                                        ) : null}
                                      </select>
                                    </label>
                                  ) : null}
                                  <details
                                    className="live-channels-craft-filters"
                                    data-testid={`live-channels-station-filters-${id}`}
                                    open={Boolean(
                                      stationCraftDraft.genres?.[0] ||
                                        stationCraftDraft.decade ||
                                        stationCraftDraft.theme ||
                                        stationCraftDraft.content_rating,
                                    )}
                                  >
                                    <summary>Narrow the pool</summary>
                                    <p className="wizard-note">
                                      Additive filters (AND) saved on this station — e.g. 1970s ∩ Horror.
                                      Refill applies them to the lineup.
                                    </p>
                                    <label>
                                      Genre
                                      <select
                                        data-testid={`live-channels-station-genre-${id}`}
                                        value={stationCraftDraft.genres?.[0] || ""}
                                        onChange={(event) =>
                                          setStationCraftDraft((prev) => ({
                                            ...prev,
                                            genres: event.target.value ? [event.target.value] : [],
                                          }))
                                        }
                                      >
                                        <option value="">Any genre</option>
                                        {(liveCraftOptions?.filter_options?.genres || []).map((row) => (
                                          <option key={row.value} value={row.value}>
                                            {row.label}
                                            {row.count ? ` (${row.count})` : ""}
                                          </option>
                                        ))}
                                      </select>
                                    </label>
                                    <label>
                                      Decade
                                      <select
                                        data-testid={`live-channels-station-decade-${id}`}
                                        value={
                                          stationCraftDraft.decade === "" ||
                                          stationCraftDraft.decade == null
                                            ? ""
                                            : String(stationCraftDraft.decade)
                                        }
                                        onChange={(event) =>
                                          setStationCraftDraft((prev) => ({
                                            ...prev,
                                            decade: event.target.value,
                                          }))
                                        }
                                      >
                                        <option value="">Any decade</option>
                                        {(liveCraftOptions?.filter_options?.decades || []).map((row) => (
                                          <option key={row.value} value={String(row.value)}>
                                            {row.label}
                                            {row.count ? ` (${row.count})` : ""}
                                          </option>
                                        ))}
                                      </select>
                                    </label>
                                    <label>
                                      Theme
                                      <select
                                        data-testid={`live-channels-station-theme-${id}`}
                                        value={stationCraftDraft.theme || ""}
                                        onChange={(event) =>
                                          setStationCraftDraft((prev) => ({
                                            ...prev,
                                            theme: event.target.value,
                                          }))
                                        }
                                      >
                                        <option value="">Any theme</option>
                                        {(liveCraftOptions?.filter_options?.themes || []).map((row) => (
                                          <option key={row.value} value={row.value}>
                                            {row.label}
                                            {row.count ? ` (${row.count})` : ""}
                                          </option>
                                        ))}
                                      </select>
                                    </label>
                                    <label>
                                      Rating
                                      <select
                                        data-testid={`live-channels-station-rating-${id}`}
                                        value={stationCraftDraft.content_rating || ""}
                                        onChange={(event) =>
                                          setStationCraftDraft((prev) => ({
                                            ...prev,
                                            content_rating: event.target.value,
                                          }))
                                        }
                                      >
                                        <option value="">Any rating</option>
                                        {(liveCraftOptions?.filter_options?.content_ratings || []).map(
                                          (row) => (
                                            <option key={row.value} value={row.value}>
                                              {row.label}
                                              {row.count ? ` (${row.count})` : ""}
                                            </option>
                                          ),
                                        )}
                                      </select>
                                    </label>
                                  </details>
                                  <label>
                                    Media scope
                                    <select
                                      data-testid={`live-channels-station-scope-${id}`}
                                      value={stationCraftDraft.media_scope || "both"}
                                      onChange={(event) =>
                                        setStationCraftDraft((prev) => ({
                                          ...prev,
                                          media_scope: event.target.value,
                                        }))
                                      }
                                    >
                                      <option value="tv">TV</option>
                                      <option value="movies">Movies</option>
                                      <option value="both">Both</option>
                                    </select>
                                  </label>
                                  <label className="live-channels-checkbox">
                                    <input
                                      type="checkbox"
                                      data-testid={`live-channels-station-captions-${id}`}
                                      checked={Boolean(stationCraftDraft.subtitles_enabled)}
                                      onChange={(event) =>
                                        setStationCraftDraft((prev) => ({
                                          ...prev,
                                          subtitles_enabled: event.target.checked,
                                        }))
                                      }
                                    />
                                    Show captions when the station has them
                                  </label>
                                  <div className="wizard-actions">
                                    <button
                                      type="button"
                                      data-testid={`live-channels-station-save-${id}`}
                                      disabled={!id || liveBusy === `settings-${id}`}
                                      onClick={async () => {
                                        if (!id || !stationCraftDraft) return;
                                        setLiveBusy(`settings-${id}`);
                                        try {
                                          const result = await patchLiveChannelsStationSettings(id, {
                                            media_scope: stationCraftDraft.media_scope || "both",
                                            subtitles_enabled: Boolean(
                                              stationCraftDraft.subtitles_enabled,
                                            ),
                                            motif: stationCraftDraft.motif || "",
                                            cluster_tag: stationCraftDraft.cluster_tag || "",
                                            craft_filters: buildCraftFiltersPayload(stationCraftDraft),
                                          });
                                          setStationSettingsSavedId(id);
                                          setActionFeedback(
                                            "live-channels",
                                            "success",
                                            result.message ||
                                              "Station craft saved. Refill to apply the lineup.",
                                            { block: "stations" },
                                          );
                                          setLiveChannelsStatus(await getLiveChannelsStatus());
                                        } catch (error) {
                                          setActionFeedback("live-channels", "error", error.message, {
                                            block: "stations",
                                          });
                                        } finally {
                                          setLiveBusy(null);
                                        }
                                      }}
                                    >
                                      {liveBusy === `settings-${id}` ? "Saving…" : "Save craft"}
                                    </button>
                                    {stationSettingsSavedId === id ? (
                                      <button
                                        type="button"
                                        className="ghost"
                                        data-testid={`live-channels-station-refill-cta-${id}`}
                                        disabled={!id || liveBusy === `refill-${id}`}
                                        onClick={async () => {
                                          if (!id) return;
                                          if (!window.confirm(`Refill lineup for ${ch.name}?`)) return;
                                          setLiveBusy(`refill-${id}`);
                                          try {
                                            const result = await refillLiveChannelsChannel(id);
                                            setStationSettingsSavedId(null);
                                            setActionFeedback(
                                              "live-channels",
                                              result.ok ? "success" : "error",
                                              result.note || "Refill finished.",
                                              { block: "stations" },
                                            );
                                            setLiveChannelsStatus(await getLiveChannelsStatus());
                                          } catch (error) {
                                            setActionFeedback("live-channels", "error", error.message, {
                                              block: "stations",
                                            });
                                          } finally {
                                            setLiveBusy(null);
                                          }
                                        }}
                                      >
                                        {liveBusy === `refill-${id}`
                                          ? "Refilling…"
                                          : "Refill to apply"}
                                      </button>
                                    ) : null}
                                  </div>
                                  <p className="wizard-note">
                                    Save updates the station recipe only. Refill rebuilds the lineup
                                    from those filters — empty when nothing matches, never the whole
                                    library. Captions still depend on the Live encode or a Plex-backed
                                    track for the title on air.
                                  </p>
                                </div>
                              ) : null}
                            </li>
                          );
                        })}
                      </ul>
                    ) : (
                      <p className="wizard-note" data-testid="live-channels-manage-empty">
                        No stations yet — craft one above or publish a starter pack.
                      </p>
                    )}
                  </div>

                  </>
                  ) : null}

                  {!liveLaunched || effectiveLiveTab === "setup" ? (
                  <>
                  <div
                    className={`service-card${
                      liveAttach?.discovery?.ok ||
                      liveChannelsStatus?.guide_index?.last_attach?.ok
                        ? " service-ok"
                        : ""
                    }`}
                    data-testid="live-channels-plex-attach"
                  >
                    <div className="service-card-header">
                      <div className="service-card-title">
                        {!liveLaunched ? (
                          <p className="live-channels-step-label">
                            Step {setupSteps.plex}
                          </p>
                        ) : null}
                        <h3>Add to Plex</h3>
                        <LiveReadyBadge
                          ready={Boolean(
                            liveAttach?.discovery?.ok ||
                              liveChannelsStatus?.guide_index?.last_attach?.ok,
                          )}
                          label="Attached"
                          testId="live-channels-attach-ready"
                        />
                      </div>
                      <div className="service-card-actions">
                        <button
                          type="button"
                          className="ghost"
                          data-testid="live-channels-load-attach"
                          disabled={liveBusy === "attach" || liveBusy === "attach-guide"}
                          onClick={async () => {
                            setLiveBusy("attach");
                            try {
                              setLiveAttach(await getLiveChannelsPlexAttach());
                            } catch (error) {
                              setActionFeedback("live-channels", "error", error.message, { block: "connection" });
                            } finally {
                              setLiveBusy(null);
                            }
                          }}
                        >
                          {liveBusy === "attach" ? "Loading…" : "Show Plex steps"}
                        </button>
                        <button
                          type="button"
                          className="primary"
                          data-testid="live-channels-attach-guide"
                          disabled={
                            liveBusy === "attach" ||
                            liveBusy === "attach-guide" ||
                            liveBusy === "plex-repair" ||
                            Boolean(liveAttach?.needs_lan_url)
                          }
                          onClick={async () => {
                            setLiveBusy("attach-guide");
                            try {
                              if (!liveAttach) {
                                setLiveAttach(await getLiveChannelsPlexAttach());
                              }
                              const result = await postLiveChannelsPlexAttachGuide();
                              const mappedNote =
                                result.expected != null
                                  ? ` Mapped ${result.mapped ?? 0}/${result.expected}.`
                                  : "";
                              setActionFeedback(
                                "live-channels",
                                "success",
                                `${result.message || "Tunarr XMLTV guide attached in Plex (OTA left alone)."}${mappedNote}`,
                                { block: "attach" },
                              );
                              try {
                                setLiveChannelsStatus(await getLiveChannelsStatus());
                              } catch {
                                /* status refresh best-effort */
                              }
                            } catch (error) {
                              setActionFeedback("live-channels", "error", error.message, { block: "attach" });
                            } finally {
                              setLiveBusy(null);
                            }
                          }}
                        >
                          {liveBusy === "attach-guide"
                            ? "Attaching guide…"
                            : "Attach Tunarr guide in Plex"}
                        </button>
                        <button
                          type="button"
                          className="ghost"
                          data-testid="live-channels-plex-repair"
                          disabled={
                            liveBusy === "attach" ||
                            liveBusy === "attach-guide" ||
                            liveBusy === "plex-repair" ||
                            Boolean(liveAttach?.needs_lan_url)
                          }
                          onClick={async () => {
                            if (
                              !window.confirm(
                                "Repair Plex tuner/guide? This recreates the Tunarr device and XMLTV DVR in Plex (OTA stays), rescans all channels, and remaps the guide. Active Live TV sessions on Tunarr channels may drop briefly.",
                              )
                            ) {
                              return;
                            }
                            setLiveBusy("plex-repair");
                            try {
                              const result = await postLiveChannelsPlexRepair();
                              const mappedNote =
                                result.expected != null
                                  ? ` Mapped ${result.mapped ?? 0}/${result.expected}.`
                                  : "";
                              setActionFeedback(
                                "live-channels",
                                "success",
                                `${result.message || "Plex Tunarr tuner/guide repaired."}${mappedNote}`,
                                { block: "attach" },
                              );
                              try {
                                setLiveChannelsStatus(await getLiveChannelsStatus());
                              } catch {
                                /* status refresh best-effort */
                              }
                            } catch (error) {
                              setActionFeedback("live-channels", "error", error.message, { block: "attach" });
                            } finally {
                              setLiveBusy(null);
                            }
                          }}
                        >
                          {liveBusy === "plex-repair" ? "Repairing…" : "Repair Plex tuner/guide"}
                        </button>
                      </div>
                    </div>
                    {renderLiveBlockAlert("attach")}
                    {liveAttach ? (
                      <>
                        <p
                          className="wizard-note live-channels-coexist-note"
                          data-testid="live-channels-coexist-note"
                        >
                          {liveAttach.existing_livetv?.message ||
                            liveAttach.coexistence?.note ||
                            "Plex supports multiple tuners — add Tunarr alongside any OTA setup; do not remove existing Live TV."}
                        </p>
                        {liveAttach.coexistence?.guide_warning ? (
                          <p
                            className="wizard-note live-channels-guide-warning"
                            data-testid="live-channels-guide-warning"
                          >
                            {liveAttach.coexistence.guide_warning}
                          </p>
                        ) : null}
                        <ol className="wizard-note" data-testid="live-channels-attach-steps">
                          {(liveAttach.steps || []).map((step) => (
                            <li key={step.title}>
                              <strong>{step.title}</strong> — {step.body}
                            </li>
                          ))}
                        </ol>
                        {liveAttach.needs_lan_url || !liveAttach.tuner_url ? (
                          <p className="wizard-note" data-testid="live-channels-attach-warning">
                            {liveAttach.warning ||
                              "Set a LAN Tunarr address before pasting into Plex. Projectionist uses host.docker.internal only for its own connection to Tunarr — Plex cannot resolve that name."}
                          </p>
                        ) : (
                          <div className="service-fields">
                            <label>
                              <span>
                                Network address (host:port) — only if Plex did not discover Tunarr
                              </span>
                              <input
                                type="text"
                                readOnly
                                data-testid="live-channels-manual-address"
                                value={liveAttach.manual_address || ""}
                                onFocus={(event) => event.target.select()}
                              />
                            </label>
                            <label>
                              <span>Tuner base URL (reference)</span>
                              <input
                                type="text"
                                readOnly
                                data-testid="live-channels-tuner-url"
                                value={liveAttach.tuner_url || ""}
                                onFocus={(event) => event.target.select()}
                              />
                            </label>
                            <label>
                              <span>
                                Tunarr XMLTV URL (used by Attach Tunarr guide in Plex — not a
                                Plex UI paste field)
                              </span>
                              <input
                                type="text"
                                readOnly
                                data-testid="live-channels-guide-url"
                                value={liveAttach.guide_url || ""}
                                onFocus={(event) => event.target.select()}
                              />
                            </label>
                          </div>
                        )}
                        <ul className="live-channels-check-list">
                          <LiveStatusCheck ok={Boolean(liveAttach.discovery?.ok)} soft={!liveAttach.discovery?.ok}>
                            {liveAttach.discovery?.message || "Discovery not checked."}
                          </LiveStatusCheck>
                          {liveChannelsStatus?.guide_index?.last_attach?.ok ? (
                            <LiveStatusCheck ok>
                              Guide attached
                              {liveChannelsStatus.guide_index.last_attach.dvr_key
                                ? ` · DVR ${liveChannelsStatus.guide_index.last_attach.dvr_key}`
                                : ""}
                            </LiveStatusCheck>
                          ) : null}
                        </ul>
                      </>
                    ) : (
                      <p className="wizard-note">
                        On Tuner Setup, select discovered Tunarr and enter any ZIP so Next unlocks.
                        EPG Location is commercial lineups only. Then click Attach Tunarr guide in
                        Plex — Projectionist wires Tunarr XMLTV via the PMS API (OTA stays on its
                        commercial guide). Leave any OTA device in place.
                      </p>
                    )}
                  </div>

                  <details
                    className="live-channels-logs"
                    data-testid="live-channels-tunarr-logs"
                    open={tunarrLogsOpen}
                    onToggle={(event) => {
                      const open = event.currentTarget.open;
                      setTunarrLogsOpen(open);
                      if (open && !tunarrLogs && !tunarrLogsBusy) {
                        refreshTunarrLogs();
                      }
                    }}
                  >
                    <summary data-testid="live-channels-tunarr-logs-summary">
                      TV engine logs
                    </summary>
                    <div className="live-channels-logs-toolbar">
                      <p className="wizard-note">
                        Recent TV engine output (last 200 lines). Useful when Publish starters or Start
                        engine fails.
                      </p>
                      <button
                        type="button"
                        className="ghost"
                        data-testid="live-channels-tunarr-logs-refresh"
                        disabled={tunarrLogsBusy}
                        onClick={() => refreshTunarrLogs()}
                      >
                        {tunarrLogsBusy ? "Loading…" : "Refresh"}
                      </button>
                    </div>
                    {tunarrLogsBusy && !tunarrLogs ? (
                      <p className="wizard-note" data-testid="live-channels-tunarr-logs-loading">
                        Loading logs…
                      </p>
                    ) : null}
                    {tunarrLogs && !tunarrLogs.ok ? (
                      <InlineAlert
                        type="error"
                        message={tunarrLogs.message || "Logs unavailable."}
                        testId="live-channels-tunarr-logs-error"
                      />
                    ) : null}
                    {tunarrLogs?.ok ? (
                      <>
                        <p className="wizard-note" data-testid="live-channels-tunarr-logs-source">
                          Source: {tunarrLogs.source === "docker" ? "Docker container" : "Tunarr API"}
                          {tunarrLogs.message ? ` — ${tunarrLogs.message}` : ""}
                        </p>
                        <pre
                          className="live-channels-logs-scroller"
                          data-testid="live-channels-tunarr-logs-text"
                        >
                          {tunarrLogs.text || "(empty)"}
                        </pre>
                      </>
                    ) : null}
                  </details>
                  </>
                  ) : null}
                </div>
              </>
            )}

            {/* Live Channels feedback is inline per card via liveBlockFeedback. */}
          </section>
  );
}
