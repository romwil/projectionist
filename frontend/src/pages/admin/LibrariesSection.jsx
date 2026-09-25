import { useEffect, useMemo, useState } from "react";
import InlineAlert from "../../components/InlineAlert";
import AdminExecutionCard from "../../components/AdminExecutionCard";
import { api } from "../../api/client";
import RematchStudio from "./RematchStudio";
import RepairMiss from "./RepairMiss";
import {
  formatLastSyncRelative,
  formatSyncJobDetails,
} from "../../lib/jobProgress.js";
import {
  FFMPEG_MISSING,
  SCENE_NAMES_NOT_EVIDENCE,
  STILLS_LEAVE_LAN,
  applyButtonClass,
  confidenceLabel,
  reviewEvidenceSummary,
  selectedFileIds,
  selectionMap,
} from "../../lib/episodeInvestigate.js";
import {
  sonarrFindMissingButtonClass,
  sonarrMissingBySeries,
  sonarrMissingCanCancel,
  sonarrMissingDisplayPercent,
  sonarrMissingPhaseLabel,
  sonarrMissingProgressLine,
  sonarrMissingScanReady,
  sonarrMissingSecondsAgo,
  sonarrSearchMissingButtonClass,
  sonarrWantedDeltaCopy,
} from "../../lib/sonarrMissing.js";

/**
 * Admin Libraries section — sync, Radarr register, Sonarr missing, Plex mapping.
 * Extracted from ConfigPage (H1 incremental carve after LiveChannelsSection);
 * Wave 0 unblocks episode investigation without two agents editing ConfigPage.
 */
export default function LibrariesSection({
  syncingLibrary,
  handleLibrarySync,
  activeSyncJob,
  libraryStats,
  trackedSyncJobId,
  actionAlert,
  radarrGapStats,
  registeringRadarr,
  radarrRegister,
  handleRegisterRadarrExisting,
  handleRadarrRegisterCancel,
  sonarrIncludeSpecials,
  setSonarrIncludeSpecials,
  sonarrMissing,
  handleSonarrMissingScan,
  handleSonarrMissingSearch,
  handleSonarrMissingCancel,
  certifications,
  testing,
  runTest,
  sections,
  settings,
  handleSectionChange,
  movieSections,
  tvSections,
  handleSyncReviewsToggle,
  handlePlexCollectionsToggle,
  handleEphemeralCollectionGcToggle,
  handleEphemeralCollectionGcDryRunToggle,
  updateSettings,
  persistSettings,
  setActionFeedback,
  CertifiedBadge,
}) {
  const [investigateHint, setInvestigateHint] = useState(null);
  const [repairRetryingId, setRepairRetryingId] = useState("");
  const [repairSkippingId, setRepairSkippingId] = useState("");
  const [hiddenRepairs, setHiddenRepairs] = useState(() => new Set());

  function formatLastSync(lastSync) {
    return formatLastSyncRelative(lastSync);
  }

  function scrollToId(id) {
    if (typeof document === "undefined") return;
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function handleRepairRematch() {
    scrollToId("rematch-studio");
  }

  function handleRepairInvestigate(item) {
    setInvestigateHint({ title: item?.title || "", source: item?.source || "" });
    scrollToId("episode-investigate");
  }

  async function handleRepairRetry(item) {
    if (item?.source === "sonarr_missing") {
      handleSonarrMissingSearch?.();
      return;
    }
    if (item?.id == null) return;
    setRepairRetryingId(String(item.id));
    try {
      await api("/admin/rematch/retry", {
        method: "POST",
        body: JSON.stringify({ item_id: Number(item.id) }),
      });
    } catch {
      /* job card + repair copy stay visible */
    } finally {
      setRepairRetryingId("");
    }
  }

  async function handleRepairSkip(item) {
    setRepairSkippingId(String(item.id));
    try {
      if (item?.source === "radarr_register" && item.id != null) {
        await api("/admin/rematch/skip", {
          method: "POST",
          body: JSON.stringify({ item_id: Number(item.id), skipped: true }),
        });
      }
      setHiddenRepairs((prev) => new Set(prev).add(`${item.source}-${item.id}`));
    } catch {
      /* keep the row */
    } finally {
      setRepairSkippingId("");
    }
  }

  const repairRegister = useMemo(() => {
    const items = (radarrRegister?.items || []).filter(
      (row) => !hiddenRepairs.has(`radarr_register-${row.id}`),
    );
    return { ...radarrRegister, items };
  }, [radarrRegister, hiddenRepairs]);

  const repairSonarr = hiddenRepairs.has("sonarr_missing-sonarr-miss")
    ? { ...sonarrMissing, execution: { ...(sonarrMissing?.execution || {}), failed: 0, last_error: "" }, error: "" }
    : sonarrMissing;

  return (
        <>
        <section className="config-section" data-testid="library-sync-card" id="library-sync">
          <h2>Sync library</h2>
          <p className="wizard-note">
            Refresh Projectionist from your Plex libraries. The first sync can take a few minutes while titles
            are indexed and enriched.
          </p>
          <div className="config-actions">
            <button type="button" className="primary" data-testid="library-sync-button" onClick={handleLibrarySync} disabled={syncingLibrary}>
              {syncingLibrary ? "Syncing…" : "Sync library"}
            </button>
          </div>
          {(() => {
            const details = formatSyncJobDetails(activeSyncJob, libraryStats);
            if (!details) return null;
            if (details.state === "running" || syncingLibrary) {
              const live = details.state === "running" ? details : formatSyncJobDetails(
                { ...(activeSyncJob || {}), status: "running", progress: activeSyncJob?.progress || { phase: "preparing", message: "Starting…" } },
                libraryStats,
              );
              return (
                <div className="library-sync-progress" data-testid="library-sync-job-status">
                  <p className="library-sync-progress-headline">
                    <strong>{live.headline}</strong>
                    {typeof live.percent === "number" ? ` · ${live.percent}%` : ""}
                  </p>
                  <p className="library-sync-progress-detail status status-secondary">
                    {live.detail}
                    {live.countHint && !String(live.detail || "").includes(String(activeSyncJob?.progress?.current ?? ""))
                      ? ` · ${live.countHint}`
                      : ""}
                  </p>
                  {typeof live.percent === "number" ? (
                    <div
                      className="library-sync-progress-bar"
                      role="progressbar"
                      aria-valuenow={live.percent}
                      aria-valuemin={0}
                      aria-valuemax={100}
                    >
                      <span className="library-sync-progress-fill" style={{ width: `${live.percent}%` }} />
                    </div>
                  ) : null}
                </div>
              );
            }
            if (details.state === "failed") {
              return (
                <p className="status status-error" data-testid="library-sync-job-status">
                  Sync failed: {details.detail}
                </p>
              );
            }
            if (details.state === "completed" && trackedSyncJobId === activeSyncJob?.id) {
              return (
                <p className="status" data-testid="library-sync-job-status">
                  {details.headline}
                </p>
              );
            }
            return null;
          })()}
          {libraryStats ? (
            <p className="status status-secondary" data-testid="library-sync-stats">
              {libraryStats.movies} movies · {libraryStats.shows} shows
              {libraryStats.last_sync
                ? ` · Last synced ${formatLastSync(libraryStats.last_sync)}`
                : syncingLibrary
                  ? " · Syncing…"
                  : " · Never synced"}
            </p>
          ) : (
            <p className="status status-secondary" data-testid="library-sync-stats">
              No library indexed yet — run Sync library after Plex is connected.
            </p>
          )}
          <InlineAlert
            type={actionAlert?.area === "library-sync" ? actionAlert.type : null}
            message={actionAlert?.area === "library-sync" ? actionAlert.message : null}
          />
        </section>

        <section className="config-section" data-testid="radarr-register-existing-card">
          <h2>Radarr — register on disk</h2>
          <p className="wizard-note">
            Movies already in Plex but missing from Radarr by TMDB id can be registered
            without starting a download search. A path conflict means Radarr already owns
            that folder under a different identity — rematch, don’t ignore. Titles without
            a TMDB id need a Plex rematch first.
          </p>
          <p className="status status-secondary" data-testid="radarr-owned-not-indexed-stats">
            {radarrGapStats
              ? `${radarrGapStats.total} ready to register${
                  radarrGapStats.needs_rematch
                    ? ` · ${radarrGapStats.needs_rematch} need rematch`
                    : ""
                }`
              : "Checking Radarr gaps…"}
          </p>
          <div className="config-actions">
            <button
              type="button"
              className="primary"
              data-testid="radarr-register-existing-button"
              onClick={handleRegisterRadarrExisting}
              disabled={registeringRadarr || Boolean(radarrRegister?.busy) || !radarrGapStats?.total}
            >
              {radarrRegister?.busy ? "Registering…" : "Register up to 25 in Radarr"}
            </button>
          </div>
          <AdminExecutionCard
            job={radarrRegister}
            testId="radarr-register-progress"
            phaseLabels={{ registering: "Registering in Radarr", done: "Registration finished" }}
            onCancel={handleRadarrRegisterCancel}
          />
          <InlineAlert
            type={actionAlert?.area === "radarr-register" ? actionAlert.type : null}
            message={actionAlert?.area === "radarr-register" ? actionAlert.message : null}
          />
        </section>

        <RepairMiss
          radarrRegister={repairRegister}
          onRematch={handleRepairRematch}
          onRetry={handleRepairRetry}
          onSkip={handleRepairSkip}
          onInvestigate={handleRepairInvestigate}
          retryingId={repairRetryingId}
          skippingId={repairSkippingId}
        />

        <section className="config-section" data-testid="sonarr-find-missing-card">
          <h2>Sonarr — find all missing</h2>
          <p className="wizard-note">
            Re-derives gaps from each series’ episode records (aired, monitored, no file) instead of
            trusting Sonarr’s Wanted list. After the scan, confirm to submit EpisodeSearch in batches.
            Sonarr then runs those commands on its own queue — often a few at a time — so watch
            queued / running / completed here. That is not the same as a download-client grab.
          </p>
          <label className="config-toggle" data-testid="sonarr-include-specials">
            <input
              type="checkbox"
              checked={sonarrIncludeSpecials}
              onChange={(event) => setSonarrIncludeSpecials(event.target.checked)}
              disabled={Boolean(sonarrMissing?.busy)}
            />
            <span>Include specials</span>
          </label>
          <div className="config-actions">
            <button
              type="button"
              className={sonarrFindMissingButtonClass(sonarrMissing)}
              data-testid="sonarr-find-missing-button"
              onClick={handleSonarrMissingScan}
              disabled={Boolean(sonarrMissing?.busy)}
            >
              {sonarrMissing?.busy && !["searching", "executing"].includes(String(sonarrMissing?.phase || ""))
                ? "Scanning…"
                : "Find all missing"}
            </button>
            <button
              type="button"
              className={sonarrSearchMissingButtonClass(sonarrMissing)}
              data-testid="sonarr-search-missing-button"
              onClick={handleSonarrMissingSearch}
              disabled={!sonarrMissingScanReady(sonarrMissing) || Boolean(sonarrMissing?.busy)}
            >
              {sonarrMissing?.phase === "searching"
                ? "Submitting…"
                : sonarrMissing?.phase === "executing"
                  ? "Sonarr searching…"
                  : "Search these"}
            </button>
            {sonarrMissingCanCancel(sonarrMissing) ? (
              <button
                type="button"
                className="ghost"
                data-testid="sonarr-cancel-missing-button"
                onClick={handleSonarrMissingCancel}
              >
                Cancel remaining
              </button>
            ) : null}
          </div>
          {sonarrMissingProgressLine(sonarrMissing) ? (
            <div className="library-sync-progress" data-testid="sonarr-missing-progress">
              <p className="library-sync-progress-headline">
                <strong>
                  {sonarrMissingPhaseLabel(sonarrMissing?.phase)}
                </strong>
                {typeof sonarrMissingDisplayPercent(sonarrMissing) === "number"
                  ? ` · ${sonarrMissingDisplayPercent(sonarrMissing)}%`
                  : ""}
              </p>
              <p className="library-sync-progress-detail status status-secondary">
                {sonarrMissingProgressLine(sonarrMissing)}
              </p>
              {sonarrMissing?.execution && Number(sonarrMissing.execution.total) > 0 ? (
                <div className="sonarr-missing-counts" data-testid="sonarr-missing-execution">
                  <span>{Number(sonarrMissing.execution.queued) || 0} queued</span>
                  <span>{Number(sonarrMissing.execution.running) || 0} running</span>
                  <span>{Number(sonarrMissing.execution.completed) || 0} completed</span>
                  <span data-tone={Number(sonarrMissing.execution.failed) ? "failed" : undefined}>
                    {Number(sonarrMissing.execution.failed) || 0} failed
                  </span>
                  {Number(sonarrMissing.execution.cancelled) ? (
                    <span>{Number(sonarrMissing.execution.cancelled)} cancelled</span>
                  ) : null}
                </div>
              ) : null}
              {sonarrMissing?.execution?.current ? (
                <p className="wizard-note" data-testid="sonarr-missing-current">
                  Current: {sonarrMissing.execution.current.message || sonarrMissing.execution.current.name} (
                  {sonarrMissing.execution.current.status})
                </p>
              ) : null}
              {sonarrMissingSecondsAgo(sonarrMissing?.execution?.seconds_since_last_completion) ? (
                <p className="wizard-note">{sonarrMissingSecondsAgo(sonarrMissing.execution.seconds_since_last_completion)}</p>
              ) : null}
              {sonarrMissing?.execution?.last_error ? (
                <p className="status status-error" data-testid="sonarr-missing-last-error">
                  Last command error: {sonarrMissing.execution.last_error}
                </p>
              ) : null}
              {sonarrMissing?.execution?.throttle_note &&
              ["searching", "executing"].includes(String(sonarrMissing?.phase || "")) ? (
                <p className="wizard-note" data-testid="sonarr-missing-throttle-note">
                  {sonarrMissing.execution.throttle_note}
                </p>
              ) : null}
              {typeof sonarrMissingDisplayPercent(sonarrMissing) === "number" && sonarrMissing?.busy ? (
                <div
                  className="library-sync-progress-bar"
                  role="progressbar"
                  aria-valuenow={sonarrMissingDisplayPercent(sonarrMissing)}
                  aria-valuemin={0}
                  aria-valuemax={100}
                >
                  <span
                    className="library-sync-progress-fill"
                    style={{ width: `${sonarrMissingDisplayPercent(sonarrMissing)}%` }}
                  />
                </div>
              ) : null}
            </div>
          ) : null}
          {sonarrMissing?.result ? (
            <p className="status status-secondary" data-testid="sonarr-missing-wanted-delta">
              {sonarrWantedDeltaCopy(sonarrMissing.result)}
            </p>
          ) : null}
          {sonarrMissingBySeries(sonarrMissing?.result).length ? (
            <div data-testid="sonarr-missing-by-series">
              {sonarrMissingBySeries(sonarrMissing.result).map((group) => (
                <details key={group.seriesId} className="config-advanced-details">
                  <summary>
                    {group.seriesTitle} · {group.count} missing
                  </summary>
                  <ul>
                    {group.episodes.map((episode) => (
                      <li key={episode.episodeId}>
                        {`S${String(episode.season ?? 0).padStart(2, "0")}E${String(episode.episode ?? 0).padStart(2, "0")}`}
                        {episode.title ? ` ${episode.title}` : ""}
                      </li>
                    ))}
                  </ul>
                </details>
              ))}
            </div>
          ) : null}
          <InlineAlert
            type={actionAlert?.area === "sonarr-missing" ? actionAlert.type : null}
            message={actionAlert?.area === "sonarr-missing" ? actionAlert.message : null}
          />
        </section>

        <RepairMiss
          sonarrMissing={repairSonarr}
          onRematch={handleRepairRematch}
          onRetry={handleRepairRetry}
          onSkip={handleRepairSkip}
          onInvestigate={handleRepairInvestigate}
          retryingId={repairRetryingId}
          skippingId={repairSkippingId}
        />

        <RematchStudio
          onInvestigate={handleRepairInvestigate}
          onHighlight={handleRepairRematch}
        />

        <InvestigatePanel focusHint={investigateHint} />

        <section className="config-section" data-testid="plex-library-mapping">
          <h2>Plex libraries</h2>
          <p className="wizard-note">Choose which movie and TV libraries Projectionist indexes. Update these if you rename or add libraries in Plex.</p>
          <div className="wizard-actions">
            <CertifiedBadge certified={certifications.plex?.certified} testing={testing === "plex"} serviceId="plex" />
            {!sections.length ? (
              <button type="button" className="ghost" onClick={() => runTest("plex")} disabled={testing === "plex"}>
                {testing === "plex" ? "Loading libraries…" : "Reload Plex libraries"}
              </button>
            ) : null}
          </div>
          <div className="section-dropdowns">
            <label>
              <span>Movie library</span>
              <select
                data-testid="plex-movie-section"
                value={settings.plex_movie_section ?? ""}
                onChange={(event) => handleSectionChange("plex_movie_section", event.target.value)}
                disabled={!sections.length}
              >
                <option value="">Select a movie library</option>
                {movieSections.map((section) => (
                  <option key={section.key} value={section.key}>
                    {section.title}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>TV library</span>
              <select
                data-testid="plex-tv-section"
                value={settings.plex_tv_section ?? ""}
                onChange={(event) => handleSectionChange("plex_tv_section", event.target.value)}
                disabled={!sections.length}
              >
                <option value="">Select a TV library</option>
                {tvSections.map((section) => (
                  <option key={section.key} value={section.key}>
                    {section.title}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <label className="config-toggle" data-testid="sync-reviews-to-plex">
            <input
              type="checkbox"
              checked={Boolean(settings.sync_reviews_to_plex)}
              onChange={(event) => handleSyncReviewsToggle(event.target.checked)}
            />
            <span>Copy star ratings to Plex when you review a title</span>
          </label>
          <p className="wizard-note">
            A 1–5 star review in Projectionist becomes the matching Plex rating (2, 4, 6, 8, or 10).
          </p>
          <label className="config-toggle" data-testid="plex-collections-enabled">
            <input
              type="checkbox"
              checked={Boolean(settings?.features?.plex_collections_enabled)}
              onChange={(event) => handlePlexCollectionsToggle(event.target.checked)}
            />
            <span>Let the curator propose Plex collections</span>
          </label>
          <p className="wizard-note">
            The curator can suggest creating a collection or adding titles you already own — you always confirm first.
            Agent / movie-night shelves are tagged with a <code>[Projectionist]</code> prefix and expire after the TTL below.
          </p>
          <label className="config-toggle" data-testid="ephemeral-collection-gc-toggle">
            <input
              type="checkbox"
              checked={settings?.features?.ephemeral_collection_gc_enabled !== false}
              onChange={(event) => handleEphemeralCollectionGcToggle(event.target.checked)}
              disabled={!settings?.features?.plex_collections_enabled}
            />
            <span>Auto-clean expired Projectionist movie-night collections</span>
          </label>
          <label className="config-toggle" data-testid="ephemeral-collection-gc-dry-run-toggle">
            <input
              type="checkbox"
              checked={Boolean(settings?.features?.ephemeral_collection_gc_dry_run)}
              onChange={(event) => handleEphemeralCollectionGcDryRunToggle(event.target.checked)}
              disabled={
                !settings?.features?.plex_collections_enabled ||
                settings?.features?.ephemeral_collection_gc_enabled === false
              }
            />
            <span>Dry-run only (log what would be deleted)</span>
          </label>
          <label>
            <span>Ephemeral collection TTL (hours)</span>
            <input
              type="number"
              min={1}
              data-testid="ephemeral-collection-ttl-hours"
              value={settings?.ephemeral_collection_ttl_hours ?? 168}
              onChange={(event) => {
                const next = Math.max(1, Number(event.target.value) || 168);
                updateSettings({ ephemeral_collection_ttl_hours: next });
              }}
              onBlur={() =>
                persistSettings({
                  ephemeral_collection_ttl_hours: Math.max(
                    1,
                    Number(settings?.ephemeral_collection_ttl_hours) || 168,
                  ),
                }).catch((error) => setActionFeedback("plex-sections", "error", error.message))
              }
              disabled={!settings?.features?.plex_collections_enabled}
            />
          </label>
          <InlineAlert
            type={actionAlert?.area === "plex-sections" ? actionAlert.type : null}
            message={actionAlert?.area === "plex-sections" ? actionAlert.message : null}
          />
        </section>
        </>
  );
}

function InvestigatePanel({ focusHint }) {
  const [health, setHealth] = useState(null);
  const [shows, setShows] = useState([]);
  const [showId, setShowId] = useState("");
  const [season, setSeason] = useState("");
  const [useVision, setUseVision] = useState(true);
  const [job, setJob] = useState(null);
  const [applyJob, setApplyJob] = useState(null);
  const [selected, setSelected] = useState({});
  const [reviewOpen, setReviewOpen] = useState(false);
  const [error, setError] = useState("");
  const [busyStart, setBusyStart] = useState(false);

  const rows = useMemo(() => {
    const result = job?.result;
    return Array.isArray(result?.rows) ? result.rows : [];
  }, [job]);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const [nextHealth, nextShows] = await Promise.all([
          api("/admin/investigate/health"),
          api("/admin/investigate/shows"),
        ]);
        if (cancelled) return;
        setHealth(nextHealth);
        setShows(Array.isArray(nextShows?.items) ? nextShows.items : []);
        if (nextHealth?.vision?.default_on === false) setUseVision(false);
      } catch (err) {
        if (!cancelled) setError(err.message || "Could not load Investigate.");
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function poll() {
      try {
        const [status, applyStatus] = await Promise.all([
          api("/admin/investigate/status"),
          api("/admin/investigate/apply/status"),
        ]);
        if (cancelled) return;
        setJob(status);
        setApplyJob(applyStatus);
        if (status?.phase === "done" && Array.isArray(status?.result?.rows)) {
          setReviewOpen(true);
        }
      } catch {
        /* keep last snapshot */
      }
    }
    poll();
    const interval = setInterval(poll, 2000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  useEffect(() => {
    if (!focusHint?.title || !shows.length) return;
    const needle = String(focusHint.title).toLowerCase();
    const match = shows.find((item) => String(item.title || "").toLowerCase().includes(needle));
    if (match) setShowId(String(match.id));
  }, [focusHint, shows]);

  useEffect(() => {
    if (!reviewOpen || !rows.length) return;
    setSelected((prev) => {
      if (Object.keys(prev).length) return prev;
      return selectionMap(rows);
    });
  }, [reviewOpen, rows]);

  const selectedIds = selectedFileIds(rows, selected);
  const investigating = Boolean(job?.busy);
  const applying = Boolean(applyJob?.busy);
  const visionAvailable = Boolean(health?.vision?.available);
  const ffmpegReady = health?.ffmpeg?.available !== false;
  const evidenceSummary = reviewEvidenceSummary(rows, {
    ffmpegReady,
    visionOn: visionAvailable && useVision,
    identifyConfigured: health?.acrcloud?.available !== false,
  });

  async function handleStart() {
    setError("");
    setBusyStart(true);
    setReviewOpen(false);
    setSelected({});
    try {
      const snap = await api("/admin/investigate/start", {
        method: "POST",
        body: JSON.stringify({
          show_id: Number(showId),
          season: season === "" ? null : Number(season),
          use_vision: visionAvailable ? useVision : false,
        }),
      });
      setJob(snap);
    } catch (err) {
      setError(err.message || "Investigate failed to start.");
    } finally {
      setBusyStart(false);
    }
  }

  async function handleCancelJob() {
    try {
      const snap = await api("/admin/investigate/cancel", { method: "POST" });
      setJob(snap);
    } catch (err) {
      setError(err.message || "Could not cancel.");
    }
  }

  async function handleApply() {
    setError("");
    try {
      const snap = await api("/admin/investigate/apply", {
        method: "POST",
        body: JSON.stringify({ file_ids: selectedIds }),
      });
      setApplyJob(snap);
    } catch (err) {
      setError(err.message || "Apply failed to start.");
    }
  }

  async function handleUndo() {
    const applyId = applyJob?.result?.apply_id || applyJob?.apply_id;
    if (!applyId) return;
    try {
      const snap = await api("/admin/investigate/undo", {
        method: "POST",
        body: JSON.stringify({ apply_id: applyId }),
      });
      setApplyJob(snap);
    } catch (err) {
      setError(err.message || "Undo failed.");
    }
  }

  function toggleRow(id) {
    setSelected((prev) => ({ ...prev, [id]: !prev[id] }));
  }

  const currentShow = shows.find((item) => String(item.id) === String(showId));
  const seasonOptions = [];
  if (currentShow?.season_count) {
    for (let n = 1; n <= Number(currentShow.season_count); n += 1) seasonOptions.push(n);
  }

  return (
    <section className="config-section" data-testid="episode-investigate-card" id="episode-investigate">
      <h2>Investigate episodes</h2>
      <p className="wizard-note">{SCENE_NAMES_NOT_EVIDENCE}</p>
      <p className="wizard-note" data-testid="investigate-stills-leave-lan">
        {STILLS_LEAVE_LAN}
      </p>
      {!health?.sonarr?.configured ? (
        <p className="status status-secondary">Sonarr is required so Investigate can see episode files.</p>
      ) : null}
      {!ffmpegReady ? (
        <p className="status status-error" data-testid="investigate-ffmpeg-note">
          {FFMPEG_MISSING}
        </p>
      ) : null}
      <div className="section-dropdowns">
        <label>
          <span>Show</span>
          <select
            data-testid="investigate-show"
            value={showId}
            onChange={(event) => {
              setShowId(event.target.value);
              setSeason("");
            }}
            disabled={investigating || applying}
          >
            <option value="">Select a show</option>
            {shows.map((item) => (
              <option key={item.id} value={item.id}>
                {item.title}
                {item.year ? ` (${item.year})` : ""}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Season (optional)</span>
          <select
            data-testid="investigate-season"
            value={season}
            onChange={(event) => setSeason(event.target.value)}
            disabled={investigating || applying || !showId}
          >
            <option value="">All seasons</option>
            {seasonOptions.map((n) => (
              <option key={n} value={n}>
                Season {n}
              </option>
            ))}
          </select>
        </label>
      </div>
      <label className="config-toggle" data-testid="investigate-vision-toggle">
        <input
          type="checkbox"
          checked={visionAvailable && useVision}
          onChange={(event) => setUseVision(event.target.checked)}
          disabled={!visionAvailable || investigating || applying}
        />
        <span>Include vision (default when the chat LLM accepts images)</span>
      </label>
      <div className="config-actions">
        <button
          type="button"
          className="primary"
          data-testid="investigate-start"
          onClick={handleStart}
          disabled={!showId || investigating || applying || busyStart || !health?.sonarr?.configured}
        >
          {investigating || busyStart ? "Investigating…" : "Investigate"}
        </button>
      </div>
      <AdminExecutionCard
        job={job}
        testId="investigate-progress"
        phaseLabels={{ running: "Investigating", queued: "Queued" }}
        onCancel={handleCancelJob}
      />
      <AdminExecutionCard
        job={applyJob}
        testId="investigate-apply-progress"
        phaseLabels={{ running: "Applying", queued: "Queued" }}
      />
      {applyJob?.result?.apply_id && !applyJob?.busy && !applyJob?.result?.undo ? (
        <div className="config-actions">
          <button type="button" className="ghost" data-testid="investigate-undo" onClick={handleUndo}>
            Undo last apply
          </button>
        </div>
      ) : null}
      {reviewOpen && rows.length && !investigating ? (
        <div className="investigate-review" data-testid="investigate-review">
          <p className="wizard-note">
            Certain and Likely start selected. Uncertain stays off. Deselect any row. Apply remaps
            the same show only.
          </p>
          {evidenceSummary ? (
            <p className="status status-secondary" data-testid="investigate-evidence-summary">
              {evidenceSummary}
            </p>
          ) : null}
          <div className="investigate-review-table-wrap">
            <table className="investigate-review-table">
              <thead>
                <tr>
                  <th scope="col">Apply</th>
                  <th scope="col">Filename claim</th>
                  <th scope="col">File / Sonarr</th>
                  <th scope="col">Evidence</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <InvestigateReviewRow
                    key={row.id}
                    row={row}
                    checked={Boolean(selected[row.id])}
                    onToggle={toggleRow}
                  />
                ))}
              </tbody>
            </table>
          </div>
          <div className="investigate-review-actions">
            <button
              type="button"
              className={applyButtonClass(selectedIds.length)}
              data-testid="investigate-apply"
              onClick={handleApply}
              disabled={!selectedIds.length || applying}
            >
              {applying ? "Applying…" : "Apply selected"}
            </button>
            <button
              type="button"
              className="ghost"
              data-testid="investigate-cancel-review"
              onClick={() => setReviewOpen(false)}
            >
              Cancel
            </button>
          </div>
        </div>
      ) : null}
      {error ? (
        <p className="status status-error" data-testid="investigate-error">
          {error}
        </p>
      ) : null}
    </section>
  );
}

function InvestigateReviewRow({ row, checked, onToggle }) {
  const reasons = Array.isArray(row.reasons) ? row.reasons : [];
  const proposed =
    row.proposed?.scope === "this_series" && row.proposed?.season != null
      ? `S${String(row.proposed.season).padStart(2, "0")}E${String(row.proposed.episode).padStart(2, "0")}${
          row.proposed?.title ? ` ${row.proposed.title}` : ""
        }`
      : "";
  const stills = (row.stills || []).slice(0, 3);
  const tmdbStills = (row.tmdb_stills || []).slice(0, 3);
  return (
    <tr data-testid={`investigate-row-${row.id}`}>
      <td>
        <label className="config-toggle investigate-review-select">
          <input
            type="checkbox"
            data-testid={`investigate-select-${row.id}`}
            checked={checked}
            onChange={() => onToggle(row.id)}
            disabled={row.same_show === false}
          />
          <span className="sr-only">Select {row.filename || row.id}</span>
        </label>
      </td>
      <td data-testid={`investigate-claimed-${row.id}`}>
        <p className="investigate-filename" title={row.filename || ""}>
          {row.filename}
        </p>
      </td>
      <td className="status status-secondary">
        File {row.claimed?.label || "unparsed"}
        {row.sonarr?.label ? ` · Sonarr ${row.sonarr.label}` : ""}
        {row.sonarr?.title ? ` ${row.sonarr.title}` : ""}
      </td>
      <td>
        <details className="investigate-review-evidence">
          <summary>
            {confidenceLabel(row.confidence)}
            {proposed ? ` · ${proposed}` : ""}
            {row.same_show === false ? " · other show (not this sprint)" : ""}
            {reasons.length ? ` · ${reasons[0]}` : ""}
          </summary>
          {reasons.length > 1 ? <p className="wizard-note">{reasons.join(" · ")}</p> : null}
          <div className="investigate-review-stills" data-testid={`investigate-stills-${row.id}`}>
            {stills.map((src, index) => (
              <img key={`file-${index}`} src={src} alt={`File still ${index + 1}`} />
            ))}
            {tmdbStills.map((src, index) => (
              <img key={`tmdb-${index}`} src={src} alt={`TMDB still ${index + 1}`} />
            ))}
          </div>
        </details>
      </td>
    </tr>
  );
}
