import { useEffect, useState } from "react";
import InlineAlert from "../../components/InlineAlert";
import OwnerNowPlayingBreakdown from "../../components/OwnerNowPlayingBreakdown";
import QueuePadControl from "../../components/live/QueuePadControl";
import SeasonalShelves from "../../components/live/SeasonalShelves";
import {
  getLiveChannelsCraftOptions,
  getLiveChannelsStarterPack,
  getLiveChannelsStatus,
  postLiveChannelsPlexAttachGuide,
  postLiveChannelsPlexRepair,
  postLiveChannelsPreflight,
  previewLiveChannelsCraft,
  publishLiveChannelsChannel,
  publishLiveChannelsFromCollection,
  publishLiveChannelsFromShow,
  publishLiveChannelsStarters,
  queryLibrary,
} from "../../api/client";
import { buildCraftFiltersPayload, filterLiveCollections } from "../../lib/liveChannelsCraft.js";
import { craftSoftCapHonestyNote, liveInfrastructureFacts } from "../../lib/liveChannelsCopy.js";
import {
  CHANNEL_KINDS,
  LAUNCH_PHASES,
  MOOD_SOURCES,
  channelSummaryLine,
  createStepsFor,
  launchBlockers,
  launchReadinessRows,
  liveStationState,
  ownerLiveText,
  publishSucceeded,
} from "../../lib/liveChannelsOwnerCopy.js";
import { isLiveMutatingDisabled, plexRebuildConfirmMessage } from "../../lib/liveChannelsJob.js";
import { DEFAULT_QUEUE_PAD_DRAFT, queuePadPayload } from "../../lib/liveQueuePad.js";
import { LiveJobRail, LiveStatusCheck } from "./LiveChannelsParts.jsx";

const EMPTY_DRAFT = {
  kind: "",
  // show
  show: { item_id: 0, rating_key: "", title: "" },
  // collection
  collection_id: "",
  collection_title: "",
  // mood
  mood_source: "motif",
  motif: "",
  cluster_tag: "",
  // shape
  name: "",
  number: "",
  programming_mode: "sequential",
  media_scope: "both",
  genres: [],
  decade: "",
  theme: "",
  content_rating: "",
  ...DEFAULT_QUEUE_PAD_DRAFT,
};

function pickTitleFor(draft) {
  if (draft.kind === "show") return draft.show.title;
  if (draft.kind === "collection") return draft.collection_title;
  if (draft.kind === "mood") {
    if (draft.mood_source === "motif") return draft.motif;
    if (draft.mood_source === "taste_cluster") return draft.cluster_tag;
    return "Family night";
  }
  return "";
}

function pickReady(draft, startersSelected) {
  if (draft.kind === "show") return Boolean(draft.show.item_id > 0 || draft.show.rating_key);
  if (draft.kind === "collection") return Boolean(draft.collection_id);
  if (draft.kind === "mood") {
    if (draft.mood_source === "motif") return Boolean(draft.motif);
    if (draft.mood_source === "taste_cluster") return Boolean(draft.cluster_tag);
    return true;
  }
  if (draft.kind === "suggest") return startersSelected > 0;
  return false;
}

/**
 * The owner-facing Live studio: turn Live on, create a channel in three steps
 * (what's on it → make it yours → go on air), see what's playing, edit the
 * seasonal shelves, and tuck connection/health under Setup. The broadcast
 * engine underneath is never named here.
 */
export default function LiveChannelsStudio({
  settings,
  persistSettings,
  updateTunarrSettings,
  setActionFeedback,
  clearActionFeedback,
  liveChannelsStatus,
  setLiveChannelsStatus,
  livePreflight,
  setLivePreflight,
  liveCraftOptions,
  setLiveCraftOptions,
  liveAttach,
  liveBusy,
  setLiveBusy,
  liveEngineProgress,
  liveStarters,
  setLiveStarters,
  selectedStarters,
  setSelectedStarters,
  liveChannelsTab,
  setLiveChannelsTab,
  effectiveLiveTab,
  liveLaunched,
  handleLiveChannelsEnabled,
  renderLiveBlockAlert,
  renderPublishProgress,
  startBroadcastEngine,
  runPublishJob,
  formatPublishFeedback,
  openStationSettings,
  refillStation,
  stationSettings,
  advancedSetup,
}) {
  void liveChannelsTab;
  void updateTunarrSettings;
  const enabled = Boolean(settings?.features?.live_channels_enabled);
  const dockerOrchestration = Boolean(settings?.tunarr?.docker_orchestration);
  const liveJob = liveChannelsStatus?.job;
  const liveLocked = isLiveMutatingDisabled(liveJob, liveBusy);
  const channelCount = Number(liveChannelsStatus?.channel_count ?? 0);

  const [creating, setCreating] = useState(false);
  const [step, setStep] = useState(0);
  const [draft, setDraft] = useState(EMPTY_DRAFT);
  const [showQuery, setShowQuery] = useState("");
  const [showResults, setShowResults] = useState([]);
  const [showSearched, setShowSearched] = useState(false);
  const [showBusy, setShowBusy] = useState(false);
  const [collectionFilter, setCollectionFilter] = useState("");
  const [preview, setPreview] = useState(null);
  const [previewBusy, setPreviewBusy] = useState(false);
  const [launch, setLaunch] = useState(null); // { phase, error }
  const [setupOpen, setSetupOpen] = useState(false);
  const [lastLaunched, setLastLaunched] = useState("");

  const state = liveStationState({
    enabled,
    status: liveChannelsStatus,
    engineProgress: liveEngineProgress,
    launching: Boolean(launch && !launch.error),
  });

  // First-run: with no channels yet the creator is the page.
  const showCreator = enabled && (creating || (channelCount === 0 && liveChannelsStatus && !liveChannelsStatus.warming));
  const steps = createStepsFor(draft.kind);
  const stepId = steps[Math.min(step, steps.length - 1)]?.id || "pick";
  const startersSelected = Object.values(selectedStarters || {}).filter(Boolean).length;
  const collections = liveCraftOptions?.collections || [];
  const visibleCollections = filterLiveCollections(collections, {
    mediaScope: "both",
    filterQuery: collectionFilter,
    selectedId: draft.collection_id,
  });
  const infra = liveInfrastructureFacts(liveChannelsStatus);
  const plexPassConfirmed = Boolean(settings?.tunarr?.plex_pass_confirmed);

  // Reaching the launch step: run the readiness check once so the rows are honest.
  useEffect(() => {
    if (!showCreator || stepId !== "launch" || liveLaunched) return undefined;
    let cancelled = false;
    postLiveChannelsPreflight({ plex_pass_confirmed: plexPassConfirmed })
      .then((result) => {
        if (!cancelled) setLivePreflight(result);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showCreator, stepId, plexPassConfirmed, liveLaunched]);

  function patchDraft(patch) {
    setDraft((prev) => ({ ...prev, ...patch }));
    setPreview(null);
  }

  function openCreator() {
    setDraft({
      ...EMPTY_DRAFT,
      number: String(liveCraftOptions?.next_channel_number || 100),
    });
    setStep(0);
    setLaunch(null);
    setPreview(null);
    setCreating(true);
    setLiveChannelsTab("stations");
  }

  function closeCreator() {
    setCreating(false);
    setStep(0);
    setLaunch(null);
  }

  function chooseKind(kind) {
    setDraft((prev) => ({
      ...EMPTY_DRAFT,
      kind,
      number: prev.number || String(liveCraftOptions?.next_channel_number || 100),
      programming_mode: kind === "mood" ? "shuffle" : "sequential",
    }));
    setStep(0);
    if (kind === "suggest" && !liveStarters) proposeStarters();
  }

  async function searchShows() {
    const query = showQuery.trim();
    if (!query) return;
    setShowBusy(true);
    try {
      const payload = await queryLibrary({ query, media_type: "show", limit: 12 });
      setShowResults(payload?.items || []);
    } catch (error) {
      setShowResults([]);
      setActionFeedback("live-channels", "error", ownerLiveText(error.message), { block: "craft" });
    } finally {
      setShowSearched(true);
      setShowBusy(false);
    }
  }

  async function proposeStarters() {
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
      setActionFeedback("live-channels", "error", ownerLiveText(error.message), { block: "craft" });
    } finally {
      setLiveBusy(null);
    }
  }

  async function refreshStatus() {
    try {
      setLiveChannelsStatus(await getLiveChannelsStatus());
    } catch {
      /* best effort — the page keeps the last status */
    }
  }

  async function runPreview() {
    setPreviewBusy(true);
    try {
      setPreview(
        await previewLiveChannelsCraft({
          media_scope: draft.media_scope || "both",
          source: draft.kind === "collection" ? "collection" : draft.mood_source,
          collection_id: draft.kind === "collection" ? draft.collection_id : "",
          craft_filters: buildCraftFiltersPayload(draft),
        }),
      );
    } catch (error) {
      setPreview({ matched: 0, note: ownerLiveText(error.message) || "Couldn’t count titles." });
    } finally {
      setPreviewBusy(false);
    }
  }

  async function goOnAir() {
    clearActionFeedback("live-channels");
    const name = (draft.name || pickTitleFor(draft) || "").trim();
    try {
      if (!liveLaunched) {
        setLaunch({ phase: "check" });
        const pre = await postLiveChannelsPreflight({ plex_pass_confirmed: plexPassConfirmed });
        setLivePreflight(pre);
        const blockers = launchBlockers(pre);
        if (blockers.length) {
          setLaunch({ phase: "check", error: `${blockers[0].label}: ${blockers[0].message}` });
          setSetupOpen(true);
          return;
        }
        const engineUp = Boolean(liveChannelsStatus?.broadcast?.sidecar_up || liveEngineProgress?.ready);
        if (dockerOrchestration && !engineUp) {
          setLaunch({ phase: "engine" });
          await startBroadcastEngine();
          const next = await getLiveChannelsStatus();
          setLiveChannelsStatus(next);
          if (!next?.broadcast?.sidecar_up) {
            setLaunch({
              phase: "engine",
              error: "The broadcast didn’t come up. Check Setup, then try again.",
            });
            setSetupOpen(true);
            return;
          }
        }
      }

      setLaunch({ phase: "lineup" });
      let result;
      if (draft.kind === "suggest") {
        setLiveBusy("publish");
        try {
          const recipes = (liveStarters?.proposals || [])
            .filter((proposal) => selectedStarters[`${proposal.number}:${proposal.name}`])
            .map((proposal) => ({ ...proposal, queue_pad: queuePadPayload(draft) }));
          result = await publishLiveChannelsStarters({ recipes, fill_programming: true });
          const feedback = formatPublishFeedback(result);
          setActionFeedback("live-channels", feedback.type, ownerLiveText(feedback.summary), {
            block: "craft",
            details: (feedback.details || []).map(ownerLiveText),
          });
        } finally {
          setLiveBusy(null);
        }
      } else {
        const number = Number(draft.number);
        const common = {
          name,
          programming_mode: draft.programming_mode,
          queue_pad: queuePadPayload(draft),
        };
        const start = () => {
          if (draft.kind === "show") {
            return publishLiveChannelsFromShow({
              ...common,
              show_item_id: draft.show.item_id || 0,
              show_rating_key: draft.show.rating_key,
              show_title: draft.show.title,
              channel_number: Number.isFinite(number) ? number : 0,
            });
          }
          if (draft.kind === "collection") {
            return publishLiveChannelsFromCollection({
              ...common,
              collection_id: draft.collection_id,
              collection_title: draft.collection_title,
              channel_number: Number.isFinite(number) ? number : 0,
              media_scope: draft.media_scope || "both",
              craft_filters: buildCraftFiltersPayload(draft),
            });
          }
          return publishLiveChannelsChannel({
            ...common,
            number: Number.isFinite(number) ? number : 0,
            source: draft.mood_source,
            media_scope: draft.media_scope || "both",
            motif: draft.mood_source === "motif" ? draft.motif : "",
            cluster_tag: draft.mood_source === "taste_cluster" ? draft.cluster_tag : "",
            youth_safe: draft.mood_source === "youth",
            craft_filters: buildCraftFiltersPayload(draft),
            fill_programming: true,
          });
        };
        result = await runPublishJob(start, {
          busyKey: "craft",
          block: "craft",
          successFallback: `“${name}” is built.`,
        });
      }

      if (!publishSucceeded(result)) {
        setLaunch({ phase: "lineup", error: "The lineup didn’t finish. Details are above." });
        return;
      }

      setLaunch({ phase: "plex" });
      try {
        if (!liveAttach?.needs_lan_url) await postLiveChannelsPlexAttachGuide();
      } catch (error) {
        setActionFeedback(
          "live-channels",
          "error",
          `Your channel is built, but Plex didn’t pick it up yet: ${ownerLiveText(error.message)}`,
          { block: "craft" },
        );
      }
      await refreshStatus();
      try {
        setLiveCraftOptions(await getLiveChannelsCraftOptions());
      } catch {
        /* the next page load refreshes options */
      }
      setLastLaunched(name || "Your channel");
      setLaunch(null);
      setCreating(false);
      setStep(0);
      setLiveChannelsTab("stations");
    } catch (error) {
      setLaunch((prev) => ({ phase: prev?.phase || "check", error: ownerLiveText(error.message) }));
    }
  }

  async function resyncPlex(rebuild) {
    if (rebuild && !window.confirm(plexRebuildConfirmMessage())) return;
    setLiveBusy(rebuild ? "plex-repair" : "attach-guide");
    try {
      const result = rebuild ? await postLiveChannelsPlexRepair() : await postLiveChannelsPlexAttachGuide();
      const mapped = result.expected != null ? ` Plex sees ${result.mapped ?? 0} of ${result.expected}.` : "";
      setActionFeedback(
        "live-channels",
        "success",
        `${ownerLiveText(result.message) || (rebuild ? "Plex lineup rebuilt." : "Plex lineup refreshed.")}${mapped}`,
        { block: "health" },
      );
      await refreshStatus();
    } catch (error) {
      setActionFeedback("live-channels", "error", ownerLiveText(error.message), { block: "health" });
    } finally {
      setLiveBusy(null);
    }
  }

  // ---------------------------------------------------------------- Off
  if (!enabled) {
    return (
      <section
        className="config-section live-channels-section live-studio"
        data-testid="live-channels-settings"
        data-enabled="false"
      >
        <div className="live-studio-hero" data-testid="live-channels-enabled-toggle">
          <p className="eyebrow">Live</p>
          <h2>Put your library on the air</h2>
          <p className="live-studio-lede">
            Turn your shows and movies into always-on channels. They appear in Projectionist Live and in
            Plex Live TV, right beside any antenna channels you already have. You pick what’s on;
            Projectionist runs the lineup.
          </p>
          <ul className="live-studio-promises">
            <li>Channels built from a show, a collection, or a mood</li>
            <li>Nothing to schedule — the lineup rolls on its own</li>
            <li>Turn it off any time; your channels are kept</li>
          </ul>
          <div className="wizard-actions">
            <button
              type="button"
              className="primary"
              data-testid="live-channels-enable-cta"
              disabled={liveLocked || liveBusy === "enable" || liveBusy === "disable"}
              aria-busy={liveBusy === "enable"}
              onClick={() => handleLiveChannelsEnabled(true)}
            >
              {liveBusy === "enable" ? "Turning on…" : "Turn on Live"}
            </button>
          </div>
          {renderLiveBlockAlert("hero")}
        </div>
      </section>
    );
  }

  // ----------------------------------------------------------------- On
  const showBoard = !liveLaunched || effectiveLiveTab === "stations";
  const showSetup = liveLaunched && effectiveLiveTab === "setup";
  const launchBusy = Boolean(launch && !launch.error);

  return (
    <section
      className="config-section live-channels-section live-studio"
      data-testid="live-channels-settings"
      data-enabled="true"
      data-live-state={state.key}
    >
      <div className="live-studio-banner" data-testid="live-channels-enabled-toggle" role="status" aria-live="polite">
        <div className="live-studio-banner-copy">
          <p className="eyebrow">Live</p>
          <h2 data-testid="live-studio-state-title">{state.title}</h2>
          <p className="live-studio-lede" data-tone={state.tone}>
            {state.detail}
          </p>
          {lastLaunched ? (
            <p className="live-studio-fresh" data-testid="live-studio-just-launched">
              “{lastLaunched}” is on the lineup.
            </p>
          ) : null}
        </div>
        <div className="live-studio-banner-actions">
          {!showCreator ? (
            <button
              type="button"
              className="primary"
              data-testid="live-new-channel"
              disabled={liveLocked || launchBusy}
              onClick={openCreator}
            >
              New channel
            </button>
          ) : null}
          <button
            type="button"
            className="ghost"
            data-testid="live-channels-disable-cta"
            disabled={liveLocked || liveBusy === "enable" || liveBusy === "disable"}
            aria-busy={liveBusy === "disable"}
            onClick={() => handleLiveChannelsEnabled(false)}
          >
            {liveBusy === "disable" ? "Turning off…" : "Turn off"}
          </button>
        </div>
      </div>
      {renderLiveBlockAlert("hero")}
      <LiveJobRail job={liveJob} />

      {liveLaunched ? (
        <div className="live-channels-tabs" role="tablist" aria-label="Live sections" data-testid="live-channels-tabs">
          <button
            type="button"
            role="tab"
            aria-selected={effectiveLiveTab === "stations"}
            className={effectiveLiveTab === "stations" ? "live-channels-tab is-active" : "live-channels-tab"}
            data-testid="live-channels-tab-stations"
            onClick={() => setLiveChannelsTab("stations")}
          >
            Channels
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={effectiveLiveTab === "setup"}
            className={effectiveLiveTab === "setup" ? "live-channels-tab is-active" : "live-channels-tab"}
            data-testid="live-channels-tab-installation"
            onClick={() => setLiveChannelsTab("setup")}
          >
            Setup
          </button>
        </div>
      ) : null}

      {showBoard ? (
        <div className="live-studio-stack">
          {showCreator ? (
            <div className="live-studio-card live-create" data-testid="live-create">
              <header className="live-studio-card-head">
                <div>
                  <h3>{channelCount === 0 ? "Create your first channel" : "New channel"}</h3>
                  <ol className="live-create-steps" data-testid="live-create-steps">
                    {steps.map((item, index) => (
                      <li
                        key={item.id}
                        className={index === step ? "is-current" : index < step ? "is-done" : ""}
                        aria-current={index === step ? "step" : undefined}
                      >
                        <span className="live-create-step-num">{index + 1}</span> {item.label}
                      </li>
                    ))}
                  </ol>
                </div>
                {channelCount > 0 ? (
                  <button type="button" className="ghost" disabled={launchBusy} onClick={closeCreator} data-testid="live-create-cancel">
                    Cancel
                  </button>
                ) : null}
              </header>

              {stepId === "pick" ? (
                <div className="live-create-body" data-testid="live-create-pick">
                  <div className="live-kind-grid" role="radiogroup" aria-label="What’s on this channel">
                    {CHANNEL_KINDS.map((kind) => (
                      <button
                        type="button"
                        key={kind.id}
                        role="radio"
                        aria-checked={draft.kind === kind.id}
                        className={draft.kind === kind.id ? "live-kind is-selected" : "live-kind"}
                        data-testid={`live-create-kind-${kind.id}`}
                        onClick={() => chooseKind(kind.id)}
                      >
                        <strong>{kind.title}</strong>
                        <span>{kind.blurb}</span>
                      </button>
                    ))}
                  </div>

                  {draft.kind === "show" ? (
                    <div className="live-create-detail" data-testid="live-create-show">
                      <form
                        className="live-create-search"
                        onSubmit={(event) => {
                          event.preventDefault();
                          searchShows();
                        }}
                      >
                        <label>
                          <span>Find a show</span>
                          <input
                            type="search"
                            value={showQuery}
                            placeholder="e.g. Deep Space Nine"
                            data-testid="live-create-show-query"
                            onChange={(event) => setShowQuery(event.target.value)}
                          />
                        </label>
                        <button type="submit" className="ghost" disabled={showBusy || !showQuery.trim()} data-testid="live-create-show-search">
                          {showBusy ? "Searching…" : "Search"}
                        </button>
                      </form>
                      {draft.show.title ? (
                        <p className="live-studio-fresh" data-testid="live-create-show-picked">
                          Picked: {draft.show.title}
                        </p>
                      ) : null}
                      {showSearched && showResults.length === 0 ? (
                        <p className="live-studio-hint">No shows in your library match that.</p>
                      ) : null}
                      <ul className="live-pick-list">
                        {showResults.map((item) => (
                          <li key={item.id || item.rating_key}>
                            <button
                              type="button"
                              className={draft.show.item_id === item.id ? "live-pick is-selected" : "live-pick"}
                              data-testid={`live-create-show-pick-${item.id}`}
                              onClick={() =>
                                patchDraft({
                                  show: {
                                    item_id: Number(item.id) || 0,
                                    rating_key: String(item.rating_key || ""),
                                    title: item.title || "",
                                  },
                                  name: draft.name || item.title || "",
                                })
                              }
                            >
                              {item.title}
                              {item.year ? ` (${item.year})` : ""}
                            </button>
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null}

                  {draft.kind === "collection" ? (
                    <div className="live-create-detail" data-testid="live-create-collection">
                      <label>
                        <span>Narrow the list</span>
                        <input
                          type="search"
                          value={collectionFilter}
                          placeholder="Search collections and lists"
                          onChange={(event) => setCollectionFilter(event.target.value)}
                        />
                      </label>
                      <label>
                        <span>Collection or list</span>
                        <select
                          data-testid="live-create-collection-select"
                          value={draft.collection_id}
                          onChange={(event) => {
                            const match = collections.find((row) => row.id === event.target.value);
                            patchDraft({
                              collection_id: event.target.value,
                              collection_title: match?.title || "",
                              name: draft.name || match?.title || "",
                            });
                          }}
                        >
                          <option value="">Choose one…</option>
                          {visibleCollections.map((row) => (
                            <option key={row.id} value={row.id}>
                              {row.title}
                            </option>
                          ))}
                        </select>
                      </label>
                      {collections.length === 0 ? (
                        <p className="live-studio-hint" data-testid="live-create-collections-empty">
                          {ownerLiveText(liveCraftOptions?.collections_empty_hint) ||
                            "No collections or lists yet. Make one in Collections, or pick a show or a mood instead."}
                        </p>
                      ) : null}
                    </div>
                  ) : null}

                  {draft.kind === "mood" ? (
                    <div className="live-create-detail" data-testid="live-create-mood">
                      <div className="live-chip-row" role="radiogroup" aria-label="Kind of mood">
                        {MOOD_SOURCES.map((source) => (
                          <button
                            type="button"
                            key={source.id}
                            role="radio"
                            aria-checked={draft.mood_source === source.id}
                            className={draft.mood_source === source.id ? "live-chip is-selected" : "live-chip"}
                            data-testid={`live-create-mood-${source.id}`}
                            onClick={() => patchDraft({ mood_source: source.id })}
                          >
                            {source.label}
                          </button>
                        ))}
                      </div>
                      {draft.mood_source === "motif" ? (
                        <label>
                          <span>Story mood</span>
                          <select
                            data-testid="live-create-motif"
                            value={draft.motif}
                            onChange={(event) =>
                              patchDraft({ motif: event.target.value, name: draft.name || event.target.value })
                            }
                          >
                            <option value="">Choose a mood…</option>
                            {(liveCraftOptions?.motifs || []).map((motif) => (
                              <option key={motif.value} value={motif.value}>
                                {motif.label}
                                {motif.count ? ` (${motif.count})` : ""}
                              </option>
                            ))}
                          </select>
                        </label>
                      ) : null}
                      {draft.mood_source === "taste_cluster" ? (
                        <label>
                          <span>Taste</span>
                          <select
                            data-testid="live-create-cluster"
                            value={draft.cluster_tag}
                            onChange={(event) =>
                              patchDraft({ cluster_tag: event.target.value, name: draft.name || event.target.value })
                            }
                          >
                            <option value="">Choose a taste…</option>
                            {(liveCraftOptions?.taste_clusters || []).map((cluster) => (
                              <option key={cluster.cluster_tag} value={cluster.cluster_tag}>
                                {cluster.label}
                              </option>
                            ))}
                          </select>
                        </label>
                      ) : null}
                      {draft.mood_source === "youth" ? (
                        <p className="live-studio-hint">
                          Only titles rated for younger viewers, so the channel is safe to leave on.
                        </p>
                      ) : null}
                    </div>
                  ) : null}

                  {draft.kind === "suggest" ? (
                    <div className="live-create-detail" data-testid="live-create-suggest">
                      {liveBusy === "starters" ? <p className="live-studio-hint">Looking through your library…</p> : null}
                      {liveStarters?.proposals?.length ? (
                        <ul className="live-suggest-list" data-testid="live-channels-starter-list">
                          {liveStarters.proposals.map((proposal) => {
                            const key = `${proposal.number}:${proposal.name}`;
                            return (
                              <li key={key}>
                                <label className="live-studio-check">
                                  <input
                                    type="checkbox"
                                    checked={Boolean(selectedStarters[key])}
                                    onChange={(event) =>
                                      setSelectedStarters((prev) => ({ ...prev, [key]: event.target.checked }))
                                    }
                                  />
                                  <span>
                                    <strong>{proposal.name}</strong>
                                    {proposal.summary ? ` — ${ownerLiveText(proposal.summary)}` : ""}
                                  </span>
                                </label>
                              </li>
                            );
                          })}
                        </ul>
                      ) : liveBusy !== "starters" ? (
                        <p className="live-studio-hint" data-testid="live-channels-starters-empty">
                          Nothing to suggest yet — sync your library, or pick a show or a mood.
                        </p>
                      ) : null}
                      <QueuePadControl value={draft} onChange={(next) => patchDraft(next)} testIdPrefix="live-create-queue-pad" />
                    </div>
                  ) : null}

                  <div className="live-create-actions">
                    <button
                      type="button"
                      className="primary"
                      data-testid="live-create-next"
                      disabled={!pickReady(draft, startersSelected)}
                      onClick={() => setStep(1)}
                    >
                      Next
                    </button>
                  </div>
                </div>
              ) : null}

              {stepId === "shape" ? (
                <div className="live-create-body" data-testid="live-create-shape">
                  <div className="live-create-fields">
                    <label>
                      <span>Channel name</span>
                      <input
                        type="text"
                        maxLength={48}
                        value={draft.name}
                        placeholder={pickTitleFor(draft) || "e.g. Midnight Mystery"}
                        data-testid="live-create-name"
                        onChange={(event) => patchDraft({ name: event.target.value })}
                      />
                    </label>
                    <label>
                      <span>Channel number</span>
                      <input
                        type="number"
                        min={1}
                        value={draft.number}
                        data-testid="live-create-number"
                        onChange={(event) => patchDraft({ number: event.target.value })}
                      />
                    </label>
                    <label>
                      <span>Play order</span>
                      <select
                        value={draft.programming_mode}
                        data-testid="live-create-order"
                        onChange={(event) => patchDraft({ programming_mode: event.target.value })}
                      >
                        <option value="sequential">In order</option>
                        <option value="shuffle">Shuffled</option>
                      </select>
                    </label>
                    {draft.kind !== "show" ? (
                      <label>
                        <span>Include</span>
                        <select
                          value={draft.media_scope}
                          data-testid="live-create-scope"
                          onChange={(event) => patchDraft({ media_scope: event.target.value })}
                        >
                          <option value="both">Movies and TV</option>
                          <option value="tv">TV only</option>
                          <option value="movies">Movies only</option>
                        </select>
                      </label>
                    ) : null}
                  </div>

                  <QueuePadControl value={draft} onChange={(next) => patchDraft(next)} testIdPrefix="live-create-queue-pad" />

                  {draft.kind !== "show" ? (
                    <details className="live-studio-details" data-testid="live-create-finetune">
                      <summary>Fine-tune what qualifies</summary>
                      <div className="live-create-fields">
                        <label>
                          <span>Genre</span>
                          <select
                            value={draft.genres?.[0] || ""}
                            onChange={(event) => patchDraft({ genres: event.target.value ? [event.target.value] : [] })}
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
                          <span>Decade</span>
                          <select value={String(draft.decade ?? "")} onChange={(event) => patchDraft({ decade: event.target.value })}>
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
                          <span>Rating</span>
                          <select value={draft.content_rating || ""} onChange={(event) => patchDraft({ content_rating: event.target.value })}>
                            <option value="">Any rating</option>
                            {(liveCraftOptions?.filter_options?.content_ratings || []).map((row) => (
                              <option key={row.value} value={row.value}>
                                {row.label}
                                {row.count ? ` (${row.count})` : ""}
                              </option>
                            ))}
                          </select>
                        </label>
                      </div>
                      <p className="live-studio-hint">
                        Titles in your “{liveCraftOptions?.exclusion_collection_name || "NoLive"}” Plex
                        collection are always skipped.
                      </p>
                      <button type="button" className="ghost" disabled={previewBusy} onClick={runPreview} data-testid="live-create-preview">
                        {previewBusy ? "Counting…" : "How many titles match?"}
                      </button>
                      {preview ? (
                        <p className="live-studio-hint" data-testid="live-create-preview-result">
                          {ownerLiveText(craftSoftCapHonestyNote(preview)) ||
                            ownerLiveText(preview.note) ||
                            `${preview.matched ?? 0} titles match.`}
                        </p>
                      ) : null}
                    </details>
                  ) : null}

                  <div className="live-create-actions">
                    <button type="button" className="ghost" onClick={() => setStep(0)}>
                      Back
                    </button>
                    <button
                      type="button"
                      className="primary"
                      data-testid="live-create-next"
                      disabled={!String(draft.name || pickTitleFor(draft)).trim()}
                      onClick={() => setStep(2)}
                    >
                      Next
                    </button>
                  </div>
                </div>
              ) : null}

              {stepId === "launch" ? (
                <div className="live-create-body" data-testid="live-create-launch">
                  <p className="live-create-summary" data-testid="live-create-summary">
                    {draft.kind === "suggest"
                      ? `${startersSelected} suggested channel${startersSelected === 1 ? "" : "s"}`
                      : channelSummaryLine({
                          kind: draft.kind,
                          name: draft.name,
                          number: draft.number,
                          programmingMode: draft.programming_mode,
                          mediaScope: draft.media_scope,
                          pickTitle: pickTitleFor(draft),
                        })}
                  </p>

                  {!liveLaunched ? (
                    <div className="live-ready" data-testid="live-create-ready">
                      <h4>Ready to go on air?</h4>
                      {launchReadinessRows(livePreflight).length ? (
                        <ul className="live-channels-check-list" data-testid="live-channels-preflight-list">
                          {launchReadinessRows(livePreflight).map((row) => (
                            <LiveStatusCheck key={row.id} ok={row.ok} soft={row.soft}>
                              {row.label}
                              {row.ok || !row.message ? "" : ` — ${row.message}`}
                            </LiveStatusCheck>
                          ))}
                        </ul>
                      ) : (
                        <p className="live-studio-hint">Checking your setup…</p>
                      )}
                      <label className="live-studio-check" data-testid="live-channels-plex-pass-confirm">
                        <input
                          type="checkbox"
                          checked={plexPassConfirmed}
                          onChange={(event) => {
                            const confirmed = event.target.checked;
                            updateTunarrSettings({ plex_pass_confirmed: confirmed });
                            persistSettings({
                              tunarr: { ...(settings.tunarr || {}), plex_pass_confirmed: confirmed },
                            }).catch((error) =>
                              setActionFeedback("live-channels", "error", ownerLiveText(error.message), { block: "craft" }),
                            );
                          }}
                        />
                        <span>
                          I have an active Plex Pass (Plex needs it for Live TV). Projectionist can’t check this
                          for you.
                        </span>
                      </label>
                    </div>
                  ) : (
                    <p className="live-studio-hint">Your broadcast is already running — this channel joins the lineup.</p>
                  )}

                  {launch ? (
                    <ol className="live-launch-phases" data-testid="live-launch-phases">
                      {LAUNCH_PHASES.filter((phase) => liveLaunched ? phase.id !== "check" && phase.id !== "engine" : true).map((phase) => {
                        const order = LAUNCH_PHASES.map((p) => p.id);
                        const at = order.indexOf(launch.phase);
                        const mine = order.indexOf(phase.id);
                        const cls = mine < at ? "is-done" : mine === at ? (launch.error ? "is-failed" : "is-current") : "";
                        return (
                          <li key={phase.id} className={cls}>
                            {phase.label}
                          </li>
                        );
                      })}
                    </ol>
                  ) : null}
                  {launch?.error ? (
                    <InlineAlert type="error" message={launch.error} testId="live-create-error" />
                  ) : null}
                  {renderPublishProgress("craft")}
                  {renderLiveBlockAlert("craft")}

                  <div className="live-create-actions">
                    <button type="button" className="ghost" disabled={launchBusy} onClick={() => setStep(steps.length - 2)}>
                      Back
                    </button>
                    <button
                      type="button"
                      className="primary live-go-on-air"
                      data-testid="live-go-on-air"
                      disabled={liveLocked || launchBusy || (draft.kind === "suggest" && startersSelected === 0)}
                      aria-busy={launchBusy}
                      onClick={goOnAir}
                    >
                      {launchBusy ? "Going on air…" : liveLaunched ? "Add to the lineup" : "Go on air"}
                    </button>
                  </div>
                </div>
              ) : null}
            </div>
          ) : null}

          {channelCount > 0 ? (
            <OwnerNowPlayingBreakdown
              status={liveChannelsStatus}
              compact
              digInExtras
              actionsDisabled={liveLocked}
              refillBusyId={String(liveBusy || "").startsWith("refill-") ? String(liveBusy).slice("refill-".length) : ""}
              onRefreshStatus={async () => {
                setLiveBusy("status");
                try {
                  setLiveChannelsStatus(await getLiveChannelsStatus());
                } finally {
                  setLiveBusy(null);
                }
              }}
              onOpenStationSettings={openStationSettings}
              onRefill={refillStation}
            />
          ) : null}

          {stationSettings}

          <SeasonalShelves />

          {!liveLaunched ? (
            <details
              className="live-studio-details live-studio-setup-fold"
              data-testid="live-setup-details"
              open={setupOpen}
              onToggle={(event) => setSetupOpen(event.currentTarget.open)}
            >
              <summary>Connection &amp; health</summary>
              {advancedSetup}
            </details>
          ) : null}
        </div>
      ) : null}

      {showSetup ? (
        <div className="live-studio-stack" data-testid="live-studio-setup">
          <div className="live-studio-card" data-testid="live-channels-health-strip">
            <header className="live-studio-card-head">
              <div>
                <h3>Health</h3>
                <p className="live-studio-hint" data-testid="live-channels-health-summary">
                  {state.detail}
                </p>
              </div>
              <div className="live-studio-card-actions">
                <button
                  type="button"
                  className="primary"
                  data-testid="live-channels-strip-refresh"
                  disabled={liveLocked || Boolean(liveAttach?.needs_lan_url)}
                  onClick={() => resyncPlex(false)}
                >
                  {liveBusy === "attach-guide" ? "Refreshing…" : "Refresh Plex lineup"}
                </button>
                <button
                  type="button"
                  className="ghost"
                  data-testid="live-channels-strip-rebuild"
                  disabled={liveLocked || Boolean(liveAttach?.needs_lan_url)}
                  onClick={() => resyncPlex(true)}
                >
                  {liveBusy === "plex-repair" ? "Rebuilding…" : "Rebuild in Plex"}
                </button>
                <button
                  type="button"
                  className="ghost"
                  data-testid="live-channels-refresh-status"
                  disabled={liveBusy === "status"}
                  onClick={() => {
                    setLiveBusy("status");
                    getLiveChannelsStatus()
                      .then(setLiveChannelsStatus)
                      .catch((error) =>
                        setActionFeedback("live-channels", "error", ownerLiveText(error.message), { block: "health" }),
                      )
                      .finally(() => setLiveBusy(null));
                  }}
                >
                  Refresh status
                </button>
              </div>
            </header>
            <ul className="live-channels-check-list" data-testid="live-channels-infra-facts">
              <LiveStatusCheck ok={infra.engineUp} testId="live-channels-infra-engine">
                {infra.engineLabel}
              </LiveStatusCheck>
              <LiveStatusCheck ok={infra.guideOk} soft={!infra.guideOk} testId="live-channels-infra-guide">
                {infra.guideLabel}
              </LiveStatusCheck>
              <LiveStatusCheck ok={infra.tunerAlive} soft={!infra.tunerAlive} testId="live-channels-infra-tuner">
                {infra.tunerLabel}
              </LiveStatusCheck>
              <LiveStatusCheck ok soft testId="live-channels-infra-warm">
                {infra.streamWarmLabel}
              </LiveStatusCheck>
            </ul>
            {infra.xmltvError ? <p className="live-studio-hint">Guide problem: {ownerLiveText(infra.xmltvError)}</p> : null}
            {renderLiveBlockAlert("health")}
            {liveChannelsStatus?.last_error ? (
              <InlineAlert type="error" message={ownerLiveText(liveChannelsStatus.last_error)} testId="live-channels-last-error" />
            ) : null}
          </div>

          <details className="live-studio-details" data-testid="live-studio-advanced">
            <summary>Advanced</summary>
            {advancedSetup}
          </details>
        </div>
      ) : null}
    </section>
  );
}
