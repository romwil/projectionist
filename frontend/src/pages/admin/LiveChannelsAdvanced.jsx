import MuzakFolderPanel from "../../components/admin/MuzakFolderPanel";
import InlineAlert from "../../components/InlineAlert";
import SectionHelp from "../../components/SectionHelp";
import {
  deleteLiveChannelsChannel,
  getLiveChannelsCraftOptions,
  getLiveChannelsStatus,
  patchLiveChannelsEngineSettings,
  patchLiveChannelsStationSettings,
  postLiveChannelsPlexAttachGuide,
  postLiveChannelsPlexRepair,
  postLiveChannelsPreflight,
} from "../../api/client";
import { buildCraftFiltersPayload } from "../../lib/liveChannelsCraft.js";
import QueuePadControl from "../../components/live/QueuePadControl";
import { ownerLiveText } from "../../lib/liveChannelsOwnerCopy.js";
import { queuePadPayload } from "../../lib/liveQueuePad.js";
import { liveSetupStepNumbers } from "../../lib/liveChannelsCopy.js";
import { isLiveMutatingDisabled, plexRebuildConfirmMessage } from "../../lib/liveChannelsJob.js";
import { LiveReadyBadge, LiveStatusCheck } from "./LiveChannelsParts.jsx";

/**
 * Behind-the-scenes panels for Live: broadcast connection, ready check, breaks,
 * Plex hookup, logs (panel="setup") and per-channel craft settings (panel="station").
 * The owner-facing flow lives in LiveChannelsStudio; this stays reachable but tucked away.
 */
export default function LiveChannelsAdvanced({
  panel = "setup",
  settings,
  persistSettings,
  updateTunarrSettings,
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
  fillerPathDraft,
  setFillerPathDraft,
  padFlexDraft,
  setPadFlexDraft,
  exclusionNameDraft,
  setExclusionNameDraft,
  liveAttach,
  liveBusy,
  setLiveBusy,
  liveEngineProgress,
  liveEngineError,
  stationSettingsOpen,
  setStationSettingsOpen,
  stationCraftDraft,
  setStationCraftDraft,
  refillStation,
  fillerBinds,
  renderLiveBlockAlert,
  renderContinuityProgress,
  startBroadcastEngine,
  runContinuityJob,
  tunarrLogsOpen,
  setTunarrLogsOpen,
  tunarrLogs,
  tunarrLogsBusy,
  refreshTunarrLogs,
}) {
  const liveLaunched = true;
  const effectiveLiveTab = "setup";
  const setupSteps = liveSetupStepNumbers({
    dockerOrchestration: Boolean(settings?.tunarr?.docker_orchestration),
  });
  const liveJob = liveChannelsStatus?.job;
  const liveLocked = isLiveMutatingDisabled(liveJob, liveBusy);
  const mappingOk = Boolean(liveChannelsStatus?.guide_index?.plex_livetv?.mapping_ok);
  const settingsStationId = stationSettingsOpen;
  const settingsStation =
    (liveChannelsStatus?.channels || []).find(
      (c) => (c.id || c.channel_id) === settingsStationId,
    ) || null;

  return (
    <div className="live-studio-advanced-body" data-testid="live-channels-advanced-panels" data-panel={panel}>
      {panel === "setup" ? (
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
                          Broadcast connection{" "}
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
                          label="Broadcast ready"
                          testId="live-channels-engine-ready-badge"
                        />
                      </div>
                      <div className="service-card-actions">
                        <button
                          type="button"
                          className="primary"
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
                    </div>
                    <p className="wizard-note">
                      Where Projectionist reaches your broadcast. Most owners leave this as-is once
                      Projectionist has started it.
                    </p>
                    <div className="service-fields">
                      <label>
                        <span>Broadcast address</span>
                        <input
                          type="text"
                          data-testid="tunarr-url"
                          value={settings?.tunarr?.url ?? ""}
                          placeholder="http://your-server:8000"
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
                          Let Projectionist start and stop the broadcast for you (needs container access on the host).
                        </span>
                      </label>
                      <p className="wizard-note">
                        Host setting: <code>PROJECTIONIST_DOCKER_ORCHESTRATION=1</code>
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
                      <div className="service-card-actions">
                        <button
                          type="button"
                          className="primary"
                          data-testid="live-channels-run-preflight"
                          disabled={liveLocked || liveBusy === "preflight"}
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
                        Looks for container access, free disk, a reachable Plex, your broadcast address, and the Plex Pass
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
                          <h3>Start the broadcast</h3>
                          <LiveReadyBadge
                            ready={Boolean(liveEngineProgress?.ready)}
                            label="Broadcast ready"
                            testId="live-channels-engine-ready"
                          />
                        </div>
                        <div className="service-card-actions">
                          <button
                            type="button"
                            className="primary"
                            data-testid="live-channels-ensure-running"
                            disabled={liveLocked || liveBusy === "lifecycle"}
                            onClick={() => {
                              startBroadcastEngine().catch(() => {});
                            }}
                          >
                            {liveBusy === "lifecycle"
                              ? "Starting…"
                              : liveEngineProgress?.ready
                                ? "Restart broadcast"
                                : "Start broadcast"}
                          </button>
                        </div>
                      </div>
                      <p className="wizard-note">
                        Downloads and starts the broadcast with a config volume under your data
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
                              <LiveStatusCheck ok>Broadcast ready</LiveStatusCheck>
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
                                  (liveBusy === "lifecycle" ? "Starting the broadcast…" : "Working…")}
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
                                aria-label="Broadcast start progress"
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
                                        ? "Waiting for the broadcast"
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
                      <div className="service-card-actions">
                        <button
                          type="button"
                          className="primary"
                          data-testid="live-channels-rescan-filler"
                          disabled={liveLocked || liveBusy === "continuity-repair"}
                          onClick={async () => {
                          if (
                            !window.confirm(
                              "Rescan filler and repair continuity? This remounts filler paths if needed, force-scans the local filler library, attaches the shared list, and warms streams. Active Live TV sessions may briefly drop while the broadcast restarts.",
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
                    </div>
                    <p className="wizard-note">
                      Commercial-cut shows often need a few minutes of bumpers between episodes.
                      Add host folders of trailers / shorts — Projectionist mounts each path into the
                      broadcast and builds one randomized break list for every channel. Gap fill
                      caps pads toward :00/:30 (0 = back-to-back). Exclusion skips a named Plex
                      collection (default NoLive) during channel fill.
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
                      <div className="live-channels-filler-add">
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
                        className="ghost"
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
                                "Filler path saved. Restart the broadcast engine if it is already running so the broadcast picks up the new mount, then Rescan filler.",
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
                        New channels: show captions when available
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
                        disabled={liveLocked || liveBusy === "engine-settings"}
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

                  <MuzakFolderPanel
                    currentPath={settings?.tunarr?.muzak_folder || ""}
                    onSaved={(path) => updateTunarrSettings({ muzak_folder: path })}
                  />

                  <div
                    className={`service-card${
                      mappingOk ? " service-ok" : ""
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
                        <h3>Plex Live TV</h3>
                        <LiveReadyBadge
                          ready={mappingOk}
                          label="Attached"
                          testId="live-channels-attach-ready"
                        />
                      </div>
                      <div className="service-card-actions">
                        <button
                          type="button"
                          className="primary"
                          data-testid="live-channels-attach-guide"
                          disabled={liveLocked || Boolean(liveAttach?.needs_lan_url)}
                          onClick={async () => {
                            setLiveBusy("attach-guide");
                            try {
                              const result = await postLiveChannelsPlexAttachGuide();
                              const mappedNote =
                                result.expected != null
                                  ? ` Mapped ${result.mapped ?? 0}/${result.expected}.`
                                  : "";
                              setActionFeedback(
                                "live-channels",
                                "success",
                                `${result.message || "Plex map refreshed."}${mappedNote}`,
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
                            ? "Refreshing…"
                            : "Refresh Plex map"}
                        </button>
                        <button
                          type="button"
                          className="ghost"
                          data-testid="live-channels-plex-repair"
                          disabled={liveLocked || Boolean(liveAttach?.needs_lan_url)}
                          onClick={async () => {
                            if (!window.confirm(plexRebuildConfirmMessage())) {
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
                                `${result.message || "Plex tuner rebuilt."}${mappedNote}`,
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
                          {liveBusy === "plex-repair" ? "Rebuilding…" : "Rebuild tuner in Plex"}
                        </button>
                      </div>
                    </div>
                    {renderLiveBlockAlert("attach")}
                    <p className="wizard-note" data-testid="live-channels-plex-writes">
                      Projectionist writes the Projectionist tuner and channel guide in Plex.
                      Refresh injects or remaps channels without deleting the DVR.
                      Rebuild is advanced — it hangs Plex Media Server briefly and drops
                      Projectionist Live TV; over-the-air stays.
                    </p>
                    {liveAttach ? (
                      <>
                        <p
                          className="wizard-note live-channels-coexist-note"
                          data-testid="live-channels-coexist-note"
                        >
                          {liveAttach.existing_livetv?.message ||
                            liveAttach.coexistence?.note ||
                            "Plex supports multiple tuners — add Projectionist alongside any OTA setup; do not remove existing Live TV."}
                        </p>
                        {liveAttach.coexistence?.guide_warning ? (
                          <p
                            className="wizard-note live-channels-guide-warning"
                            data-testid="live-channels-guide-warning"
                          >
                            {liveAttach.coexistence.guide_warning}
                          </p>
                        ) : null}
                        <details
                          className="live-channels-advanced"
                          data-testid="live-channels-plex-fallback"
                        >
                          <summary data-testid="live-channels-plex-fallback-summary">
                            Plex didn’t see the tuner
                          </summary>
                          <ol className="wizard-note" data-testid="live-channels-attach-steps">
                            {(liveAttach.steps || []).map((step) => (
                              <li key={step.title}>
                                <strong>{step.title}</strong> — {step.body}
                              </li>
                            ))}
                          </ol>
                        </details>
                        {liveAttach.needs_lan_url || !liveAttach.tuner_url ? (
                          <p className="wizard-note" data-testid="live-channels-attach-warning">
                            {liveAttach.warning ||
                              "Set a LAN broadcast address before pasting into Plex. Projectionist uses the host name only for its own connection to the broadcast — Plex cannot resolve that name."}
                          </p>
                        ) : (
                          <div className="service-fields">
                            <label>
                              <span>
                                Network address (host:port) — only if Plex did not discover the broadcast
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
                                Channel guide address (Projectionist writes this — not a Plex UI paste field)
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
                          {mappingOk ? (
                            <LiveStatusCheck ok>
                              Live Plex map ok
                              {liveChannelsStatus?.guide_index?.plex_livetv?.mapped != null
                                ? ` · ${liveChannelsStatus.guide_index.plex_livetv.mapped}/${liveChannelsStatus.guide_index.plex_livetv.expected}`
                                : ""}
                            </LiveStatusCheck>
                          ) : null}
                        </ul>
                      </>
                    ) : (
                      <p className="wizard-note">
                        Click Refresh Plex map — Projectionist writes the tuner and guide.
                        Open <strong>Plex didn’t see the tuner</strong> only if Plex never
                        discovered the broadcast. Leave any OTA device in place.
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
                      Broadcast logs
                    </summary>
                    <div className="live-channels-logs-toolbar">
                      <p className="wizard-note">
                        Recent broadcast output (last 200 lines). Useful when Create suggested channels or Start
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
                          Source: {tunarrLogs.source === "docker" ? "container" : "the broadcast API"}
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
      {panel === "station" ? (
        <>
                  {settingsStationId && stationCraftDraft ? (
                  <div className="service-card" data-testid="live-channels-station-settings-card">
                    <div className="service-card-header">
                      <div className="service-card-title">
                        <h3>
                          Channel settings
                          {settingsStation?.number != null ? ` · ${settingsStation.number}` : ""}
                          {settingsStation?.name ? ` · ${settingsStation.name}` : ""}
                        </h3>
                      </div>
                      <div className="service-card-actions">
                        <button
                          type="button"
                          className="ghost"
                          data-testid={`live-channels-delete-${settingsStationId}`}
                          disabled={liveLocked || !settingsStationId || liveBusy === `delete-${settingsStationId}`}
                          onClick={async () => {
                            if (!settingsStationId) return;
                            const label = `${settingsStation?.number != null ? `${settingsStation.number} · ` : ""}${settingsStation?.name || "station"}`;
                            if (!window.confirm(`Delete channel ${label}? This cannot be undone.`)) {
                              return;
                            }
                            setLiveBusy(`delete-${settingsStationId}`);
                            try {
                              await deleteLiveChannelsChannel(settingsStationId);
                              setActionFeedback("live-channels", "success", `Deleted ${settingsStation?.name || "station"}.`, { block: "stations" });
                              setStationSettingsOpen(null);
                              setStationCraftDraft(null);
                              setLiveChannelsStatus(await getLiveChannelsStatus());
                              setLiveCraftOptions(await getLiveChannelsCraftOptions());
                            } catch (error) {
                              setActionFeedback("live-channels", "error", error.message, { block: "stations" });
                            } finally {
                              setLiveBusy(null);
                            }
                          }}
                        >
                          {liveBusy === `delete-${settingsStationId}` ? "Deleting…" : "Delete"}
                        </button>
                        <button
                          type="button"
                          className="ghost"
                          data-testid="live-channels-settings-close"
                          onClick={() => {
                            setStationSettingsOpen(null);
                            setStationCraftDraft(null);
                          }}
                        >
                          Close
                        </button>
                      </div>
                    </div>
                    {renderLiveBlockAlert("stations")}
                    <div
                      className="live-channels-station-settings"
                      data-testid={`live-channels-station-settings-${settingsStationId}`}
                    >
                      <label>
                        Channel name
                        <input
                          type="text"
                          maxLength={48}
                          data-testid={`live-channels-station-name-${settingsStationId}`}
                          value={stationCraftDraft.name || ""}
                          placeholder={settingsStation?.name || "Station"}
                          onChange={(event) =>
                            setStationCraftDraft((prev) => ({
                              ...prev,
                              name: event.target.value,
                            }))
                          }
                        />
                      </label>
                      <p className="wizard-note" data-testid={`live-channels-station-source-${settingsStationId}`}>
                        {stationCraftDraft.source
                          ? stationCraftDraft.source === "collection"
                            ? "Collection"
                            : stationCraftDraft.source === "taste_cluster"
                              ? "Taste"
                              : stationCraftDraft.source === "youth"
                                ? "Youth safe"
                                : stationCraftDraft.source === "show"
                                  ? "TV show"
                                  : "Motif"
                          : "Custom station"}
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
                            data-testid={`live-channels-station-motif-${settingsStationId}`}
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
                        data-testid={`live-channels-station-filters-${settingsStationId}`}
                        open={Boolean(
                          stationCraftDraft.genres?.[0] ||
                            stationCraftDraft.decade ||
                            stationCraftDraft.theme ||
                            stationCraftDraft.content_rating,
                        )}
                      >
                        <summary>Narrow the pool</summary>
                        <p className="wizard-note">
                          Additive filters (AND) saved on this channel — e.g. 1970s ∩ Horror.
                          Refill applies them to the lineup.
                        </p>
                        <label>
                          Genre
                          <select
                            data-testid={`live-channels-station-genre-${settingsStationId}`}
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
                            data-testid={`live-channels-station-decade-${settingsStationId}`}
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
                            data-testid={`live-channels-station-theme-${settingsStationId}`}
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
                            data-testid={`live-channels-station-rating-${settingsStationId}`}
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
                          data-testid={`live-channels-station-scope-${settingsStationId}`}
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
                      <QueuePadControl
                        value={stationCraftDraft}
                        onChange={(next) =>
                          setStationCraftDraft((prev) => ({ ...prev, ...next }))
                        }
                        testIdPrefix={`live-channels-station-queue-pad-${settingsStationId}`}
                      />
                      <label className="live-channels-checkbox">
                        <input
                          type="checkbox"
                          data-testid={`live-channels-station-captions-${settingsStationId}`}
                          checked={Boolean(stationCraftDraft.subtitles_enabled)}
                          onChange={(event) =>
                            setStationCraftDraft((prev) => ({
                              ...prev,
                              subtitles_enabled: event.target.checked,
                            }))
                          }
                        />
                        Show captions when the channel has them
                      </label>
                      <div className="wizard-actions">
                        <button
                          type="button"
                          className="ghost"
                          data-testid={`live-channels-station-save-${settingsStationId}`}
                          disabled={liveLocked || !settingsStationId || liveBusy === `settings-${settingsStationId}`}
                          onClick={async () => {
                            if (!settingsStationId || !stationCraftDraft) return;
                            setLiveBusy(`settings-${settingsStationId}`);
                            try {
                              const nextName = String(stationCraftDraft.name || "").trim();
                              if (!nextName) {
                                setActionFeedback(
                                  "live-channels",
                                  "error",
                                  "Station name cannot be empty.",
                                  { block: "stations" },
                                );
                                return;
                              }
                              const result = await patchLiveChannelsStationSettings(settingsStationId, {
                                name: nextName,
                                media_scope: stationCraftDraft.media_scope || "both",
                                subtitles_enabled: Boolean(stationCraftDraft.subtitles_enabled),
                                motif: stationCraftDraft.motif || "",
                                cluster_tag: stationCraftDraft.cluster_tag || "",
                                craft_filters: buildCraftFiltersPayload(stationCraftDraft),
                                queue_pad: queuePadPayload(stationCraftDraft),
                              });
                              setActionFeedback(
                                "live-channels",
                                "success",
                                result.message || "Station craft saved. Refill to apply the lineup.",
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
                          {liveBusy === `settings-${settingsStationId}` ? "Saving…" : "Save changes"}
                        </button>
                        <button
                          type="button"
                          className="primary"
                          data-testid={`live-channels-station-refill-cta-${settingsStationId}`}
                          disabled={liveLocked || !settingsStationId || liveBusy === `refill-${settingsStationId}`}
                          onClick={() => refillStation(settingsStationId, settingsStation?.name)}
                        >
                          {liveBusy === `refill-${settingsStationId}` ? "Rebuilding…" : "Rebuild lineup"}
                        </button>
                      </div>
                      <p className="wizard-note">
                        Save updates the channel recipe only. Refill rebuilds the lineup
                        from those filters — empty when nothing matches, never the whole
                        library. Captions still depend on the Live encode or a Plex-backed
                        track for the title on air.
                      </p>
                    </div>
                  </div>
                  ) : null}
        </>
      ) : null}
    </div>
  );
}
