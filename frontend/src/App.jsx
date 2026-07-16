import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  api,
  addWatchlistPin,
  confirmAction,
  createThread,
  dismissReviewPrompt,
  formatApiError,
  getActiveContext,
  getEngagementStreak,
  getFeatures,
  getThreadFeedback,
  getThreadMessages,
  getTypingPhrases,
  listJobs,
  listReviewPrompts,
  listReviews,
  listThreads,
  listWatchlist,
  proposeAction,
  removeWatchlistPin,
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
import { agentPulseTitle, resolveAgentPulse } from "./lib/agentPulse.js";
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
import {
  createKonamiTracker,
  easterEggAlreadyFired,
  easterEggResponse,
  isReversedCuratorName,
  markEasterEggFired,
  resolveDockDropTarget,
} from "./lib/easterEggs.js";
import { extractSpeakableText } from "./lib/voiceSpeech.js";
import { buildWatchlistLookup } from "./lib/watchlistKeys.js";
import ChatThread from "./components/ChatThread";
import InlineAlert from "./components/InlineAlert";
import PersonaSelector from "./components/PersonaSelector";
import KeyboardHelpModal from "./components/KeyboardHelpModal";
import NewReplyChip from "./components/NewReplyChip";
import StatusDock from "./components/StatusDock";
import ThreadList from "./components/ThreadList";
import TurnstyleResultsOverlay from "./components/TurnstyleResultsOverlay";
import TypingIndicator from "./components/TypingIndicator";
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
  const { authReady, multiUserEnabled, isOwner } = useAuthGate();
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
  const [watchlistOpen, setWatchlistOpen] = useState(false);
  const [sessionStreak, setSessionStreak] = useState(0);
  const [reviewPrompts, setReviewPrompts] = useState([]);
  const [reviewLookup, setReviewLookup] = useState({});
  const [typingPhrases, setTypingPhrases] = useState([]);
  const [typingLabel, setTypingLabel] = useState("");
  const [composerPlaceholder, setComposerPlaceholder] = useState("");
  const [nightOwl, setNightOwl] = useState(isNightOwlHour);
  const [anniversaries, setAnniversaries] = useState([]);
  const [libraryGlance, setLibraryGlance] = useState(null);
  const [glanceShown, setGlanceShown] = useState(false);
  const [quickPick, setQuickPick] = useState(null);
  const [personas, setPersonas] = useState([]);
  const [activePersonaId, setActivePersonaId] = useState(null);
  const [defaultPersonaId, setDefaultPersonaId] = useState(null);
  const helpfulCountRef = useRef(0);
  const perfectPickPendingRef = useRef(false);
  const jobsRunningRef = useRef(false);
  const composerRef = useRef(null);
  const konamiTrackerRef = useRef(null);
  const inputRef = useRef("");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    try {
      return sessionStorage.getItem(SIDEBAR_RAIL_KEY) === "true";
    } catch {
      return false;
    }
  });
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

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
    listWatchlist()
      .then((data) => setWatchlistPins(data.items || []))
      .catch(console.error);
  }, []);

  const refreshStreak = useCallback(() => {
    getEngagementStreak()
      .then((data) => setSessionStreak(data.session_count_30d || 0))
      .catch(console.error);
  }, []);

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
      if (def) setDefaultPersonaId(def.id);
      return list;
    } catch (error) {
      console.error(error);
      return [];
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
      setThreadsReady(true);
    }

    initializeThreads().catch(console.error);
  }, [loadThreadMessages, refreshThreads]);

  useEffect(() => {
    Promise.all([
      api("/setup/status").then(setSetup),
      api("/library/stats").then(setStats),
      api("/persona").then(setPersona).catch(console.error),
      getFeatures().then(setFeatures).catch(console.error),
      refreshReviewData(),
      getActiveContext()
        .then(setActiveContext)
        .catch(() => setActiveContext({ context_hash: "general", inferred_label: "General Exploration" })),
    ]).catch(console.error);
    api("/library/anniversaries").then((res) => setAnniversaries(res?.items || [])).catch(() => {});
    api("/system-config").then((cfg) => {
      if (cfg?.library_glance_shown === "true") setGlanceShown(true);
    }).catch(() => {});
    refreshJobs();
    refreshWatchlist();
    refreshStreak();
    refreshTypingPhrases();
    refreshPersonas();
    const interval = setInterval(refreshJobs, 5000);
    const nightInterval = setInterval(() => setNightOwl(isNightOwlHour()), 60_000);
    return () => {
      clearInterval(interval);
      clearInterval(nightInterval);
    };
  }, [refreshJobs, refreshPersonas, refreshReviewData, refreshStreak, refreshTypingPhrases, refreshWatchlist]);

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
    setTypingLabel(pickRandomPhrase(typingPhrases, fallback));
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
    const list = await refreshPersonas();
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
    try {
      const result = await api("/library/quick-pick");
      if (result?.item) {
        setQuickPick(result);
      }
    } catch {
      // graceful degradation
    }
  }

  async function sendMessage(text) {
    if (!text.trim() || loading) return;
    stopVoiceListening();
    stopTts();
    setLoading(true);
    setChatError("");
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
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === streamPlaceholderId
                ? { ...msg, blocks: [{ type: "text", content: snapshot }] }
                : msg,
            ),
          );
        },
        onToolCall: ({ name, status }) => {
          if (status === "start") {
            const label = name.replace(/_/g, " ");
            setTypingLabel(`Searching ${label}…`);
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
        },
      });
    } catch (error) {
      if (!streamFailed) {
        setMessages((prev) => prev.filter((msg) => msg.id !== streamPlaceholderId));
        appendChatError(formatApiError(error));
      }
    } finally {
      setLoading(false);
    }
  }

  function handleAdd(item, target) {
    setAddFeedback(null);
    setPendingBulk(null);
    setPendingTokens([]);
    setPendingAdd({ item, target });
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
    const label = item.title || "this title";
    const service = serviceLabelForTarget(target);
    const body = buildProposeActionBody(item, target);

    setAddInProgress(true);
    try {
      const proposal = await proposeAction(body);
      if (isAlreadyInArr(proposal)) {
        setAddFeedback({
          type: "success",
          message: alreadyInArrMessage(proposal, { label, service }),
        });
        setPendingAdd(null);
        return;
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
      setPendingAdd(null);
    } catch (error) {
      setAddFeedback({ type: "error", message: formatApiError(error) });
    } finally {
      setAddInProgress(false);
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
  const agentPulseLabel = agentPulseTitle(agentPulse, chatError);
  const curatorName = persona?.curator_name || "Curator";
  const presetTagline = personaUi?.preset_tagline || "";
  const radarrConnected = Boolean(setup?.checks?.radarr?.ok);
  const sonarrConnected = Boolean(setup?.checks?.sonarr?.ok);
  const dockDropEnabled =
    requestPath !== "seerr" && (radarrConnected || sonarrConnected);
  const personaLookup = useMemo(
    () => Object.fromEntries(personas.map((p) => [p.id, p])),
    [personas],
  );
  const watchlistLookup = buildWatchlistLookup(watchlistPins);
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
      <header className={`app-topbar ${nightOwl ? "night-owl" : ""}`}>
        <div className="app-topbar-brand">
          <button
            type="button"
            className="app-topbar-menu ghost"
            data-testid="mobile-nav-toggle"
            aria-label="Open conversations"
            aria-expanded={mobileNavOpen}
            aria-controls="workspace-sidebar"
            onClick={() => setMobileNavOpen(true)}
          >
            <span aria-hidden="true">☰</span>
          </button>
          <div className="app-topbar-titles">
            <h1>CuratorX</h1>
            <p
              className="app-topbar-eyebrow"
              title={presetTagline || undefined}
              data-testid="curator-name-eyebrow"
            >
              {curatorName}
            </p>
          </div>
          <span
            className={`agent-pulse ${agentPulse}`}
            title={agentPulseLabel}
            aria-label={agentPulseLabel}
            data-testid="agent-pulse"
          />
        </div>
        <div className="app-topbar-actions">
          {stats ? (
            <span className="stat-chip app-topbar-meta" data-testid="library-stats-chip">
              {stats.movies} movies · {stats.shows} shows
            </span>
          ) : null}
          {sessionStreak >= 3 ? (
            <span className="stat-chip streak-chip app-topbar-meta" data-testid="curator-streak-chip" title="Conversations in the last 30 days">
              {sessionStreak} chats this month
            </span>
          ) : null}
          {watchlistPins.length ? (
            <button
              type="button"
              className="stat-chip watchlist-chip app-topbar-meta"
              data-testid="watchlist-topbar-chip"
              title="Watchlist pins — click to toggle panel"
              onClick={() => setWatchlistOpen((open) => !open)}
            >
              ★ {watchlistPins.length} pinned
            </button>
          ) : null}
          {isOwner ? (
            <Link to="/admin" className="app-topbar-link" data-testid="topbar-admin-link">
              Admin
            </Link>
          ) : null}
          <Link to="/settings" className="app-topbar-link" data-testid="topbar-settings-link">
            Settings
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
          <div className="workspace-sidebar-scroll">
            <ThreadList
              threads={threads}
              activeSessionId={activeSessionId}
              onSelect={switchThread}
              onCreate={handleCreateThread}
              hideHeader
              personaLookup={personaLookup}
            />
          </div>
          <WatchlistPanel
            pins={watchlistPins}
            open={watchlistOpen}
            onToggle={() => setWatchlistOpen((open) => !open)}
            onRemove={(pin) => handleToggleWatchlistPin(pin, pin)}
          />
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
            {showWelcomePanel ? (
              <>
                {anniversaries.length > 0 ? (
                  <OnThisDayCard items={anniversaries} accentColor={personaUi?.accent_hue} />
                ) : null}
                <WelcomePanel
                  curatorName={curatorName}
                  greeting={personaUi?.welcome_greeting}
                  starters={personaUi?.welcome_starters}
                  onStarterSelect={sendMessage}
                />
              </>
            ) : null}
            {libraryGlance && !glanceShown ? (
              <LibraryGlanceCard snapshot={libraryGlance} onDismiss={handleDismissGlance} />
            ) : null}
            {quickPick?.item ? (
              <QuickPickCard
                item={quickPick.item}
                why={quickPick.why}
                onRetry={handleQuickPick}
                onTellMore={() => sendMessage(`Tell me more about ${quickPick.item.title}`)}
                onAdd={handleAdd}
                onDismiss={() => setQuickPick(null)}
                requestPath={requestPath}
              />
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
              actionsDisabled={addInProgress}
              onTogglePin={handleToggleWatchlistPin}
              watchlistLookup={watchlistLookup}
              requestPath={requestPath}
              showErrors={false}
              draggableToDock={dockDropEnabled}
              onReviewConflictResolved={handleReviewConflictResolved}
            />
            {loading && !messages.some((m) => m._streaming && m.blocks?.[0]?.content) ? (
              <TypingIndicator label={typingLabel || `${curatorName} is thinking`} />
            ) : null}
            <NewReplyChip visible={showNewReplyChip} onClick={() => scrollToLatestTurn("smooth")} />
          </div>

          <form
            className="composer"
            onSubmit={(event) => {
              event.preventDefault();
              sendMessage(input);
            }}
          >
            <span className="ambient-context-tag" data-testid="ambient-context-tag">
              ⧉ {contextLabel}
            </span>
            <InlineAlert type="error" message={chatError} />
            <div className="composer-row">
              {personas.length > 0 && (
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
              )}
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
                className="composer-surprise ghost"
                data-testid="surprise-me-button"
                disabled={loading || !threadsReady}
                aria-label="Surprise me"
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
                    d="M3.4 20.4 21 12 3.4 3.6v6.6L15 12 3.4 13.8v6.6Z"
                    fill="currentColor"
                  />
                </svg>
              </button>
            </div>
            {voiceStatus ? (
              <p className="composer-voice-status status status-secondary" data-testid="composer-voice-status">
                {voiceStatus}
              </p>
            ) : null}
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
          actionsDisabled={addInProgress}
          requestPath={requestPath}
          draggableToDock={dockDropEnabled}
        />
      ) : null}

      <KeyboardHelpModal
        open={keyboardHelpOpen}
        onClose={() => setKeyboardHelpOpen(false)}
        plexCollectionsEnabled={Boolean(features?.features?.plex_collections_enabled)}
      />

      <footer className="app-footer" data-testid="app-footer">
        <Link to="/privacy" className="app-footer-link">Privacy</Link>
        <span className="app-footer-sep">·</span>
        <Link to="/about" className="app-footer-link">About</Link>
      </footer>
    </div>
  );
}
