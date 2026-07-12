import { useCallback, useEffect, useRef, useState } from "react";
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
  resolveAgentPulse,
  saveReview,
  sendChat,
  sessionId,
  setActiveSession,
  submitMessageFeedback,
} from "./api/client";
import {
  alreadyInArrMessage,
  buildProposeActionBody,
  isAlreadyInArr,
  normalizePendingTokens,
  requestPathFromFeatures,
  serviceLabelForTarget,
  tokenConfirmFailureMessage,
  tokenConfirmSuccessMessage,
} from "./lib/addActions.js";
import { blendAmbientAccent } from "./lib/ambientAccent.js";
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
import { buildWatchlistLookup } from "./lib/watchlistKeys.js";
import ChatThread from "./components/ChatThread";
import InlineAlert from "./components/InlineAlert";
import KeyboardHelpModal from "./components/KeyboardHelpModal";
import NewReplyChip from "./components/NewReplyChip";
import StatusDock from "./components/StatusDock";
import ThreadList from "./components/ThreadList";
import TurnstyleResultsOverlay from "./components/TurnstyleResultsOverlay";
import TypingIndicator from "./components/TypingIndicator";
import WelcomePanel from "./components/WelcomePanel";
import UserMenu, { useAuthGate } from "./components/UserMenu";
import { reviewPromptBlock } from "./components/ReviewPromptCard";
import useChatScroll from "./hooks/useChatScroll";
import useKeyboardShortcuts from "./hooks/useKeyboardShortcuts";

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
  const { authReady, multiUserEnabled } = useAuthGate();
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
  const helpfulCountRef = useRef(0);
  const perfectPickPendingRef = useRef(false);
  const jobsRunningRef = useRef(false);
  const composerRef = useRef(null);
  const konamiTrackerRef = useRef(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    try {
      return sessionStorage.getItem(SIDEBAR_RAIL_KEY) === "true";
    } catch {
      return false;
    }
  });

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
      await loadThreadMessages(session);
    },
    [activeSessionId, loadThreadMessages]
  );

  const handleCreateThread = useCallback(async () => {
    try {
      const created = await createThread();
      const nextId = created.session_id;
      setActiveSession(nextId);
      setActiveSessionId(nextId);
      setMessages([]);
      setMessageFeedback({});
      setChatError("");
      await refreshThreads();
    } catch (error) {
      console.error(error);
    }
  }, [refreshThreads]);

  useKeyboardShortcuts({
    composerRef,
    onNewThread: handleCreateThread,
    onCloseOverlay: () => setTurnstyleResults(null),
    onShowHelp: () => setKeyboardHelpOpen(true),
    overlayOpen: Boolean(turnstyleResults),
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
    refreshJobs();
    refreshWatchlist();
    refreshStreak();
    refreshTypingPhrases();
    const interval = setInterval(refreshJobs, 5000);
    const nightInterval = setInterval(() => setNightOwl(isNightOwlHour()), 60_000);
    return () => {
      clearInterval(interval);
      clearInterval(nightInterval);
    };
  }, [refreshJobs, refreshReviewData, refreshStreak, refreshTypingPhrases, refreshWatchlist]);

  useEffect(() => {
    const running = jobs.some((job) => job.status === "running" || job.status === "queued");
    if (jobsRunningRef.current && !running) {
      refreshReviewData();
    }
    jobsRunningRef.current = running;
  }, [jobs, refreshReviewData]);

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

  async function sendMessage(text) {
    if (!text.trim() || loading) return;
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
      setMessages((prev) => [
        ...prev,
        {
          id: createId(),
          role: "assistant",
          blocks: [{ type: "text", content: easterEggResponse("reversed_name", curatorName) }],
        },
      ]);
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

    try {
      const result = await sendChat(text, "general", { sessionId: activeSessionId });
      if (!result?.message?.blocks?.length) {
        appendChatError(
          "The curator returned no content blocks. Check your LLM provider, API key, and model in Settings."
        );
        return;
      }
      let assistantMessage = result.message;
      if (perfectPickPendingRef.current) {
        assistantMessage = appendPerfectPickAck(assistantMessage);
        perfectPickPendingRef.current = false;
        helpfulCountRef.current = 0;
      }
      setMessages((prev) => [...prev, assistantMessage]);
      setPendingTokens(normalizePendingTokens(result.pending_tokens));
      if (Array.isArray(result.pending_tokens) && result.pending_tokens.length >= 2) {
        setPendingBulk(null);
        setPendingAdd(null);
      }
      refreshJobs();
      refreshThreads();
      getActiveContext()
        .then(setActiveContext)
        .catch(() => {});
    } catch (error) {
      appendChatError(formatApiError(error));
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
    setPendingBulk({ items, target });
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
    await saveReview({
      stars,
      title: prompt.title,
      media_type: prompt.media_type,
      rating_key: prompt.rating_key,
      review_text: reviewText,
      prompted_by: slashRate ? "slash_rate" : "near_complete",
      session_id: reviewSessionId || activeSessionId,
      prompt_id: slashRate ? undefined : prompt.id,
      replace_plex_rating: Boolean(replacePlexRating),
    });
    if (!slashRate) {
      setReviewPrompts((current) => current.filter((entry) => entry.id !== prompt.id));
    }
    refreshReviewData();
  }

  async function handleReviewDismiss(prompt) {
    if (!String(prompt.id || "").startsWith("slash-rate-")) {
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

  const agentPulse = resolveAgentPulse(jobs);
  const curatorName = persona?.curator_name || "Curator";
  const presetTagline = personaUi?.preset_tagline || "";
  const radarrConnected = Boolean(setup?.checks?.radarr?.ok);
  const sonarrConnected = Boolean(setup?.checks?.sonarr?.ok);
  const dockDropEnabled =
    requestPath !== "seerr" && (radarrConnected || sonarrConnected);
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
          <div className="app-topbar-titles">
            <p
              className="eyebrow app-topbar-eyebrow"
              title={presetTagline || undefined}
              data-testid="curator-name-eyebrow"
            >
              {curatorName}
            </p>
            <h1>CuratorX</h1>
          </div>
          <span className={`agent-pulse ${agentPulse}`} title={`Agent ${agentPulse}`} data-testid="agent-pulse" />
        </div>
        <div className="app-topbar-actions">
          {stats ? (
            <span className="stat-chip" data-testid="library-stats-chip">
              {stats.movies} movies · {stats.shows} shows
            </span>
          ) : null}
          {sessionStreak >= 3 ? (
            <span className="stat-chip streak-chip" data-testid="curator-streak-chip" title="Conversations in the last 30 days">
              {sessionStreak} chats this month
            </span>
          ) : null}
          {watchlistPins.length ? (
            <button
              type="button"
              className="stat-chip watchlist-chip"
              data-testid="watchlist-topbar-chip"
              onClick={() => setWatchlistOpen((open) => !open)}
            >
              ★ {watchlistPins.length} pinned
            </button>
          ) : null}
          <Link to="/config" className="app-topbar-link">
            Config
          </Link>
          {multiUserEnabled ? <UserMenu /> : null}
        </div>
      </header>

      {setup && !setup.onboarding_complete ? (
        <div className="banner workspace-banner" data-testid="setup-banner">
          Finish setup in <Link to="/config">Settings</Link> to connect Plex, TMDB, and your LLM provider.
        </div>
      ) : null}

      <div className="workspace-body">
        <aside
          className={`workspace-sidebar ${sidebarCollapsed ? "sidebar-collapsed" : ""}`}
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
            />
          </div>
          <StatusDock
            jobs={jobs}
            jobStatusPhrases={personaUi?.job_status_phrases}
            pendingAdd={pendingAdd}
            pendingBulk={pendingBulk}
            pendingTokens={pendingTokens.length >= 2 ? pendingTokens : null}
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
              <WelcomePanel
                curatorName={curatorName}
                greeting={personaUi?.welcome_greeting}
                starters={personaUi?.welcome_starters}
                onStarterSelect={sendMessage}
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
            {loading ? <TypingIndicator label={typingLabel || `${curatorName} is thinking`} /> : null}
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
            <textarea
              ref={composerRef}
              data-testid="composer-input"
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (!konamiTrackerRef.current) {
                  konamiTrackerRef.current = createKonamiTracker((kind) => {
                    const name = persona?.curator_name || "Curator";
                    setMessages((prev) => [
                      ...prev,
                      {
                        id: createId(),
                        role: "assistant",
                        blocks: [{ type: "text", content: easterEggResponse(kind, name) }],
                      },
                    ]);
                  });
                }
                konamiTrackerRef.current(event);
              }}
              placeholder={composerPlaceholder || "Describe what you're hunting for…"}
              rows={2}
              disabled={loading || !threadsReady}
            />
            <button type="submit" data-testid="send-button" disabled={loading || !threadsReady || !input.trim()}>
              {loading ? "Thinking…" : "Send"}
            </button>
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
    </div>
  );
}
