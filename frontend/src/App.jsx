import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import {
  api,
  addWatchlistPin,
  confirmAction,
  createThread,
  deleteThread,
  dismissReviewPrompt,
  formatApiError,
  getActiveContext,
  getAuthMe,
  getFeatures,
  patchAuthMe,
  getThreadFeedback,
  getThreadMessages,
  getTypingPhrases,
  listJobs,
  listRecommendations,
  listReviewPrompts,
  listReviews,
  listThreads,
  listWatchlist,
  markRecommendationsSeen,
  proposeAction,
  removeWatchlistPin,
  runWatchlistSync,
  saveReview,
  createPersona,
  deletePersona,
  getPersonas,
  sendChat,
  sendChatStream,
  sessionId,
  setActiveSession,
  setDefaultPersona,
  submitMessageFeedback,
  updatePersona,
} from "./api/client";
import {
  activityEventFromToolCall,
  appendActivityLog,
  createActivityEvent,
  nextActivityPanelExpanded,
} from "./lib/agentActivityLog.js";
import { resolveAgentPulse } from "./lib/agentPulse.js";
import {
  addItemKey,
  withAddInFlight,
  withoutAddInFlight,
} from "./lib/addConcurrency.js";
import {
  alreadyInArrMessage,
  buildProposeActionBody,
  isAlreadyInArr,
  lastAssistantHasTitleCards,
  normalizePendingTokens,
  requestPathFromFeatures,
  serviceLabelForTarget,
  tokenConfirmFailureMessage,
  tokenConfirmSuccessMessage,
} from "./lib/addActions.js";
import { blendAmbientAccent } from "./lib/ambientAccent.js";
import { shouldSubmitComposerOnEnter } from "./lib/composerKeyboard.js";
import { createId } from "./lib/id.js";
import { executeSlashCommand, parseSlashCommand } from "./lib/slashCommands.js";
import { normalizeQuickPickError, normalizeQuickPickResult } from "./lib/quickPick.js";
import { resolveActivePersonaId } from "./lib/resolveActivePersona.js";
import {
  createKonamiTracker,
  easterEggAlreadyFired,
  easterEggResponse,
  isReversedCuratorName,
  markEasterEggFired,
  resolveDockDropTarget,
} from "./lib/easterEggs.js";
import { extractSpeakableText } from "./lib/voiceSpeech.js";
import {
  applyUiFontSize,
  applyUiTheme,
  cycleUiTheme,
  loadStoredUiTheme,
  normalizeUiTheme,
  themeControlIcon,
  themePreferenceLabel,
} from "./lib/uiPrefs.js";
import {
  isRateFlowRequest,
  isWatchlistPanelRequest,
  ROUTES,
  stripRateFlowParam,
  stripWatchlistPanelParam,
} from "./lib/backNav.js";
import { buildWatchlistLookup } from "./lib/watchlistKeys.js";
import ChatThread from "./components/ChatThread";
import InlineAlert from "./components/InlineAlert";
import PersonaSelector from "./components/PersonaSelector";
import KeyboardHelpModal from "./components/KeyboardHelpModal";
import NewReplyChip from "./components/NewReplyChip";
import RecommendModal from "./components/RecommendModal";
import RecommendationsInbox from "./components/RecommendationsInbox";
import StatusDock from "./components/StatusDock";
import AppNav, { AppNavToggle } from "./components/AppNav";
import CuratorXBrand from "./components/CuratorXBrand";
import ThreadList from "./components/ThreadList";
import TurnstyleResultsOverlay from "./components/TurnstyleResultsOverlay";
import TypingIndicator from "./components/TypingIndicator";
import UndoToast from "./components/UndoToast";
import WatchlistPanel from "./components/WatchlistPanel";
import WelcomePanel from "./components/WelcomePanel";
import OnThisDayCard from "./components/OnThisDayCard";
import LibraryGlanceCard from "./components/LibraryGlanceCard";
import QuickPickCard from "./components/QuickPickCard";
import UserMenu, { useAuthGate } from "./components/UserMenu";
import { reviewPromptBlock } from "./components/ReviewPromptCard";
import useChatScroll from "./hooks/useChatScroll";
import useKeyboardShortcuts from "./hooks/useKeyboardShortcuts";
import useVoiceMode from "./hooks/useVoiceMode.js";

const SIDEBAR_RAIL_KEY = "curatorx.sidebar.rail";
const ADD_FEEDBACK_DISMISS_MS = 5000;
const THREAD_DELETE_UNDO_MS = 6000;
const PERFECT_PICK_ACK =
  "\n\n*(You're on a roll with these picks — I'll keep that momentum going.)*";

function pickRandomPhrase(phrases, fallback) {
  if (!phrases?.length) return fallback;
  return phrases[Math.floor(Math.random() * phrases.length)];
}

function isNightOwlHour() {
  return new Date().getHours() >= 23;
}

function appendPerfectPickAck(message) {
  if (!message?.blocks?.length) return message;
  const blocks = message.blocks.map((block, index) => {
    if (index === 0 && block.type === "text") {
      return { ...block, content: `${block.content}${PERFECT_PICK_ACK}` };
    }
    return block;
  });
  return { ...message, blocks };
}

export default function App() {
  const { authReady, multiUserEnabled, isOwner, role: userRole } = useAuthGate();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [uiTheme, setUiTheme] = useState(() => loadStoredUiTheme());
  const [messages, setMessages] = useState([]);
  const [messageFeedback, setMessageFeedback] = useState({});
  const [threads, setThreads] = useState([]);
  const [activeSessionId, setActiveSessionId] = useState(() => sessionId());
  const [threadsReady, setThreadsReady] = useState(false);
  const [turnstyleResults, setTurnstyleResults] = useState(null);
  const [pendingAdd, setPendingAdd] = useState(null);
  const [pendingBulk, setPendingBulk] = useState(null);
  const [pendingTokens, setPendingTokens] = useState([]);
  const [addInProgress, setAddInProgress] = useState(false);
  const addInFlightKeysRef = useRef(new Set());
  const [appNavOpen, setAppNavOpen] = useState(false);
  const [addProgress, setAddProgress] = useState(null);
  const [addFeedback, setAddFeedback] = useState(null);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [chatError, setChatError] = useState("");
  const [stats, setStats] = useState(null);
  const [setup, setSetup] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [persona, setPersona] = useState(null);
  const [features, setFeatures] = useState(null);
  const [activeContext, setActiveContext] = useState(null);
  const [keyboardHelpOpen, setKeyboardHelpOpen] = useState(false);
  const [watchlistPins, setWatchlistPins] = useState([]);
  const [recommendItem, setRecommendItem] = useState(null);
  const [incomingRecommendations, setIncomingRecommendations] = useState([]);
  const [reviewPrompts, setReviewPrompts] = useState([]);
  const [reviewLookup, setReviewLookup] = useState({});
  const [typingPhrases, setTypingPhrases] = useState([]);
  const [typingLabel, setTypingLabel] = useState("");
  const [agentActivityLog, setAgentActivityLog] = useState([]);
  const [activityPanelOpen, setActivityPanelOpen] = useState(false);
  const [composerPlaceholder, setComposerPlaceholder] = useState("");
  const [nightOwl, setNightOwl] = useState(isNightOwlHour);
  const [anniversaries, setAnniversaries] = useState([]);
  const [libraryGlance, setLibraryGlance] = useState(null);
  const [glanceShown, setGlanceShown] = useState(false);
  const [quickPick, setQuickPick] = useState(null);
  const [quickPickLoading, setQuickPickLoading] = useState(false);
  const [undoToast, setUndoToast] = useState(null);
  const [personas, setPersonas] = useState([]);
  const [activePersonaId, setActivePersonaId] = useState(null);
  const [defaultPersonaId, setDefaultPersonaId] = useState(null);
  const [authUser, setAuthUser] = useState(null);
  const helpfulCountRef = useRef(0);
  const perfectPickPendingRef = useRef(false);
  const jobsRunningRef = useRef(false);
  const tokenNoteLoggedRef = useRef(false);
  const composerRef = useRef(null);
  const quickPickAnchorRef = useRef(null);
  const konamiTrackerRef = useRef(null);
  const inputRef = useRef("");
  const pendingDeleteRef = useRef(null);
  const rateFlowStartedRef = useRef(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    try {
      return sessionStorage.getItem(SIDEBAR_RAIL_KEY) === "true";
    } catch {
      return false;
    }
  });
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  useEffect(() => {
    if (!isWatchlistPanelRequest(searchParams)) return;
    setSearchParams(stripWatchlistPanelParam(searchParams), { replace: true });
    navigate(ROUTES.watchlist);
  }, [searchParams, setSearchParams, navigate]);

  inputRef.current = input;

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
    getComposerText: () => inputRef.current,
    setComposerText: setInput,
  });

  const speakAssistantMessage = useCallback(
    (message) => {
      speakReply(extractSpeakableText(message));
    },
    [speakReply]
  );

  const { scrollRef, showNewReplyChip, scrollToLatestTurn } = useChatScroll({
    messages,
    loading,
    sessionId: activeSessionId,
  });

  const refreshReviewData = useCallback(async () => {
    try {
      const [reviewsData, promptsData] = await Promise.all([listReviews({ limit: 200 }), listReviewPrompts(5)]);
      const lookup = {};
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

  const refreshJobs = useCallback(() => {
    listJobs().then(setJobs).catch(console.error);
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
    if (!multiUserEnabled) {
      setIncomingRecommendations([]);
      return;
    }
    listRecommendations({ unread_only: true, limit: 8 })
      .then((data) => setIncomingRecommendations(data.items || []))
      .catch(() => setIncomingRecommendations([]));
  }, [multiUserEnabled]);

  const refreshTypingPhrases = useCallback(() => {
    getTypingPhrases()
      .then((data) => setTypingPhrases(data.phrases || []))
      .catch(console.error);
  }, []);

  const refreshPersonas = useCallback(async () => {
    try {
      const data = await getPersonas();
      const list = data.items || data || [];
      setPersonas(list);
      const def = list.find((p) => p.is_default);
      const nextDefaultId = def?.id ?? null;
      setDefaultPersonaId(nextDefaultId);
      return { list, defaultPersonaId: nextDefaultId };
    } catch (error) {
      console.error(error);
      return { list: [], defaultPersonaId: null };
    }
  }, []);

  const refreshThreads = useCallback(async () => {
    try {
      const nextThreads = await listThreads();
      setThreads(nextThreads);
      return nextThreads;
    } catch (error) {
      console.error(error);
      return [];
    }
  }, []);

  const loadThreadFeedback = useCallback(async (session) => {
    try {
      const data = await getThreadFeedback(session);
      const next = {};
      for (const item of data.items || []) {
        if (item.message_id && item.feedback) {
          next[item.message_id] = item.feedback;
        }
      }
      setMessageFeedback(next);
    } catch (error) {
      if (!error.message?.includes("Thread not found")) {
        console.error(error);
      }
      setMessageFeedback({});
    }
  }, []);

  const loadThreadMessages = useCallback(async (session) => {
    try {
      const data = await getThreadMessages(session);
      setMessages(data.messages || []);
      setChatError("");
      await loadThreadFeedback(session);
      return true;
    } catch (error) {
      if (error.message?.includes("Thread not found")) {
        setMessages([]);
        setMessageFeedback({});
        return false;
      }
      console.error(error);
      return false;
    }
  }, [loadThreadFeedback]);

  const switchThread = useCallback(
    async (session) => {
      setMobileNavOpen(false);
      if (!session || session === activeSessionId) return;
      helpfulCountRef.current = 0;
      perfectPickPendingRef.current = false;
      setActiveSession(session);
      setActiveSessionId(session);
      setChatError("");
      setAgentActivityLog([]);
      setActivityPanelOpen(false);
      setPendingAdd(null);
      setPendingBulk(null);
      setPendingTokens([]);
      setAddFeedback(null);
      const thread = threads.find((t) => t.id === session);
      setActivePersonaId(thread?.persona_id || defaultPersonaId);
      if (thread?.context_label) {
        setActiveContext({ context_hash: thread.context_hash || "general", inferred_label: thread.context_label });
      } else {
        getActiveContext()
          .then(setActiveContext)
          .catch(() => setActiveContext({ context_hash: "general", inferred_label: "General Exploration" }));
      }
      await loadThreadMessages(session);
    },
    [activeSessionId, defaultPersonaId, loadThreadMessages, threads]
  );

  const handleCreateThread = useCallback(async () => {
    setMobileNavOpen(false);
    try {
      const created = await createThread();
      const nextId = created.session_id;
      setActiveSession(nextId);
      setActiveSessionId(nextId);
      setMessages([]);
      setMessageFeedback({});
      setChatError("");
      setActivePersonaId(defaultPersonaId);
      setActiveContext({ context_hash: "general", inferred_label: "General Exploration" });
      await refreshThreads();
    } catch (error) {
      console.error(error);
    }
  }, [defaultPersonaId, refreshThreads]);

  const commitPendingDelete = useCallback(async () => {
    const pending = pendingDeleteRef.current;
    if (!pending) return;
    pendingDeleteRef.current = null;
    setUndoToast(null);
    try {
      await deleteThread(pending.session);
      await refreshThreads();
    } catch (error) {
      console.error(error);
      // Restore on failure.
      setThreads((prev) => {
        if (prev.some((thread) => thread.id === pending.thread.id)) return prev;
        return [pending.thread, ...prev];
      });
    }
  }, [refreshThreads]);

  const handleUndoDeleteThread = useCallback(() => {
    const pending = pendingDeleteRef.current;
    if (!pending) return;
    clearTimeout(pending.timer);
    pendingDeleteRef.current = null;
    setUndoToast(null);
    setThreads((prev) => {
      if (prev.some((thread) => thread.id === pending.thread.id)) return prev;
      return [pending.thread, ...prev];
    });
  }, []);

  const handleDeleteThread = useCallback(
    async (session) => {
      if (!session) return;
      // Flush any prior pending delete first.
      if (pendingDeleteRef.current) {
        clearTimeout(pendingDeleteRef.current.timer);
        await commitPendingDelete();
      }
      const thread = threads.find((item) => item.id === session);
      if (!thread) return;

      const remaining = threads.filter((item) => item.id !== session);
      setThreads(remaining);

      if (session === activeSessionId) {
        if (remaining.length) {
          const nextId = remaining[0].id;
          setActiveSession(nextId);
          setActiveSessionId(nextId);
          await loadThreadMessages(nextId);
        } else {
          try {
            const created = await createThread();
            const nextId = created.session_id;
            setActiveSession(nextId);
            setActiveSessionId(nextId);
            setMessages([]);
            setMessageFeedback({});
            await refreshThreads();
          } catch (error) {
            console.error(error);
          }
        }
      }

      const timer = setTimeout(() => {
        commitPendingDelete();
      }, THREAD_DELETE_UNDO_MS);
      pendingDeleteRef.current = { session, thread, timer };
      setUndoToast({ message: "Conversation deleted" });
    },
    [
      activeSessionId,
      commitPendingDelete,
      loadThreadMessages,
      refreshThreads,
      threads,
    ],
  );

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

  const handleMessageFeedbackChange = useCallback(
    async (messageId, feedback) => {
      const previous = messageFeedback[messageId] ?? null;
      if (feedback === previous) return;

      if (!feedback) {
        setMessageFeedback((current) => {
          const next = { ...current };
          delete next[messageId];
          return next;
        });
        try {
          await submitMessageFeedback(messageId, activeSessionId, null);
        } catch (error) {
          if (previous) {
            setMessageFeedback((current) => ({ ...current, [messageId]: previous }));
          }
          console.error(error);
        }
        return;
      }

      setMessageFeedback((current) => ({ ...current, [messageId]: feedback }));
      if (feedback === "helpful") {
        helpfulCountRef.current += 1;
        if (helpfulCountRef.current >= 5) {
          perfectPickPendingRef.current = true;
        }
      }
      try {
        await submitMessageFeedback(messageId, activeSessionId, feedback);
      } catch (error) {
        setMessageFeedback((current) => {
          const next = { ...current };
          if (previous) {
            next[messageId] = previous;
          } else {
            delete next[messageId];
          }
          return next;
        });
        console.error(error);
      }
    },
    [activeSessionId, messageFeedback]
  );

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
    async function initializeThreads() {
      let storedId = sessionId();
      let threadList = await refreshThreads();
      let loaded = await loadThreadMessages(storedId);
      const storedExists = threadList.some((thread) => thread.id === storedId);

      if (!storedExists && !loaded) {
        if (threadList.length > 0) {
          storedId = threadList[0].id;
          setActiveSession(storedId);
          setActiveSessionId(storedId);
          await loadThreadMessages(storedId);
        } else {
          const created = await createThread();
          storedId = created.session_id;
          setActiveSession(storedId);
          setActiveSessionId(storedId);
          threadList = await refreshThreads();
        }
      } else if (!storedExists) {
        threadList = await refreshThreads();
      }

      setActiveSessionId(storedId);

      const activeThread = threadList.find((t) => t.id === storedId);
      if (activeThread?.context_label) {
        setActiveContext({
          context_hash: activeThread.context_hash || "general",
          inferred_label: activeThread.context_label,
        });
      } else {
        setActiveContext({ context_hash: "general", inferred_label: "General Exploration" });
      }

      setThreadsReady(true);
    }

    initializeThreads().catch(console.error);
  }, [loadThreadMessages, refreshThreads]);

  // Ensure the persona dropdown reflects default / thread selection once both
  // personas and the active thread are available (they load in parallel).
  useEffect(() => {
    if (!threadsReady || !personas.length) return;
    const activeThread = threads.find((t) => t.id === activeSessionId);
    setActivePersonaId((current) =>
      resolveActivePersonaId({
        activePersonaId: current,
        threadPersonaId: activeThread?.persona_id || null,
        defaultPersonaId,
        personas,
      }),
    );
  }, [threadsReady, personas, defaultPersonaId, activeSessionId, threads]);

  useEffect(() => {
    Promise.all([
      api("/setup/status").then(setSetup),
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
    refreshTypingPhrases();
    refreshPersonas();
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
    const interval = setInterval(refreshJobs, 5000);
    const nightInterval = setInterval(() => setNightOwl(isNightOwlHour()), 60_000);
    return () => {
      clearInterval(interval);
      clearInterval(nightInterval);
    };
  }, [
    refreshJobs,
    refreshPersonas,
    refreshRecommendations,
    refreshReviewData,
    refreshTypingPhrases,
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

  useEffect(() => {
    if (!loading) return;
    const fallback = `${persona?.curator_name || "Curator"} is thinking`;
    const phrase = pickRandomPhrase(typingPhrases, fallback);
    setTypingLabel(phrase);
    setAgentActivityLog((prev) => {
      if (prev.some((entry) => entry.kind === "status")) return prev;
      return appendActivityLog(prev, createActivityEvent({ kind: "status", label: phrase }));
    });
  }, [loading, persona?.curator_name, typingPhrases]);

  useEffect(() => {
    refreshTypingPhrases();
  }, [persona?.persona_preset_id, persona?.curator_name, refreshTypingPhrases]);

  const personaUi = persona?.persona_ui;
  const composerPlaceholders =
    personaUi?.composer_placeholders?.length
      ? personaUi.composer_placeholders
      : ["Describe what you're hunting for…"];

  useEffect(() => {
    if (!composerPlaceholders.length) return undefined;
    setComposerPlaceholder(composerPlaceholders[0]);
    let index = 0;
    const interval = setInterval(() => {
      index = (index + 1) % composerPlaceholders.length;
      setComposerPlaceholder(composerPlaceholders[index]);
    }, 8000);
    return () => clearInterval(interval);
  }, [composerPlaceholders]);

  useEffect(() => {
    if (!addFeedback) return undefined;
    const timer = setTimeout(() => setAddFeedback(null), ADD_FEEDBACK_DISMISS_MS);
    return () => clearTimeout(timer);
  }, [addFeedback]);

  function dismissAddFeedback() {
    setAddFeedback(null);
  }

  function appendChatError(reason) {
    const snark = persona?.val_dipl_snark ?? 0.5;
    let message;
    if (snark >= 0.66) {
      message = `Well, that didn't work — ${reason}`;
    } else if (snark <= 0.33) {
      message = `Sorry, I couldn't respond just now: ${reason}`;
    } else {
      message = `Curator couldn't respond: ${reason}`;
    }
    setChatError(message);
    setMessages((prev) => [
      ...prev,
      {
        id: createId(),
        role: "error",
        blocks: [{ type: "error", content: message }],
      },
    ]);
  }

  function handleDismissGlance() {
    setLibraryGlance(null);
    setGlanceShown(true);
    api("/system-config", {
      method: "PUT",
      body: JSON.stringify({ values: { library_glance_shown: "true" } }),
    }).catch(() => {});
  }

  async function handleCreatePersona(data) {
    await createPersona(data);
    const { list } = await refreshPersonas();
    if (list.length === 1) setActivePersonaId(list[0].id);
  }

  async function handleUpdatePersona(id, data) {
    await updatePersona(id, data);
    await refreshPersonas();
  }

  async function handleDeletePersona(id) {
    await deletePersona(id);
    await refreshPersonas();
    if (activePersonaId === id) setActivePersonaId(defaultPersonaId);
  }

  async function handleSetDefaultPersona(id) {
    await setDefaultPersona(id);
    setDefaultPersonaId(id);
  }

  async function handleQuickPick() {
    if (quickPickLoading) return;
    setQuickPickLoading(true);
    try {
      const result = await api("/library/quick-pick");
      setQuickPick(normalizeQuickPickResult(result));
    } catch (error) {
      setQuickPick(normalizeQuickPickError(error, formatApiError));
    } finally {
      setQuickPickLoading(false);
    }
  }

  // Surprise Me renders near the composer (below the transcript). Scroll it into
  // view so a long chat history never makes the pick look like a silent no-op.
  useEffect(() => {
    if (!quickPickLoading && !quickPick) return;
    const el = quickPickAnchorRef.current;
    if (!el) return;
    requestAnimationFrame(() => {
      el.scrollIntoView({ behavior: "smooth", block: "nearest" });
    });
  }, [quickPickLoading, quickPick]);

  async function sendMessage(text) {
    if (!text.trim() || loading) return;
    stopVoiceListening();
    stopTts();
    setLoading(true);
    setChatError("");
    tokenNoteLoggedRef.current = false;
    setAgentActivityLog([]);
    setActivityPanelOpen(false);
    const userMessage = {
      id: createId(),
      role: "user",
      blocks: [{ type: "text", content: text }],
    };
    setMessages((prev) => [...prev, userMessage]);
    setInput("");

    const curatorName = persona?.curator_name || "Curator";
    if (!easterEggAlreadyFired() && isReversedCuratorName(text, curatorName)) {
      markEasterEggFired();
      const eggMessage = {
        id: createId(),
        role: "assistant",
        blocks: [{ type: "text", content: easterEggResponse("reversed_name", curatorName) }],
      };
      setMessages((prev) => [...prev, eggMessage]);
      speakAssistantMessage(eggMessage);
      setAgentActivityLog([]);
      setLoading(false);
      return;
    }

    const slash = parseSlashCommand(text);
    if (slash) {
      try {
        const assistantMessage = await executeSlashCommand(slash, {
          api,
          getFeatures,
          curatorName: persona?.curator_name || "Curator",
          user: reviewUserContext,
        });
        setMessages((prev) => [...prev, assistantMessage]);
        speakAssistantMessage(assistantMessage);
        if (slash.command === "sync" && !features?.features?.multi_user_enabled) {
          refreshJobs();
        }
        if (slash.command === "stats") {
          api("/library/stats").then(setStats).catch(console.error);
        }
      } catch (error) {
        appendChatError(formatApiError(error));
      } finally {
        setAgentActivityLog([]);
        setActivityPanelOpen(false);
        setLoading(false);
      }
      return;
    }

    const streamPlaceholderId = createId();
    let streamAccumulated = "";
    let streamFailed = false;

    try {
      setMessages((prev) => [
        ...prev,
        { id: streamPlaceholderId, role: "assistant", blocks: [{ type: "text", content: "" }], _streaming: true },
      ]);

      await sendChatStream(text, {
        sessionId: activeSessionId,
        personaId: activePersonaId || undefined,
        onToken: ({ content }) => {
          streamAccumulated += content;
          const snapshot = streamAccumulated;
          if (!tokenNoteLoggedRef.current && snapshot.trim()) {
            tokenNoteLoggedRef.current = true;
            setAgentActivityLog((prev) =>
              appendActivityLog(prev, createActivityEvent({ kind: "token_note", label: "Writing response…" })),
            );
          }
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === streamPlaceholderId
                ? { ...msg, blocks: [{ type: "text", content: snapshot }] }
                : msg,
            ),
          );
        },
        onToolCall: ({ name, status, args, summary }) => {
          setAgentActivityLog((prev) =>
            appendActivityLog(prev, activityEventFromToolCall({ name, status, args, summary })),
          );
          if (status === "start") {
            const label = String(name || "tool").replace(/_/g, " ");
            setTypingLabel(`Searching ${label}…`);
          } else if (status === "complete") {
            setTypingLabel(`${persona?.curator_name || "Curator"} is thinking`);
          }
        },
        onDone: (data) => {
          let assistantMessage = data.message;
          if (perfectPickPendingRef.current) {
            assistantMessage = appendPerfectPickAck(assistantMessage);
            perfectPickPendingRef.current = false;
            helpfulCountRef.current = 0;
          }
          setMessages((prev) =>
            prev.map((msg) => (msg.id === streamPlaceholderId ? assistantMessage : msg)),
          );
          speakAssistantMessage(assistantMessage);
          setPendingTokens(normalizePendingTokens(data.pending_tokens));
          if (Array.isArray(data.pending_tokens) && data.pending_tokens.length >= 2) {
            setPendingBulk(null);
            setPendingAdd(null);
          }
          setAgentActivityLog((prev) =>
            appendActivityLog(prev, createActivityEvent({ kind: "status", label: "Response ready" })),
          );
          setActivityPanelOpen((open) => nextActivityPanelExpanded({ streamDone: true, expanded: open }));
          refreshJobs();
          refreshThreads();
          getActiveContext()
            .then(setActiveContext)
            .catch(() => {});
        },
        onError: ({ error }) => {
          streamFailed = true;
          setMessages((prev) => prev.filter((msg) => msg.id !== streamPlaceholderId));
          appendChatError(error || "Chat stream failed");
          setActivityPanelOpen((open) => nextActivityPanelExpanded({ streamDone: true, expanded: open }));
        },
      });
    } catch (error) {
      if (!streamFailed) {
        setMessages((prev) => prev.filter((msg) => msg.id !== streamPlaceholderId));
        appendChatError(formatApiError(error));
      }
      setActivityPanelOpen((open) => nextActivityPanelExpanded({ streamDone: true, expanded: open }));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!authReady || !threadsReady || loading || rateFlowStartedRef.current) return;
    if (!isRateFlowRequest(searchParams)) return;
    rateFlowStartedRef.current = true;
    setSearchParams(stripRateFlowParam(searchParams), { replace: true });
    sendMessage("/rate");
  }, [authReady, threadsReady, loading, searchParams, setSearchParams]);

  useEffect(() => {
    return () => {
      if (pendingDeleteRef.current?.timer) {
        clearTimeout(pendingDeleteRef.current.timer);
      }
    };
  }, []);

  async function executeSingleAdd(item, target, { trackGlobal = false } = {}) {
    const label = item.title || "this title";
    const service = serviceLabelForTarget(target);
    const body = buildProposeActionBody(item, target);
    const key = addItemKey(item, target);

    addInFlightKeysRef.current = withAddInFlight(addInFlightKeysRef.current, key);
    if (trackGlobal) setAddInProgress(true);
    try {
      const proposal = await proposeAction(body);
      if (isAlreadyInArr(proposal)) {
        setAddFeedback({
          type: "success",
          message: alreadyInArrMessage(proposal, { label, service }),
        });
        return proposal;
      }
      const confirm = await confirmAction(proposal.confirmation_token);
      if (isAlreadyInArr(confirm)) {
        setAddFeedback({
          type: "success",
          message: alreadyInArrMessage(confirm, { label, service }),
        });
      } else {
        setAddFeedback({
          type: "success",
          message:
            target === "seerr"
              ? `Requested "${label}" in Seerr.`
              : `Added "${label}" to ${service}.`,
        });
      }
      return confirm;
    } catch (error) {
      setAddFeedback({ type: "error", message: formatApiError(error) });
      throw error;
    } finally {
      addInFlightKeysRef.current = withoutAddInFlight(addInFlightKeysRef.current, key);
      if (trackGlobal) setAddInProgress(false);
    }
  }

  async function handleAdd(item, target) {
    // Per-card concurrent adds — do not globally block other cards.
    setAddFeedback(null);
    setPendingBulk(null);
    setPendingTokens([]);
    setPendingAdd(null);
    await executeSingleAdd(item, target, { trackGlobal: false });
  }

  function handleConfirmAllItems(items, target) {
    if (!items?.length || addInProgress) return;
    setAddFeedback(null);
    setPendingAdd(null);
    setPendingTokens([]);
    // Chat / turnstyle "Confirm all" is the confirmation — do not enqueue a
    // second StatusDock bulk prompt that mirrors the in-message button.
    setPendingBulk(null);
    executeBulkAdd(items, target);
  }

  function handleConfirmAllTokens() {
    if (pendingTokens.length < 2 || addInProgress) return;
    setAddFeedback(null);
    setPendingAdd(null);
    setPendingBulk(null);
    executeConfirmAllTokens();
  }

  function cancelPendingBulk() {
    if (addInProgress) return;
    setPendingBulk(null);
  }

  function cancelPendingTokens() {
    if (addInProgress) return;
    setPendingTokens([]);
  }

  function cancelPendingAdd() {
    if (addInProgress) return;
    setPendingAdd(null);
  }

  const requestPath = requestPathFromFeatures(features);

  async function executeBulkAdd(items, target) {
    const service = serviceLabelForTarget(target);
    const action = target === "sonarr" ? "add_sonarr" : target === "seerr" ? "request_seerr" : "add_radarr";
    let successCount = 0;
    const failures = [];

    setAddInProgress(true);
    setAddProgress({ current: 0, total: items.length });

    for (let index = 0; index < items.length; index += 1) {
      const item = items[index];
      setAddProgress({ current: index + 1, total: items.length, title: item.title });
      const body = buildProposeActionBody(item, target);
      try {
        const proposal = await proposeAction(body);
        if (isAlreadyInArr(proposal)) {
          successCount += 1;
          continue;
        }
        const confirm = await confirmAction(proposal.confirmation_token);
        if (isAlreadyInArr(confirm)) {
          successCount += 1;
          continue;
        }
        successCount += 1;
      } catch (error) {
        failures.push({ title: item.title || "Unknown title", message: formatApiError(error) });
      }
    }

    setAddInProgress(false);
    setAddProgress(null);
    setPendingBulk(null);

    if (successCount === items.length) {
      setAddFeedback({
        type: "success",
        message:
          target === "seerr"
            ? `Requested ${successCount} title${successCount === 1 ? "" : "s"} in Seerr.`
            : `Added ${successCount} title${successCount === 1 ? "" : "s"} to ${service}.`,
      });
      return;
    }

    if (successCount > 0) {
      setAddFeedback({
        type: "error",
        message: `Added ${successCount} of ${items.length} to ${service}. ${failures.length} failed.`,
      });
      return;
    }

    setAddFeedback({
      type: "error",
      message: failures[0]?.message || `Could not add titles to ${service}.`,
    });
  }

  async function executeConfirmAllTokens() {
    const tokens = [...pendingTokens];
    let successCount = 0;
    const failures = [];

    setAddInProgress(true);
    setAddProgress({ current: 0, total: tokens.length });

    for (let index = 0; index < tokens.length; index += 1) {
      const entry = tokens[index];
      setAddProgress({ current: index + 1, total: tokens.length });
      try {
        const confirm = await confirmAction(entry.token);
        if (isAlreadyInArr(confirm)) {
          successCount += 1;
          continue;
        }
        successCount += 1;
      } catch (error) {
        failures.push(formatApiError(error));
      }
    }

    setAddInProgress(false);
    setAddProgress(null);
    setPendingTokens([]);

    if (successCount === tokens.length) {
      setAddFeedback({
        type: "success",
        message: tokenConfirmSuccessMessage(successCount, tokens),
      });
      return;
    }

    if (successCount > 0) {
      setAddFeedback({
        type: "error",
        message: `Confirmed ${successCount} of ${tokens.length}. ${failures.length} failed.`,
      });
      return;
    }

    setAddFeedback({
      type: "error",
      message: failures[0] || tokenConfirmFailureMessage(tokens),
    });
  }

  async function confirmActiveAction() {
    if (pendingBulk) {
      await executeBulkAdd(pendingBulk.items, pendingBulk.target);
      return;
    }
    if (pendingTokens.length >= 2) {
      await executeConfirmAllTokens();
      return;
    }
    await confirmPendingAdd();
  }

  function cancelActiveAction() {
    if (pendingBulk) {
      cancelPendingBulk();
      return;
    }
    if (pendingTokens.length >= 2) {
      cancelPendingTokens();
      return;
    }
    cancelPendingAdd();
  }

  async function confirmPendingAdd() {
    if (!pendingAdd || addInProgress) return;
    const { item, target } = pendingAdd;
    try {
      await executeSingleAdd(item, target, { trackGlobal: true });
      setPendingAdd(null);
    } catch {
      // Feedback already set by executeSingleAdd.
    }
  }

  async function handleDismiss(item) {
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

  async function handleToggleWatchlistPin(item, pinRecord) {
    try {
      if (pinRecord?.id) {
        await removeWatchlistPin(pinRecord.id);
      } else {
        await addWatchlistPin({
          tmdb_id: item.tmdb_id,
          tvdb_id: item.tvdb_id,
          media_type: item.media_type,
          title: item.title || "Unknown title",
        });
      }
      refreshWatchlist();
    } catch (error) {
      console.error(error);
    }
  }

  function handleRecommendTitle(item) {
    setRecommendItem(item);
  }

  async function handleDismissRecommendation(rec) {
    if (!rec?.id) return;
    setIncomingRecommendations((prev) => prev.filter((item) => item.id !== rec.id));
    try {
      await markRecommendationsSeen({ ids: [rec.id] });
    } catch (error) {
      console.error(error);
      refreshRecommendations();
    }
  }

  async function handleDismissAllRecommendations(items) {
    setIncomingRecommendations([]);
    try {
      if (items?.length) {
        await markRecommendationsSeen({ ids: items.map((item) => item.id) });
      } else {
        await markRecommendationsSeen({ all_unread: true });
      }
    } catch (error) {
      console.error(error);
      refreshRecommendations();
    }
  }

  async function handleReviewSave({ prompt, stars, review_text: reviewText, session_id: reviewSessionId, replace_plex_rating: replacePlexRating }) {
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

  async function handleReviewDismiss(prompt) {
    if (!String(prompt.id || "").startsWith("slash-rate-") && !String(prompt.id || "").startsWith("viewed-unrated-")) {
      await dismissReviewPrompt(prompt.id);
      setReviewPrompts((current) => current.filter((entry) => entry.id !== prompt.id));
    }
  }

  async function handleReviewConflictResolved() {
    refreshReviewData();
  }

  function handleDockDrop(item) {
    const target = resolveDockDropTarget(item, {
      radarrConnected: Boolean(setup?.checks?.radarr?.ok),
      sonarrConnected: Boolean(setup?.checks?.sonarr?.ok),
    });
    if (!target) return;
    handleAdd(item, target);
  }

  const agentPulse = resolveAgentPulse({ loading, chatError });
  const curatorName = persona?.curator_name || "Curator";
  const radarrConnected = Boolean(setup?.checks?.radarr?.ok);
  const sonarrConnected = Boolean(setup?.checks?.sonarr?.ok);
  const dockDropEnabled =
    requestPath !== "seerr" && (radarrConnected || sonarrConnected);
  const personaLookup = useMemo(
    () => Object.fromEntries(personas.map((p) => [p.id, p])),
    [personas],
  );
  const watchlistLookup = buildWatchlistLookup(watchlistPins);
  const reviewUserContext = useMemo(
    () => authUser || features?.user || null,
    [authUser, features?.user],
  );
  const contextLabel = activeContext?.inferred_label || "Exploring…";
  const ambientAccent = blendAmbientAccent(
    activeContext?.context_hash,
    personaUi?.accent_hue,
  );
  const showWelcomePanel = threadsReady && messages.length === 0;
  const reviewPromptMessages = reviewPrompts.map((prompt) => ({
    id: `review-prompt-${prompt.id}`,
    role: "assistant",
    blocks: [reviewPromptBlock(prompt)],
  }));
  const displayMessages = [...messages, ...reviewPromptMessages];

  if (!authReady) {
    return (
      <div className="app-root workspace app-loading" data-testid="app-auth-loading">
        <p className="login-lede">Loading…</p>
      </div>
    );
  }

  return (
    <div
      className="app-root workspace"
      style={{ "--ambient-accent": ambientAccent }}
    >
      <AppNav
        open={appNavOpen}
        onClose={() => setAppNavOpen(false)}
        isOwner={isOwner}
      />
      <header className={`app-topbar ${nightOwl ? "night-owl" : ""}`}>
        <div className="app-topbar-brand">
          <AppNavToggle
            open={appNavOpen}
            onClick={() => setAppNavOpen(true)}
            testId="app-nav-toggle"
          />
          <button
            type="button"
            className="app-topbar-menu ghost app-topbar-threads"
            data-testid="mobile-nav-toggle"
            aria-label="Open conversations"
            aria-expanded={mobileNavOpen}
            aria-controls="workspace-sidebar"
            onClick={() => setMobileNavOpen(true)}
          >
            <span className="material-symbols-outlined" aria-hidden="true">
              chat
            </span>
          </button>
          <CuratorXBrand pulse={agentPulse} chatError={chatError} />
        </div>
        <div className="app-topbar-actions">
          <Link
            to="/explore"
            className="app-topbar-icon"
            data-testid="topbar-explore-link"
            aria-label="Explore"
            data-tooltip="Explore"
          >
            <span className="material-symbols-outlined" aria-hidden="true">
              explore
            </span>
          </Link>
          <button
            type="button"
            className="app-topbar-icon"
            data-testid="topbar-theme-toggle"
            aria-label={`Theme: ${themePreferenceLabel(uiTheme)}. Click to change.`}
            data-tooltip={themePreferenceLabel(uiTheme)}
            onClick={async () => {
              const next = cycleUiTheme(uiTheme);
              setUiTheme(next);
              applyUiTheme(next);
              try {
                await patchAuthMe({ ui_theme: next });
              } catch {
                // Persist locally even if auth/profile API is unavailable
              }
            }}
          >
            <span className="material-symbols-outlined" aria-hidden="true">
              {themeControlIcon(uiTheme)}
            </span>
          </button>
          {isOwner ? (
            <Link
              to="/admin"
              className="app-topbar-icon"
              data-testid="topbar-admin-link"
              aria-label="Admin"
              data-tooltip="Admin"
            >
              <span className="material-symbols-outlined" aria-hidden="true">
                admin_panel_settings
              </span>
            </Link>
          ) : null}
          <Link
            to="/settings"
            className="app-topbar-icon"
            data-testid="topbar-settings-link"
            aria-label="Settings"
            data-tooltip="Settings"
          >
            <span className="material-symbols-outlined" aria-hidden="true">
              settings
            </span>
          </Link>
          {multiUserEnabled ? <UserMenu /> : null}
        </div>
      </header>

      {setup && !setup.onboarding_complete ? (
        <div className="banner workspace-banner" data-testid="setup-banner">
          Finish setup in <Link to="/admin">Admin</Link> to connect Plex, TMDB, and your LLM provider.
        </div>
      ) : null}

      <div className={`workspace-body ${mobileNavOpen ? "mobile-nav-open" : ""}`}>
        {mobileNavOpen ? (
          <button
            type="button"
            className="workspace-drawer-backdrop"
            data-testid="mobile-nav-backdrop"
            aria-label="Close conversations"
            onClick={() => setMobileNavOpen(false)}
          />
        ) : null}
        <aside
          id="workspace-sidebar"
          className={`workspace-sidebar ${sidebarCollapsed ? "sidebar-collapsed" : ""} ${mobileNavOpen ? "mobile-nav-open" : ""}`}
          data-testid="workspace-sidebar"
        >
          <div className="workspace-sidebar-top">
            <p className="eyebrow workspace-sidebar-eyebrow">Conversations</p>
            <div className="workspace-sidebar-top-actions">
              <button
                type="button"
                className="ghost thread-new-btn"
                data-testid="new-thread"
                aria-label="New conversation"
                title="New conversation"
                onClick={handleCreateThread}
              >
                +
              </button>
              <button
                type="button"
                className="workspace-sidebar-toggle ghost"
                data-testid="sidebar-rail-toggle"
                onClick={toggleSidebarRail}
                aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
                title={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
              >
                {sidebarCollapsed ? "»" : "«"}
              </button>
            </div>
          </div>
          <ThreadList
            threads={threads}
            activeSessionId={activeSessionId}
            onSelect={switchThread}
            onCreate={handleCreateThread}
            onDelete={handleDeleteThread}
            hideHeader
            personaLookup={personaLookup}
          />
          {undoToast ? (
            <UndoToast
              message={undoToast.message}
              onUndo={handleUndoDeleteThread}
              onDismiss={() => {
                commitPendingDelete();
              }}
            />
          ) : null}
          <div className="sidebar-footer" data-testid="sidebar-footer">
            {stats ? (
              <p className="workspace-sidebar-library" data-testid="library-stats-chip">
                {stats.plex_server_name
                  ? `${stats.plex_server_name} · ${stats.movies} movies · ${stats.shows} shows`
                  : `${stats.movies} movies · ${stats.shows} shows`}
              </p>
            ) : null}
            <div className="sidebar-bottom-actions" data-testid="sidebar-bottom-actions">
              <Link
                to="/explore"
                className="sidebar-nav-btn"
                data-testid="sidebar-explore"
                onClick={() => setMobileNavOpen(false)}
              >
                Explore
              </Link>
              <WatchlistPanel count={watchlistPins.length} />
            </div>
          </div>
          <StatusDock
            jobs={jobs}
            jobStatusPhrases={personaUi?.job_status_phrases}
            pendingAdd={pendingAdd}
            pendingBulk={pendingBulk}
            pendingTokens={
              pendingTokens.length >= 2 && !lastAssistantHasTitleCards(messages)
                ? pendingTokens
                : null
            }
            addInProgress={addInProgress}
            addProgress={addProgress}
            addFeedback={addFeedback}
            onConfirm={confirmActiveAction}
            onCancel={cancelActiveAction}
            onDismissFeedback={dismissAddFeedback}
            onDropTitle={dockDropEnabled ? handleDockDrop : undefined}
            radarrConnected={radarrConnected}
            sonarrConnected={sonarrConnected}
          />
        </aside>

        <main className="workspace-main" data-testid="workspace-main">
          <div className="chat-scroll-region" data-testid="chat-scroll-region" ref={scrollRef}>
            {incomingRecommendations.length ? (
              <RecommendationsInbox
                items={incomingRecommendations}
                onDismiss={handleDismissRecommendation}
                onDismissAll={handleDismissAllRecommendations}
              />
            ) : null}
            {showWelcomePanel ? (
              <>
                {(anniversaries.length > 0 || (libraryGlance && !glanceShown)) ? (
                  <div className="home-bento" data-testid="home-bento">
                    {anniversaries.length > 0 ? (
                      <OnThisDayCard items={anniversaries} accentColor={personaUi?.accent_hue} />
                    ) : null}
                    {libraryGlance && !glanceShown ? (
                      <LibraryGlanceCard snapshot={libraryGlance} onDismiss={handleDismissGlance} />
                    ) : null}
                  </div>
                ) : null}
                <WelcomePanel
                  curatorName={curatorName}
                  greeting={personaUi?.welcome_greeting}
                  starters={personaUi?.welcome_starters}
                  onStarterSelect={sendMessage}
                />
              </>
            ) : null}
            {!showWelcomePanel && libraryGlance && !glanceShown ? (
              <LibraryGlanceCard snapshot={libraryGlance} onDismiss={handleDismissGlance} />
            ) : null}
            <ChatThread
              messages={displayMessages}
              sessionId={activeSessionId}
              curatorName={curatorName}
              reviewPromptTemplates={personaUi?.review_prompt_templates}
              reviewLookup={reviewLookup}
              messageFeedback={messageFeedback}
              onFeedbackChange={handleMessageFeedbackChange}
              onReviewSave={handleReviewSave}
              onReviewDismiss={handleReviewDismiss}
              onAdd={handleAdd}
              onDismiss={handleDismiss}
              onOpenViewport={setTurnstyleResults}
              onConfirmAllItems={handleConfirmAllItems}
              onConfirmAllTokens={handleConfirmAllTokens}
              pendingTokenCount={pendingTokens.length}
              pendingTokenActions={pendingTokens}
              actionsDisabled={loading}
              onTogglePin={handleToggleWatchlistPin}
              onRecommend={multiUserEnabled ? handleRecommendTitle : undefined}
              watchlistLookup={watchlistLookup}
              requestPath={requestPath}
              userRole={userRole}
              multiUserEnabled={multiUserEnabled}
              showErrors={false}
              draggableToDock={dockDropEnabled}
              onReviewConflictResolved={handleReviewConflictResolved}
            />
            {quickPickLoading || quickPick ? (
              <div ref={quickPickAnchorRef} data-testid="quick-pick-anchor">
                <QuickPickCard
                  item={quickPick?.item}
                  why={quickPick?.why}
                  status={quickPick?.status}
                  message={quickPick?.message}
                  loading={quickPickLoading}
                  onRetry={handleQuickPick}
                  onTellMore={
                    quickPick?.item?.title
                      ? () => sendMessage(`Tell me more about ${quickPick.item.title}`)
                      : undefined
                  }
                  onAdd={handleAdd}
                  onDismiss={() => setQuickPick(null)}
                  requestPath={requestPath}
                  userRole={userRole}
                  multiUserEnabled={multiUserEnabled}
                />
              </div>
            ) : null}
            {loading || agentActivityLog.length > 0 ? (
              <TypingIndicator
                label={
                  loading
                    ? typingLabel || `${curatorName} is thinking`
                    : "Agent activity"
                }
                activityLog={agentActivityLog}
                expanded={activityPanelOpen}
                onToggle={() => setActivityPanelOpen((open) => !open)}
                interactive
                streaming={loading}
              />
            ) : null}
            <NewReplyChip visible={showNewReplyChip} onClick={() => scrollToLatestTurn("smooth")} />
          </div>

          <form
            className="composer composer-raised"
            onSubmit={(event) => {
              event.preventDefault();
              sendMessage(input);
            }}
          >
            <div className="composer-shell">
              <span className="ambient-context-tag" data-testid="ambient-context-tag">
                ⧉ {contextLabel}
              </span>
              <InlineAlert type="error" message={chatError} />
              <div className="composer-chrome" data-testid="composer-chrome">
                <textarea
                  ref={composerRef}
                  data-testid="composer-input"
                  value={input}
                  onChange={(event) => setInput(event.target.value)}
                  onKeyDown={(event) => {
                    if (!konamiTrackerRef.current) {
                      konamiTrackerRef.current = createKonamiTracker((kind) => {
                        const name = persona?.curator_name || "Curator";
                        const eggMessage = {
                          id: createId(),
                          role: "assistant",
                          blocks: [{ type: "text", content: easterEggResponse(kind, name) }],
                        };
                        setMessages((prev) => [...prev, eggMessage]);
                        speakAssistantMessage(eggMessage);
                      });
                    }
                    konamiTrackerRef.current(event);

                    const canSubmit = Boolean(input.trim()) && !loading && threadsReady;
                    if (shouldSubmitComposerOnEnter(event, { canSubmit })) {
                      event.preventDefault();
                      sendMessage(input);
                      return;
                    }
                    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
                      event.preventDefault();
                    }
                  }}
                  placeholder={
                    voiceListening
                      ? "Listening…"
                      : composerPlaceholder || "Describe what you're hunting for…"
                  }
                  rows={2}
                  disabled={loading || !threadsReady}
                />
                <div className="composer-toolbar">
                  <div className="composer-toolbar-left">
                    {personas.length > 0 ? (
                      <PersonaSelector
                        personas={personas}
                        activePersonaId={activePersonaId}
                        onSelect={setActivePersonaId}
                        onCreate={handleCreatePersona}
                        onUpdate={handleUpdatePersona}
                        onDelete={handleDeletePersona}
                        onSetDefault={handleSetDefaultPersona}
                        defaultPersonaId={defaultPersonaId}
                      />
                    ) : null}
                  </div>
                  <div className="composer-toolbar-right">
                    {showMic ? (
                      <button
                        type="button"
                        className={`composer-mic ghost ${voiceListening ? "is-listening" : ""}`}
                        data-testid="composer-mic"
                        aria-label={voiceListening ? "Stop dictation" : "Dictate with microphone"}
                        aria-pressed={voiceListening}
                        title={voiceListening ? "Stop dictation" : "Dictate"}
                        disabled={loading || !threadsReady}
                        onClick={toggleListening}
                      >
                        <svg
                          className="composer-mic-icon"
                          width="18"
                          height="18"
                          viewBox="0 0 24 24"
                          fill="none"
                          aria-hidden="true"
                        >
                          <path
                            d="M12 14a3 3 0 0 0 3-3V6a3 3 0 1 0-6 0v5a3 3 0 0 0 3 3Z"
                            fill="currentColor"
                          />
                          <path
                            d="M17.5 11a5.5 5.5 0 0 1-11 0"
                            stroke="currentColor"
                            strokeWidth="1.8"
                            strokeLinecap="round"
                          />
                          <path
                            d="M12 16.5V20"
                            stroke="currentColor"
                            strokeWidth="1.8"
                            strokeLinecap="round"
                          />
                        </svg>
                      </button>
                    ) : null}
                    {voiceSpeaking || ttsMuted ? (
                      <button
                        type="button"
                        className={`composer-tts-mute ghost ${ttsMuted ? "is-muted" : ""}`}
                        data-testid="composer-tts-mute"
                        aria-label={ttsMuted ? "Unmute spoken replies" : "Mute spoken reply"}
                        aria-pressed={ttsMuted}
                        title={ttsMuted ? "Unmute replies" : "Mute reply"}
                        onClick={() => {
                          if (ttsMuted) unmuteTts();
                          else muteTts();
                        }}
                      >
                        {ttsMuted ? "Unmute" : "Mute"}
                      </button>
                    ) : null}
                    <button
                      type="button"
                      className={`composer-surprise ghost ${quickPickLoading ? "is-loading" : ""}`}
                      data-testid="surprise-me-button"
                      disabled={loading || !threadsReady || quickPickLoading}
                      aria-busy={quickPickLoading}
                      aria-label={quickPickLoading ? "Picking a surprise…" : "Surprise me"}
                      title="Surprise me — random pick"
                      onClick={handleQuickPick}
                    >
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                        <rect x="3" y="3" width="18" height="18" rx="3" stroke="currentColor" strokeWidth="1.8" />
                        <circle cx="8.5" cy="8.5" r="1.5" fill="currentColor" />
                        <circle cx="15.5" cy="8.5" r="1.5" fill="currentColor" />
                        <circle cx="8.5" cy="15.5" r="1.5" fill="currentColor" />
                        <circle cx="15.5" cy="15.5" r="1.5" fill="currentColor" />
                        <circle cx="12" cy="12" r="1.5" fill="currentColor" />
                      </svg>
                    </button>
                    <button
                      type="submit"
                      className="composer-send"
                      data-testid="send-button"
                      disabled={loading || !threadsReady || !input.trim()}
                      aria-label="Send"
                      title="Send"
                    >
                      <svg
                        className="composer-send-icon"
                        width="18"
                        height="18"
                        viewBox="0 0 24 24"
                        fill="none"
                        aria-hidden="true"
                      >
                        <path
                          d="M12 19V5M12 5l-5.5 5.5M12 5l5.5 5.5"
                          stroke="currentColor"
                          strokeWidth="2.2"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        />
                      </svg>
                    </button>
                  </div>
                </div>
              </div>
              {voiceStatus ? (
                <p className="composer-voice-status status status-secondary" data-testid="composer-voice-status">
                  {voiceStatus}
                </p>
              ) : null}
            </div>
          </form>
        </main>
      </div>

      {turnstyleResults ? (
        <TurnstyleResultsOverlay
          payload={turnstyleResults}
          onClose={() => setTurnstyleResults(null)}
          onAdd={handleAdd}
          onDismiss={handleDismiss}
          onConfirmAllItems={handleConfirmAllItems}
          onTogglePin={handleToggleWatchlistPin}
          watchlistLookup={watchlistLookup}
          actionsDisabled={loading}
          requestPath={requestPath}
          userRole={userRole}
          multiUserEnabled={multiUserEnabled}
          draggableToDock={dockDropEnabled}
        />
      ) : null}

      <KeyboardHelpModal
        open={keyboardHelpOpen}
        onClose={() => setKeyboardHelpOpen(false)}
        plexCollectionsEnabled={Boolean(features?.features?.plex_collections_enabled)}
      />

      <RecommendModal
        item={recommendItem}
        open={Boolean(recommendItem)}
        onClose={() => setRecommendItem(null)}
      />

      <footer className="app-footer" data-testid="app-footer">
        <Link to="/help" className="app-footer-link">Help</Link>
        <span className="app-footer-sep">·</span>
        <Link to="/privacy" className="app-footer-link">Privacy</Link>
        <span className="app-footer-sep">·</span>
        <Link to="/about" className="app-footer-link">About</Link>
      </footer>
    </div>
  );
}
