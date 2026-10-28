import { useEffect, useMemo, useRef, useState } from "react";
import {
  getLiveChannelsCraftOptions,
  getLiveChannelsContinuityStatus,
  getLiveChannelsLifecycleStatus,
  getLiveChannelsPublishStatus,
  getLiveChannelsStatus,
  getLiveChannelsTunarrLogs,
  getSettings,
  postLiveChannelsContinuityRepair,
  postLiveChannelsLifecycle,
} from "../api/client";
import InlineAlert from "../components/InlineAlert";
import { liveChannelsStartTimeoutAlertType } from "../lib/liveChannelsEngineFeedback.js";
import { isLiveJobBusy } from "../lib/liveChannelsJob.js";
import { filterLiveCollections } from "../lib/liveChannelsCraft.js";
import { ownerLiveText } from "../lib/liveChannelsOwnerCopy.js";
import { formatPublishFeedback } from "../lib/liveChannelsPublishFeedback.js";
import { isLiveChannelsLaunched } from "../pages/admin/LiveChannelsParts";
import { startVisibleBusyPoll } from "../lib/visibleBusyPoll.js";

export { formatPublishFeedback };

export default function useLiveChannelsAdmin({
  settings,
  persistSettings,
  updateTunarrSettings,
  updateFeatureFlags,
  setSettings,
  confirm,
}) {
  const [liveChannelsStatus, setLiveChannelsStatus] = useState(null);
  const [livePreflight, setLivePreflight] = useState(null);
  const [liveStarters, setLiveStarters] = useState(null);
  const [liveCraftOptions, setLiveCraftOptions] = useState(null);
  const [liveCraft, setLiveCraft] = useState({
    name: "",
    number: "",
    source: "motif",
    programming_mode: "shuffle",
    media_scope: "both",
    motif: "",
    cluster_tag: "",
    collection_id: "",
    collection_title: "",
    youth_safe: false,
    genres: [],
    decade: "",
    theme: "",
    content_rating: "",
  });
  const [liveCraftPreview, setLiveCraftPreview] = useState(null);
  const [liveCraftPreviewBusy, setLiveCraftPreviewBusy] = useState(false);
  const [fillerPathDraft, setFillerPathDraft] = useState("");
  const [padFlexDraft, setPadFlexDraft] = useState("");
  const [exclusionNameDraft, setExclusionNameDraft] = useState("");
  const [stationSettingsOpen, setStationSettingsOpen] = useState(null);
  const [liveAttach, setLiveAttach] = useState(null);
  const [liveBusy, setLiveBusy] = useState(null);
  const [liveEngineProgress, setLiveEngineProgress] = useState(null);
  const [liveEngineError, setLiveEngineError] = useState("");
  const [liveContinuityProgress, setLiveContinuityProgress] = useState(null);
  const [livePublishProgress, setLivePublishProgress] = useState(null);
  /** Per-card success/error for Live Channels (not the page-bottom banner). */
  const [liveBlockFeedback, setLiveBlockFeedback] = useState({});
  const [selectedStarters, setSelectedStarters] = useState({});
  const [tunarrLogsOpen, setTunarrLogsOpen] = useState(false);
  const [tunarrLogs, setTunarrLogs] = useState(null);
  const [tunarrLogsBusy, setTunarrLogsBusy] = useState(false);
  const [liveChannelsTab, setLiveChannelsTab] = useState(null); // null = auto by launch state
  const [collectionFilter, setCollectionFilter] = useState("");
  const enginePollRef = useRef(null);
  const continuityPollRef = useRef(null);
  const publishPollRef = useRef(null);

  const liveLaunched = useMemo(
    () => isLiveChannelsLaunched(liveChannelsStatus, liveEngineProgress),
    [liveChannelsStatus, liveEngineProgress],
  );
  const effectiveLiveTab = liveChannelsTab || (liveLaunched ? "stations" : "setup");
  const filteredLiveCollections = useMemo(
    () =>
      filterLiveCollections(liveCraftOptions?.collections, {
        mediaScope: liveCraft.media_scope || "both",
        filterQuery: collectionFilter,
        selectedId: liveCraft.collection_id,
      }),
    [
      liveCraftOptions?.collections,
      collectionFilter,
      liveCraft.collection_id,
      liveCraft.media_scope,
    ],
  );
  const fillerBinds = settings?.tunarr?.filler_binds || [];
  useEffect(() => {
    if (!settings?.features?.live_channels_enabled) {
      setLiveChannelsStatus(null);
      return;
    }
    getLiveChannelsStatus()
      .then(setLiveChannelsStatus)
      .catch(() => setLiveChannelsStatus(null));
    getLiveChannelsCraftOptions()
      .then((opts) => {
        setLiveCraftOptions(opts);
        // Provisional (warming) numbers must not seed the form — wait for the real ones.
        if (opts?.warming) return;
        setLiveCraft((prev) => ({
          ...prev,
          number: prev.number || String(opts.next_channel_number || 100),
          motif: prev.motif || opts.motifs?.[0]?.value || "",
          cluster_tag: prev.cluster_tag || opts.taste_clusters?.[0]?.cluster_tag || "",
        }));
        if (opts?.pad_flex_max_minutes != null) {
          setPadFlexDraft((prev) => (prev === "" ? String(opts.pad_flex_max_minutes) : prev));
        }
        if (opts?.exclusion_collection_name) {
          setExclusionNameDraft((prev) => (prev === "" ? opts.exclusion_collection_name : prev));
        }
      })
      .catch(() => setLiveCraftOptions(null));
    if (settings?.tunarr?.docker_orchestration) {
      getLiveChannelsLifecycleStatus()
        .then(setLiveEngineProgress)
        .catch(() => {});
    }
  }, [settings?.features?.live_channels_enabled, settings?.tunarr?.url, settings?.tunarr?.docker_orchestration]);

  // Server serves Live status / craft / lifecycle stale-while-revalidate. While
  // stale/warming, re-poll briefly so real probes replace the cached snapshot.
  const liveStatusRevalidating = Boolean(liveChannelsStatus?.warming || liveChannelsStatus?.stale);
  const liveCraftWarming = Boolean(liveCraftOptions?.warming);
  const liveLifecycleRevalidating = Boolean(
    liveEngineProgress?.warming || liveEngineProgress?.stale,
  );
  useEffect(() => {
        if (!liveStatusRevalidating && !liveCraftWarming && !liveLifecycleRevalidating) {
      return undefined;
    }
    let tries = 0;
    const timer = setInterval(() => {
      tries += 1;
      if (tries > 12) {
        clearInterval(timer);
        return;
      }
      if (liveStatusRevalidating) {
        getLiveChannelsStatus()
          .then(setLiveChannelsStatus)
          .catch(() => {});
      }
      if (liveCraftWarming) {
        getLiveChannelsCraftOptions()
          .then((opts) => {
            setLiveCraftOptions(opts);
            if (opts?.warming) return;
            setLiveCraft((prev) => ({
              ...prev,
              number: prev.number || String(opts.next_channel_number || 100),
              motif: prev.motif || opts.motifs?.[0]?.value || "",
              cluster_tag: prev.cluster_tag || opts.taste_clusters?.[0]?.cluster_tag || "",
            }));
          })
          .catch(() => {});
      }
      if (liveLifecycleRevalidating) {
        getLiveChannelsLifecycleStatus()
          .then(setLiveEngineProgress)
          .catch(() => {});
      }
    }, 2500);
    return () => clearInterval(timer);
  }, [liveStatusRevalidating, liveCraftWarming, liveLifecycleRevalidating]);

  const liveJobBusy = isLiveJobBusy(liveChannelsStatus?.job);
  useEffect(() => {
    const localBusy = Boolean(liveBusy) && liveBusy !== "status" && liveBusy !== "attach";
    if (!liveJobBusy && !localBusy) return undefined;
    return startVisibleBusyPoll(
      () =>
        getLiveChannelsStatus()
          .then(setLiveChannelsStatus)
          .catch(() => {}),
      { isBusy: () => true },
    );
  }, [liveJobBusy, liveBusy]);

  useEffect(() => {
    return () => {
      if (enginePollRef.current) {
        clearInterval(enginePollRef.current);
        enginePollRef.current = null;
      }
      if (continuityPollRef.current) {
        clearInterval(continuityPollRef.current);
        continuityPollRef.current = null;
      }
      if (publishPollRef.current) {
        clearInterval(publishPollRef.current);
        publishPollRef.current = null;
      }
    };
  }, []);

  function setLiveFeedback(block, type, message, options = {}) {
    const key = String(block || "general").trim() || "general";
    const details = Array.isArray(options.details) ? options.details : null;
    setLiveBlockFeedback((prev) => ({
      ...prev,
      [key]: { type, message, details },
    }));
  }

  function clearLiveFeedback(block) {
    if (!block) {
      setLiveBlockFeedback({});
      return;
    }
    setLiveBlockFeedback((prev) => {
      if (!prev[block]) return prev;
      const next = { ...prev };
      delete next[block];
      return next;
    });
  }

  function renderLiveBlockAlert(block) {
    const fb = liveBlockFeedback[block];
    if (!fb?.message) return null;
    return (
      <InlineAlert
        type={fb.type}
        message={ownerLiveText(fb.message)}
        details={Array.isArray(fb.details) ? fb.details.map(ownerLiveText) : fb.details}
        testId={`live-channels-${block}-alert`}
      />
    );
  }

  function setActionFeedback(area, type, message, options = {}) {
    const details = Array.isArray(options.details) ? options.details : null;
    // Live Channels: route to the card block (options.block). Do not park at page bottom.
    if (area === "live-channels") {
      setLiveFeedback(options.block || "general", type, message, { details });
    }
  }

  function clearActionFeedback(area) {
    if (area === "live-channels") {
      clearLiveFeedback();
    }
  }

  async function refreshTunarrLogs() {
    setTunarrLogsBusy(true);
    try {
      const payload = await getLiveChannelsTunarrLogs(200);
      setTunarrLogs(payload);
    } catch (error) {
      setTunarrLogs({
        ok: false,
        text: "",
        source: "",
        message: error.message || "Could not load broadcast engine logs.",
      });
    } finally {
      setTunarrLogsBusy(false);
    }
  }
  async function handleLiveChannelsEnabled(enabled) {
    if (
      !enabled &&
      !(await confirm({
        title: "Turn off Live Channels",
        body: "Turn off Live Channels? On now hides for the household. Saved channels stay on disk.",
        confirmLabel: "Turn off",
        danger: true,
      }))
    ) {
      return;
    }
    clearActionFeedback("live-channels");
    updateFeatureFlags({ live_channels_enabled: enabled });
    setLiveBusy(enabled ? "enable" : "disable");
    try {
      await persistSettings({
        features: { ...(settings.features || {}), live_channels_enabled: enabled },
      });
      if (enabled) {
        getLiveChannelsStatus().then(setLiveChannelsStatus).catch(() => {});
      } else {
        setLiveChannelsStatus(null);
        setLivePreflight(null);
        setLiveStarters(null);
        setLiveAttach(null);
        setLiveEngineProgress(null);
        setLiveEngineError("");
        setLiveChannelsTab(null);
        setCollectionFilter("");
        stopEngineProgressPoll();
      }
    } catch (error) {
      updateFeatureFlags({ live_channels_enabled: !enabled });
      setActionFeedback("live-channels", "error", error.message, { block: "hero" });
    } finally {
      setLiveBusy(null);
    }
  }

  function stopEngineProgressPoll() {
    if (enginePollRef.current) {
      clearInterval(enginePollRef.current);
      enginePollRef.current = null;
    }
  }

  async function pollEngineProgressOnce() {
    try {
      const progress = await getLiveChannelsLifecycleStatus();
      setLiveEngineProgress(progress);
      if (progress?.ready) {
        setLiveEngineError("");
      } else if (progress?.phase === "error" && progress?.error) {
        setLiveEngineError(progress.error);
      }
      return progress;
    } catch {
      return null;
    }
  }

  function stopContinuityProgressPoll() {
    if (continuityPollRef.current) {
      clearInterval(continuityPollRef.current);
      continuityPollRef.current = null;
    }
  }

  async function pollContinuityProgressOnce() {
    try {
      const progress = await getLiveChannelsContinuityStatus();
      setLiveContinuityProgress(progress);
      return progress;
    } catch {
      return null;
    }
  }

  function continuityPhaseLabel(phase) {
    switch (phase) {
      case "queued":
        return "Queued";
      case "remounting":
        return "Restarting TV engine";
      case "waiting_ready":
        return "Waiting for TV engine ready";
      case "scoping_libraries":
        return "Scoping libraries";
      case "scanning_filler":
        return "Scanning breaks";
      case "attaching":
        return "Attaching breaks";
      case "refilling":
        return "Refilling lineups";
      case "warming":
        return "Warming streams";
      case "done":
        return "Finished";
      case "error":
        return "Failed";
      default:
        return "Working…";
    }
  }

  async function runContinuityJob(body = {}, { successFallback = "Continuity update finished.", block = "stations" } = {}) {
    clearLiveFeedback(block);
    clearActionFeedback("live-channels");
    setLiveBusy("continuity-repair");
    setLiveContinuityProgress({
      phase: "queued",
      percent: 5,
      message: "Starting continuity job…",
      busy: true,
      ok: true,
      determinate: true,
    });
    stopContinuityProgressPoll();
    const startedAt = Date.now();
    const timeoutMs = 12 * 60 * 1000;
    continuityPollRef.current = setInterval(() => {
      pollContinuityProgressOnce().then((progress) => {
        if (!progress) return;
        if (
          progress.phase === "done" ||
          progress.phase === "error" ||
          (!progress.busy && progress.phase !== "queued") ||
          Date.now() - startedAt > timeoutMs
        ) {
          stopContinuityProgressPoll();
        }
      });
    }, 1500);

    try {
      const accepted = await postLiveChannelsContinuityRepair(body);
      if (accepted?.async === false && accepted?.ok != null) {
        // Sync diagnostic path — finish immediately.
        stopContinuityProgressPoll();
        setLiveContinuityProgress({
          phase: accepted.ok ? "done" : "error",
          percent: accepted.ok ? 100 : 0,
          message: accepted.message || successFallback,
          busy: false,
          ok: Boolean(accepted.ok),
          error: accepted.ok ? "" : accepted.message,
          result: accepted,
        });
        setActionFeedback("live-channels",
          accepted.ok ? "success" : "error",
          accepted.message || successFallback,
          { block },
        );
        setLiveChannelsStatus(await getLiveChannelsStatus());
        return accepted;
      }

      const deadline = Date.now() + timeoutMs;
      let progress = await pollContinuityProgressOnce();
      while (Date.now() < deadline) {
        if (progress?.phase === "done" || progress?.phase === "error") break;
        if (progress && !progress.busy && progress.phase !== "queued") break;
        await new Promise((resolve) => setTimeout(resolve, 1500));
        progress = await pollContinuityProgressOnce();
      }
      stopContinuityProgressPoll();
      if (progress?.phase === "done") {
        setActionFeedback("live-channels",
          "success",
          progress.message || progress.result?.message || successFallback,
          { block },
        );
        setLiveChannelsStatus(await getLiveChannelsStatus());
      } else if (progress?.phase === "error") {
        setActionFeedback("live-channels",
          "error",
          progress.error || progress.message || "Continuity repair failed.",
          { block },
        );
      } else {
        setActionFeedback("live-channels",
          "error",
          "Timed out waiting for continuity repair. Check Admin Logs for live_channels.continuity stages.",
          { block },
        );
      }
      return progress;
    } catch (error) {
      stopContinuityProgressPoll();
      setLiveContinuityProgress((prev) => ({
        ...(prev || {}),
        phase: "error",
        percent: 0,
        busy: false,
        ok: false,
        error: error.message,
        message: error.message,
      }));
      setActionFeedback("live-channels", "error", error.message, { block });
      throw error;
    } finally {
      stopContinuityProgressPoll();
      setLiveBusy(null);
    }
  }

  function stopPublishProgressPoll() {
    if (publishPollRef.current) {
      clearInterval(publishPollRef.current);
      publishPollRef.current = null;
    }
  }

  async function pollPublishProgressOnce() {
    try {
      const progress = await getLiveChannelsPublishStatus();
      setLivePublishProgress(progress);
      return progress;
    } catch {
      return null;
    }
  }

  function publishPhaseLabel(phase) {
    switch (phase) {
      case "queued":
        return "Queued";
      case "wiring":
        return "Wiring media source";
      case "matching":
        return "Matching titles";
      case "publishing":
        return "Publishing station";
      case "plex_sync":
        return "Refreshing Plex channels";
      case "warming":
        return "Warming streams";
      case "done":
        return "Finished";
      case "error":
        return "Failed";
      default:
        return "Working…";
    }
  }

  async function runPublishJob(startFn, { busyKey = "publish", block = "collection", successFallback = "Publish finished." } = {}) {
    clearLiveFeedback(block);
    clearActionFeedback("live-channels");
    setLiveBusy(busyKey);
    setLivePublishProgress({
      phase: "queued",
      percent: 5,
      message: "Starting publish…",
      busy: true,
      ok: true,
      determinate: true,
    });
    stopPublishProgressPoll();
    const startedAt = Date.now();
    const timeoutMs = 12 * 60 * 1000;
    publishPollRef.current = setInterval(() => {
      pollPublishProgressOnce().then((progress) => {
        if (!progress) return;
        if (
          progress.phase === "done" ||
          progress.phase === "error" ||
          (!progress.busy && progress.phase !== "queued") ||
          Date.now() - startedAt > timeoutMs
        ) {
          stopPublishProgressPoll();
        }
      });
    }, 1500);

    try {
      const accepted = await startFn();
      if (accepted?.async === false && accepted?.ok != null) {
        stopPublishProgressPoll();
        const feedback = formatPublishFeedback(accepted);
        setLivePublishProgress({
          phase: accepted.ok !== false && !accepted.count_errors ? "done" : "error",
          percent: 100,
          message: feedback.summary,
          busy: false,
          ok: feedback.type !== "error",
          error: feedback.type === "error" ? feedback.summary : "",
          result: accepted,
        });
        setActionFeedback("live-channels", feedback.type, feedback.summary, {
          block,
          details: feedback.details,
        });
        setLiveChannelsStatus(await getLiveChannelsStatus());
        setLiveCraftOptions(await getLiveChannelsCraftOptions());
        return accepted;
      }

      const deadline = Date.now() + timeoutMs;
      let progress = await pollPublishProgressOnce();
      while (Date.now() < deadline) {
        if (progress?.phase === "done" || progress?.phase === "error") break;
        if (progress && !progress.busy && progress.phase !== "queued") break;
        await new Promise((resolve) => setTimeout(resolve, 1500));
        progress = await pollPublishProgressOnce();
      }
      stopPublishProgressPoll();
      if (progress?.phase === "done") {
        const result = progress.result || {};
        const feedback = formatPublishFeedback({
          ...result,
          note: progress.message || result.note,
          ok: true,
        });
        setActionFeedback("live-channels", "success", feedback.summary, {
          block,
          details: feedback.details,
        });
        setLiveChannelsStatus(await getLiveChannelsStatus());
        setLiveCraftOptions(await getLiveChannelsCraftOptions());
      } else if (progress?.phase === "error") {
        setActionFeedback("live-channels", "error", progress.error || progress.message || "Publish failed.", {
          block,
        });
      } else {
        setActionFeedback("live-channels", "error", "Timed out waiting for publish. Check Admin Logs for live_channels.publish stages.", {
          block,
        });
      }
      return progress;
    } catch (error) {
      stopPublishProgressPoll();
      setLivePublishProgress((prev) => ({
        ...(prev || {}),
        phase: "error",
        percent: 0,
        busy: false,
        ok: false,
        error: error.message,
        message: error.message,
      }));
      setActionFeedback("live-channels", "error", error.message, { block });
      throw error;
    } finally {
      stopPublishProgressPoll();
      setLiveBusy(null);
    }
  }

  function renderPublishProgress(block) {
    const publishBusy =
      liveBusy === "collection" || liveBusy === "craft" || liveBusy === "show";
    const busyMatch =
      (block === "collection" && liveBusy === "collection") ||
      (block === "craft" && liveBusy === "craft") ||
      (block === "show" && liveBusy === "show") ||
      (block === "publish" && publishBusy);
    if (
      !(
        busyMatch ||
        (livePublishProgress &&
          livePublishProgress.phase &&
          livePublishProgress.phase !== "idle" &&
          (publishBusy || livePublishProgress.mode === block))
      )
    ) {
      return null;
    }
    const done = livePublishProgress?.phase === "done";
    const failed = livePublishProgress?.phase === "error";
    return (
      <div
        className="live-channels-engine-progress"
        data-testid={`live-channels-publish-progress-${block}`}
      >
        {done ? (
          <InlineAlert
            type="success"
            message={livePublishProgress?.message || "Publish finished"}
            testId={`live-channels-publish-success-${block}`}
          />
        ) : (
          <>
            <p className="live-channels-engine-progress-headline">
              {livePublishProgress?.message || "Publishing…"}
            </p>
            <div
              className="live-channels-engine-progress-bar"
              role="progressbar"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={
                Number.isFinite(livePublishProgress?.percent)
                  ? livePublishProgress.percent
                  : undefined
              }
              aria-label="Publish progress"
            >
              <span
                className="live-channels-engine-progress-fill"
                style={{
                  width: `${Math.max(
                    8,
                    Math.min(100, Number(livePublishProgress?.percent) || 15),
                  )}%`,
                }}
              />
            </div>
            <p className="wizard-note live-channels-engine-phase">
              {publishPhaseLabel(livePublishProgress?.phase)}
              {Number.isFinite(livePublishProgress?.percent)
                ? ` · ${livePublishProgress.percent}%`
                : ""}
            </p>
          </>
        )}
        {failed ? (
          <div
            className="inline-alert inline-alert-error"
            data-testid={`live-channels-publish-error-${block}`}
            role="alert"
          >
            <span className="inline-alert-message">
              {livePublishProgress?.error || livePublishProgress?.message}
            </span>
          </div>
        ) : null}
      </div>
    );
  }

  function renderContinuityProgress() {
    if (
      !(
        liveBusy === "continuity-repair" ||
        (liveContinuityProgress &&
          liveContinuityProgress.phase &&
          liveContinuityProgress.phase !== "idle")
      )
    ) {
      return null;
    }
    const done = liveContinuityProgress?.phase === "done";
    const failed = liveContinuityProgress?.phase === "error";
    return (
      <div
        className="live-channels-engine-progress"
        data-testid="live-channels-continuity-progress"
      >
        {done ? (
          <InlineAlert
            type="success"
            message={liveContinuityProgress?.message || "Continuity repair finished"}
            testId="live-channels-continuity-success"
          />
        ) : (
          <>
            <p className="live-channels-engine-progress-headline">
              {liveContinuityProgress?.message ||
                (liveBusy === "continuity-repair" ? "Repairing continuity…" : "Working…")}
            </p>
            <div
              className={`live-channels-engine-progress-bar${
                liveBusy === "continuity-repair" && !(liveContinuityProgress?.percent > 0)
                  ? " is-indeterminate"
                  : ""
              }`}
              role="progressbar"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={
                Number.isFinite(liveContinuityProgress?.percent)
                  ? liveContinuityProgress.percent
                  : undefined
              }
              aria-label="Continuity repair progress"
            >
              <span
                className="live-channels-engine-progress-fill"
                style={{
                  width: `${Math.max(
                    8,
                    Math.min(100, Number(liveContinuityProgress?.percent) || 15),
                  )}%`,
                }}
              />
            </div>
            <p className="wizard-note live-channels-engine-phase">
              {continuityPhaseLabel(liveContinuityProgress?.phase)}
              {Number.isFinite(liveContinuityProgress?.percent)
                ? ` · ${liveContinuityProgress.percent}%`
                : ""}
            </p>
          </>
        )}
        {failed ? (
          <div
            className="inline-alert inline-alert-error"
            data-testid="live-channels-continuity-error"
            role="alert"
          >
            <span className="inline-alert-message">
              {liveContinuityProgress?.error || liveContinuityProgress?.message}
            </span>
          </div>
        ) : null}
      </div>
    );
  }

  async function startBroadcastEngine() {
    clearActionFeedback("live-channels");
    setLiveEngineError("");
    setLiveBusy("lifecycle");
    setLiveEngineProgress({
      phase: "pulling",
      percent: 15,
      message: "Pulling image",
      ready: false,
      busy: true,
      ok: true,
      determinate: true,
    });
    stopEngineProgressPoll();
    const startedAt = Date.now();
    const timeoutMs = 5 * 60 * 1000;
    enginePollRef.current = setInterval(() => {
      pollEngineProgressOnce().then((progress) => {
        if (!progress) return;
        if (progress.ready || progress.phase === "error" || Date.now() - startedAt > timeoutMs) {
          stopEngineProgressPoll();
        }
      });
    }, 1500);

    try {
      const result = await postLiveChannelsLifecycle("ensure_running");
      if (result.tunarr_url) {
        updateTunarrSettings({ url: result.tunarr_url });
      }
      if (!result.ok) {
        const message = result.message || "TV engine failed to start.";
        setLiveEngineError(message);
        setLiveEngineProgress((prev) => ({
          ...(prev || {}),
          phase: "error",
          percent: 0,
          message,
          ready: false,
          busy: false,
          ok: false,
          error: message,
        }));
        setActionFeedback("live-channels", "error", message, { block: "engine" });
        stopEngineProgressPoll();
        setLiveBusy(null);
        return;
      }
      // Keep polling until Tunarr HTTP is ready (log banner alone is not enough), up to ~5 min.
      const deadline = Date.now() + timeoutMs;
      let progress = await pollEngineProgressOnce();
      while (Date.now() < deadline) {
        if (progress?.ready && progress?.http_ready) break;
        if (progress?.ready) break;
        if (progress?.phase === "error") break;
        await new Promise((resolve) => setTimeout(resolve, 1500));
        progress = await pollEngineProgressOnce();
      }
      stopEngineProgressPoll();
      if (progress?.ready) {
        setActionFeedback("live-channels",
          "success",
          progress.message || "TV engine is ready!",
          { block: "engine" },
        );
      } else if (progress?.phase === "error") {
        setLiveEngineError(progress.error || progress.message || "TV engine failed.");
        setActionFeedback("live-channels", "error", progress.error || progress.message, { block: "engine" });
      } else {
        const stillStarting = Boolean(progress?.still_starting || progress?.container_running);
        const timeoutMsg = stillStarting
          ? "TV engine is still starting — HTTP not ready yet. Meili/scan noise during boot is normal; try again shortly."
          : "Timed out waiting for the TV engine to become ready. Check TV engine logs below.";
        // stillStarting: container up, HTTP not ready — soft notice (ok:true), not a failure.
        setLiveEngineError(stillStarting ? "" : timeoutMsg);
        setLiveEngineProgress((prev) => ({
          ...(prev || {}),
          phase: stillStarting ? "waiting_ready" : "error",
          percent: prev?.percent || 80,
          message: timeoutMsg,
          ready: false,
          busy: false,
          ok: stillStarting,
          error: stillStarting ? "" : timeoutMsg,
          still_starting: stillStarting,
        }));
        setActionFeedback(
          "live-channels",
          liveChannelsStartTimeoutAlertType(stillStarting),
          timeoutMsg,
          { block: "engine" },
        );
      }
      const status = await getLiveChannelsStatus();
      setLiveChannelsStatus(status);
      if (result.tunarr_url) {
        await getSettings().then((next) => setSettings?.(next)).catch(() => {});
      }
    } catch (error) {
      stopEngineProgressPoll();
      const message = error.message || "TV engine failed to start.";
      setLiveEngineError(message);
      setLiveEngineProgress((prev) => ({
        ...(prev || {}),
        phase: "error",
        percent: 0,
        message,
        ready: false,
        busy: false,
        ok: false,
        error: message,
      }));
      setActionFeedback("live-channels", "error", message, { block: "engine" });
    } finally {
      setLiveBusy(null);
    }
  }

  return {
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
    setActionFeedback,
    clearActionFeedback,
  };
}
