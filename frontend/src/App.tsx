import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { AuthUser, ChatMessage, Features, Job, JsParam, LibraryItem, Persona } from "./api/types";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  api,
  addWatchlistPin,
  dismissReviewPrompt,
  getAuthMe,
  getFeatures,
  listJobs,
  listNotifications,
  listReviewPrompts,
  listReviews,
  listWatchlist,
  removeWatchlistPin,
  runWatchlistSync,
  saveReview,
} from "./api/client";
import { resolveAgentPulse } from "./lib/agentPulse.js";
import { requestPathFromFeatures } from "./lib/addActions.js";
import { blendAmbientAccent } from "./lib/ambientAccent.js";
import { extractSpeakableText } from "./lib/voiceSpeech.js";
import {
  applyUiFontSize,
  applyUiTheme,
  loadStoredUiTheme,
  normalizeUiTheme,
} from "./lib/uiPrefs.js";
import {
  CHAT_LAUNCHER_CHIPS,
} from "./lib/chatLauncherChips.js";
import { holdableShelfPages, pickResumeThread, resumeChipFromThread } from "./lib/chatLayout.js";
import {
  isWatchlistPanelRequest,
  ROUTES,
  stripWatchlistPanelParam,
} from "./lib/backNav.js";
import { buildWatchlistLookup } from "./lib/watchlistKeys.js";
import { applyOptimisticPinToggle, upsertPin } from "./lib/optimisticWatchlist.js";
import { startVisibleBusyPoll, syncToastIsOpen } from "./lib/visibleBusyPoll.js";
import { resolveDockDropTarget } from "./lib/easterEggs.js";
import { arrServiceConnected, isNightOwlHour } from "./lib/chatSession.js";
import ChatWorkspace from "./components/ChatWorkspace";
import { useBulkActionProgress } from "./components/BulkActionProgress";
import { useAuthGate } from "./components/UserMenu";
import { reviewPromptBlock } from "./components/ReviewPromptCard";
import useChatScroll from "./hooks/useChatScroll";
import useChatSession from "./hooks/useChatSession";
import useKeyboardShortcuts from "./hooks/useKeyboardShortcuts";
import useVoiceMode from "./hooks/useVoiceMode.js";

const SIDEBAR_RAIL_KEY = "projectionist.sidebar.rail";

export default function App() {
  const {
    authReady,
    multiUserEnabled,
    isOwner,
    role: userRole,
    isYouth,
    liveChannelsReady,
    seerrEnabled,
  } = useAuthGate();
  const { start: startBulkProgress, update: updateBulkProgress, finish: finishBulkProgress } = useBulkActionProgress();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [uiTheme, setUiTheme] = useState(() => loadStoredUiTheme());
  const [appNavOpen, setAppNavOpen] = useState(false);
  const [stats, setStats] = useState<JsParam>(null);
  const [setup, setSetup] = useState<JsParam>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [persona, setPersona] = useState<Persona | null>(null);
  const [features, setFeatures] = useState<Features | null>(null);
  const [keyboardHelpOpen, setKeyboardHelpOpen] = useState(false);
  const [watchlistPins, setWatchlistPins] = useState<JsParam[]>([]);
  const [recommendItem, setRecommendItem] = useState<JsParam>(null);
  const [inboxUnreadCount, setInboxUnreadCount] = useState(0);
  const [reviewPrompts, setReviewPrompts] = useState<JsParam[]>([]);
  const [reviewLookup, setReviewLookup] = useState<Record<string, JsParam>>({});
  const [nightOwl, setNightOwl] = useState(isNightOwlHour);
  const [anniversaries, setAnniversaries] = useState<JsParam[]>([]);
  const [libraryGlance, setLibraryGlance] = useState<JsParam>(null);
  const [glanceShown, setGlanceShown] = useState(false);
  const [authUser, setAuthUser] = useState<AuthUser | null>(null);
  const jobsRunningRef = useRef(false);
  const composerRef = useRef<HTMLElement | null>(null);
  const konamiTrackerRef = useRef<JsParam>(null);
  const speakAssistantMessageRef = useRef<(message: ChatMessage) => void>(() => {});
  const stopVoiceListeningRef = useRef<() => void>(() => {});
  const stopTtsRef = useRef<() => void>(() => {});
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    try {
      return sessionStorage.getItem(SIDEBAR_RAIL_KEY) === "true";
    } catch {
      return false;
    }
  });
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  const reviewUserContext = useMemo(
    () => authUser || features?.user || null,
    [authUser, features?.user],
  );

  const refreshJobs = useCallback(() => {
    listJobs().then(setJobs).catch(console.error);
  }, []);

  const chat = useChatSession({
    persona,
    features,
    isYouth,
    authReady,
    refreshJobs,
    setStats,
    speakAssistantMessageRef,
    stopVoiceListeningRef,
    stopTtsRef,
    composerRef,
    searchParams,
    setSearchParams,
    navigate,
    startBulkProgress,
    updateBulkProgress,
    finishBulkProgress,
    reviewUserContext,
    setMobileNavOpen,
  });

  const {
    messages,
    setMessages,
    messageFeedback,
    threads,
    activeSessionId,
    threadsReady,
    turnstyleResults,
    setTurnstyleResults,
    pendingAdd,
    pendingBulk,
    pendingTokens,
    addInProgress,
    addProgress,
    addFeedback,
    input,
    setInput,
    loading,
    chatError,
    activeContext,
    typingLabel,
    agentActivityLog,
    activityPanelOpen,
    setActivityPanelOpen,
    composerPlaceholder,
    quickPickLoading,
    surpriseMood,
    undoToast,
    personas,
    activePersonaId,
    setActivePersonaId,
    defaultPersonaId,
    slashPaletteIndex,
    setSlashPaletteIndex,
    slashPaletteItems,
    showSlashPalette,
    savedShelf,
    switchThread,
    handleCreateThread,
    handleDeleteThread,
    handleUndoDeleteThread,
    commitPendingDelete,
    handleMessageFeedbackChange,
    handleSaveToLibrary,
    handleCreatePersona,
    handleUpdatePersona,
    handleDeletePersona,
    handleSetDefaultPersona,
    handleQuickPick,
    handleOpenAgentResultsGrid,
    handleContextChip,
    handleSlashPaletteSelect,
    sendMessage,
    handleAdd,
    handleConfirmAllItems,
    handleConfirmAllTokens,
    confirmActiveAction,
    cancelActiveAction,
    dismissAddFeedback,
  } = chat;

  useEffect(() => {
    if (!isWatchlistPanelRequest(searchParams)) return;
    setSearchParams(stripWatchlistPanelParam(searchParams), { replace: true });
    navigate(ROUTES.watchlist);
  }, [searchParams, setSearchParams, navigate]);

  const {
    listening: voiceListening,
    speaking: voiceSpeaking,
    ttsMuted,
    voiceStatus,
    showMic,
    toggleListening,
    stopListening: stopVoiceListening,
    speakReply,
    stopTts,
    muteTts,
    unmuteTts,
  } = useVoiceMode({
    getComposerText: () => input,
    setComposerText: setInput,
  });

  const speakAssistantMessage = useCallback(
    (message: ChatMessage) => {
      speakReply(extractSpeakableText(message));
    },
    [speakReply]
  );
  useEffect(() => {
    speakAssistantMessageRef.current = speakAssistantMessage;
    stopVoiceListeningRef.current = stopVoiceListening;
    stopTtsRef.current = stopTts;
  }, [speakAssistantMessage, stopVoiceListening, stopTts]);

  const { scrollRef, showNewReplyChip, scrollToLatestTurn } = useChatScroll({
    messages,
    loading,
    sessionId: activeSessionId,
  });

  const refreshReviewData = useCallback(async () => {
    try {
      const [reviewsData, promptsData] = await Promise.all([listReviews({ limit: 200 }), listReviewPrompts(5)]);
      const lookup: Record<string, JsParam> = {};
      for (const review of reviewsData.items || []) {
        if (review.rating_key) {
          lookup[review.rating_key] = review.stars;
        }
        if (review.tmdb_id) {
          lookup[`${review.media_type}:${review.tmdb_id}`] = review.stars;
        }
      }
      setReviewLookup(lookup);
      setReviewPrompts(promptsData.items || []);
    } catch (error) {
      console.error(error);
    }
  }, []);

  const refreshWatchlist = useCallback(() => {
    runWatchlistSync({ direction: "pull" })
      .catch(() => {})
      .finally(() => {
        listWatchlist()
          .then((data) => setWatchlistPins(data.items || []))
          .catch(console.error);
      });
  }, []);

  const refreshRecommendations = useCallback(() => {
    listNotifications({ unread_only: true, limit: 20 })
      .then((data) => {
        setInboxUnreadCount(Number(data.unread_count) || (data.items || []).length);
      })
      .catch(() => {
        setInboxUnreadCount(0);
      });
  }, []);

  useKeyboardShortcuts({
    composerRef,
    onNewThread: handleCreateThread,
    onCloseOverlay: () => {
      if (mobileNavOpen) {
        setMobileNavOpen(false);
        return;
      }
      setTurnstyleResults(null);
    },
    onShowHelp: () => setKeyboardHelpOpen(true),
    overlayOpen: Boolean(turnstyleResults) || mobileNavOpen,
  });

  function toggleSidebarRail() {
    setSidebarCollapsed((collapsed) => {
      const next = !collapsed;
      try {
        sessionStorage.setItem(SIDEBAR_RAIL_KEY, String(next));
      } catch {
        // sessionStorage unavailable
      }
      return next;
    });
  }

  useEffect(() => {
    Promise.all([
      api("/setup/status").then(setSetup).catch(() => setSetup(null)),
      api("/library/stats").then(setStats),
      api("/persona").then(setPersona).catch(console.error),
      getFeatures().then(setFeatures).catch(console.error),
      refreshReviewData(),
    ]).catch(console.error);
    api("/library/anniversaries").then((res) => setAnniversaries(res?.items || [])).catch(() => {});
    api("/system-config").then((cfg) => {
      if (cfg?.library_glance_shown === "true") setGlanceShown(true);
    }).catch(() => {});
    refreshJobs();
    refreshWatchlist();
    refreshRecommendations();
    applyUiTheme(loadStoredUiTheme());
    getAuthMe()
      .then((payload) => {
        if (payload?.user) setAuthUser(payload.user);
        if (payload?.user?.ui_font_size) {
          applyUiFontSize(payload.user.ui_font_size);
        }
        if (payload?.user?.ui_theme) {
          const nextTheme = normalizeUiTheme(payload.user.ui_theme);
          setUiTheme(nextTheme);
          applyUiTheme(nextTheme);
        }
      })
      .catch(() => {});
    const nightInterval = setInterval(() => setNightOwl(isNightOwlHour()), 60_000);
    return () => {
      clearInterval(nightInterval);
    };
  }, [
    refreshJobs,
    refreshRecommendations,
    refreshReviewData,
    refreshWatchlist,
  ]);

  useEffect(() => {
    if (uiTheme !== "system" || typeof window === "undefined" || !window.matchMedia) return undefined;
    const mq = window.matchMedia("(prefers-color-scheme: light)");
    const onChange = () => applyUiTheme("system");
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [uiTheme]);

  useEffect(() => {
    const running = jobs.some((job) => job.status === "running" || job.status === "queued");
    if (jobsRunningRef.current && !running) {
      refreshReviewData();
      if (!glanceShown) {
        api("/library/overview")
          .then((data) => {
            if (data?.total > 0) {
              setLibraryGlance(data);
            }
          })
          .catch(() => {});
      }
    }
    jobsRunningRef.current = running;
  }, [jobs, refreshReviewData, glanceShown]);

  const chatSyncToastOpen = syncToastIsOpen(jobs);
  useEffect(() => {
    if (!chatSyncToastOpen) return undefined;
    return startVisibleBusyPoll(refreshJobs, { isBusy: () => true });
  }, [chatSyncToastOpen, refreshJobs]);

  function handleDismissGlance() {
    setLibraryGlance(null);
    setGlanceShown(true);
    api("/system-config", {
      method: "PUT",
      body: JSON.stringify({ values: { library_glance_shown: "true" } }),
    }).catch(() => {});
  }

  async function handleDismiss(item: LibraryItem) {
    await api("/preferences", {
      method: "POST",
      body: JSON.stringify({
        signal_type: "dismiss",
        text: `Not interested in ${item.title}`,
        tmdb_id: item.tmdb_id,
        tvdb_id: item.tvdb_id,
        media_type: item.media_type,
      }),
    });
  }

  async function handleToggleWatchlistPin(item: LibraryItem, pinRecord: JsParam) {
    const adding = !pinRecord?.id;
    const { next, rollback } = applyOptimisticPinToggle(watchlistPins, {
      item,
      pinRecord,
      adding,
    });
    setWatchlistPins(next);
    try {
      if (pinRecord?.id) {
        await removeWatchlistPin(pinRecord.id);
      } else {
        const saved = await addWatchlistPin({
          tmdb_id: item.tmdb_id,
          tvdb_id: item.tvdb_id,
          media_type: item.media_type,
          title: item.title || "Unknown title",
        });
        if (saved?.id) {
          setWatchlistPins((prev) => upsertPin(prev, { ...saved, _optimistic: false }));
        }
      }
    } catch (error) {
      console.error(error);
      setWatchlistPins(rollback);
    }
  }

  function handleRecommendTitle(item: LibraryItem) {
    setRecommendItem(item);
  }

  async function handleReviewSave({ prompt, stars, review_text: reviewText, session_id: reviewSessionId, replace_plex_rating: replacePlexRating }: JsParam) {
    const slashRate = String(prompt.id || "").startsWith("slash-rate-");
    const viewedUnrated = String(prompt.id || "").startsWith("viewed-unrated-");
    await saveReview({
      stars,
      title: prompt.title,
      media_type: prompt.media_type,
      rating_key: prompt.rating_key,
      review_text: reviewText,
      prompted_by: slashRate ? "slash_rate" : viewedUnrated ? "batch_rate" : "near_complete",
      session_id: reviewSessionId || activeSessionId,
      prompt_id: slashRate || viewedUnrated ? undefined : prompt.id,
      replace_plex_rating: Boolean(replacePlexRating),
    });
    if (!slashRate && !viewedUnrated) {
      setReviewPrompts((current) => current.filter((entry) => entry.id !== prompt.id));
    }
    refreshReviewData();
  }

  async function handleReviewDismiss(prompt: JsParam) {
    if (!String(prompt.id || "").startsWith("slash-rate-") && !String(prompt.id || "").startsWith("viewed-unrated-")) {
      await dismissReviewPrompt(prompt.id);
      setReviewPrompts((current) => current.filter((entry) => entry.id !== prompt.id));
    }
  }

  async function handleReviewConflictResolved() {
    refreshReviewData();
  }

  function handleDockDrop(item: LibraryItem) {
    const target = resolveDockDropTarget(item, {
      radarrConnected: arrServiceConnected(setup, features, "radarr"),
      sonarrConnected: arrServiceConnected(setup, features, "sonarr"),
    });
    if (!target) return;
    handleAdd(item, target);
  }

  const requestPath = requestPathFromFeatures(features);
  const agentPulse = resolveAgentPulse({ loading, chatError });
  const curatorName = persona?.curator_name || "Curator";
  const radarrConnected = arrServiceConnected(setup, features, "radarr");
  const sonarrConnected = arrServiceConnected(setup, features, "sonarr");
  const dockDropEnabled =
    requestPath !== "seerr" && (radarrConnected || sonarrConnected);
  const personaLookup = useMemo(
    () => Object.fromEntries(personas.map((p) => [p.id, p])),
    [personas],
  );
  const watchlistLookup = buildWatchlistLookup(watchlistPins);
  const personaUi = persona?.persona_ui;
  const contextLabel = activeContext?.inferred_label || "Exploring…";
  const ambientAccent = blendAmbientAccent(
    activeContext?.context_hash,
    personaUi?.accent_hue,
  );
  const showWelcomePanel = threadsReady && messages.length === 0;
  const resumeThread = pickResumeThread(threads, activeSessionId);
  const resumeChip = resumeChipFromThread(resumeThread);
  const homeChips = [...(resumeChip ? [resumeChip] : []), ...CHAT_LAUNCHER_CHIPS];
  const shelfPages = holdableShelfPages(savedShelf);
  const reviewPromptMessages = reviewPrompts.map((prompt) => ({
    id: `review-prompt-${prompt.id}`,
    role: "assistant",
    blocks: [reviewPromptBlock(prompt)],
  }));
  const displayMessages = [...messages, ...reviewPromptMessages];

  return (
    <ChatWorkspace
      authReady={authReady}
      isYouth={isYouth}
      ambientAccent={ambientAccent}
      isOwner={isOwner}
      userRole={userRole}
      multiUserEnabled={multiUserEnabled}
      seerrEnabled={seerrEnabled}
      liveChannelsReady={liveChannelsReady}
      appNavOpen={appNavOpen}
      setAppNavOpen={setAppNavOpen}
      agentPulse={agentPulse}
      chatError={chatError}
      inboxUnreadCount={inboxUnreadCount}
      uiTheme={uiTheme}
      setUiTheme={setUiTheme}
      nightOwl={nightOwl}
      mobileNavOpen={mobileNavOpen}
      setMobileNavOpen={setMobileNavOpen}
      setup={setup}
      sidebarCollapsed={sidebarCollapsed}
      handleCreateThread={handleCreateThread}
      toggleSidebarRail={toggleSidebarRail}
      threads={threads}
      activeSessionId={activeSessionId}
      switchThread={switchThread}
      handleDeleteThread={handleDeleteThread}
      personaLookup={personaLookup}
      undoToast={undoToast}
      handleUndoDeleteThread={handleUndoDeleteThread}
      commitPendingDelete={commitPendingDelete}
      stats={stats}
      watchlistPins={watchlistPins}
      jobs={jobs}
      personaUi={personaUi}
      pendingAdd={pendingAdd}
      pendingBulk={pendingBulk}
      pendingTokens={pendingTokens}
      messages={messages}
      addInProgress={addInProgress}
      addProgress={addProgress}
      addFeedback={addFeedback}
      confirmActiveAction={confirmActiveAction}
      cancelActiveAction={cancelActiveAction}
      dismissAddFeedback={dismissAddFeedback}
      dockDropEnabled={dockDropEnabled}
      handleDockDrop={handleDockDrop}
      radarrConnected={radarrConnected}
      sonarrConnected={sonarrConnected}
      scrollRef={scrollRef}
      showWelcomePanel={showWelcomePanel}
      anniversaries={anniversaries}
      libraryGlance={libraryGlance}
      glanceShown={glanceShown}
      handleDismissGlance={handleDismissGlance}
      curatorName={curatorName}
      sendMessage={sendMessage}
      homeChips={homeChips}
      handleContextChip={handleContextChip}
      shelfPages={shelfPages}
      displayMessages={displayMessages}
      reviewLookup={reviewLookup}
      messageFeedback={messageFeedback}
      handleMessageFeedbackChange={handleMessageFeedbackChange}
      handleReviewSave={handleReviewSave}
      handleReviewDismiss={handleReviewDismiss}
      handleAdd={handleAdd}
      handleDismiss={handleDismiss}
      setTurnstyleResults={setTurnstyleResults}
      handleConfirmAllItems={handleConfirmAllItems}
      handleConfirmAllTokens={handleConfirmAllTokens}
      loading={loading}
      handleToggleWatchlistPin={handleToggleWatchlistPin}
      handleRecommendTitle={handleRecommendTitle}
      watchlistLookup={watchlistLookup}
      requestPath={requestPath}
      handleReviewConflictResolved={handleReviewConflictResolved}
      handleSaveToLibrary={handleSaveToLibrary}
      handleOpenAgentResultsGrid={handleOpenAgentResultsGrid}
      agentActivityLog={agentActivityLog}
      typingLabel={typingLabel}
      activityPanelOpen={activityPanelOpen}
      setActivityPanelOpen={setActivityPanelOpen}
      showNewReplyChip={showNewReplyChip}
      scrollToLatestTurn={scrollToLatestTurn}
      input={input}
      contextLabel={contextLabel}
      showSlashPalette={showSlashPalette}
      slashPaletteItems={slashPaletteItems}
      slashPaletteIndex={slashPaletteIndex}
      handleSlashPaletteSelect={handleSlashPaletteSelect}
      setSlashPaletteIndex={setSlashPaletteIndex}
      composerRef={composerRef}
      setInput={setInput}
      konamiTrackerRef={konamiTrackerRef}
      persona={persona}
      setMessages={setMessages}
      speakAssistantMessage={speakAssistantMessage}
      threadsReady={threadsReady}
      voiceListening={voiceListening}
      composerPlaceholder={composerPlaceholder}
      personas={personas}
      activePersonaId={activePersonaId}
      setActivePersonaId={setActivePersonaId}
      handleCreatePersona={handleCreatePersona}
      handleUpdatePersona={handleUpdatePersona}
      handleDeletePersona={handleDeletePersona}
      handleSetDefaultPersona={handleSetDefaultPersona}
      defaultPersonaId={defaultPersonaId}
      showMic={showMic}
      toggleListening={toggleListening}
      voiceSpeaking={voiceSpeaking}
      ttsMuted={ttsMuted}
      unmuteTts={unmuteTts}
      muteTts={muteTts}
      surpriseMood={surpriseMood}
      quickPickLoading={quickPickLoading}
      handleQuickPick={handleQuickPick}
      voiceStatus={voiceStatus}
      turnstyleResults={turnstyleResults}
      keyboardHelpOpen={keyboardHelpOpen}
      setKeyboardHelpOpen={setKeyboardHelpOpen}
      features={features}
      recommendItem={recommendItem}
      setRecommendItem={setRecommendItem}
    />
  );
}
