import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  addCuratedListItem,
  confirmAction,
  createCuratedList,
  createThread,
  deleteThread,
  formatApiError,
  getActiveContext,
  getFeatures,
  getLibraryPage,
  getThreadFeedback,
  getThreadMessages,
  listLibraryPages,
  listThreads,
  proposeAction,
  saveLibraryPage,
  createPersona,
  deletePersona,
  getPersonas,
  sendChatStream,
  sessionId,
  setActiveSession,
  setDefaultPersona,
  submitMessageFeedback,
  updatePersona,
} from "../api/client";
import {
  activityEventFromToolCall,
  appendActivityLog,
  createActivityEvent,
  nextActivityPanelExpanded,
} from "../lib/agentActivityLog.js";
import {
  addItemKey,
  withAddInFlight,
  withoutAddInFlight,
} from "../lib/addConcurrency.js";
import {
  alreadyInArrMessage,
  buildProposeActionBody,
  isAlreadyInArr,
  normalizePendingTokens,
  requestPathFromFeatures,
  serviceLabelForTarget,
  tokenConfirmFailureMessage,
  tokenConfirmSuccessMessage,
} from "../lib/addActions.js";
import { materializeAgentResultList } from "../lib/agentResultLists.js";
import { createId } from "../lib/id.js";
import { mergeStreamedBlocks } from "../lib/mergeStreamedBlocks.js";
import {
  hasPendingPersonaConsult,
  mergeThreadMessagesById,
  PERSONA_CONSULT_FIRST_POLL_MS,
  PERSONA_CONSULT_POLL_MS,
  PERSONA_CONSULT_POLL_WINDOW_MS,
  shouldSchedulePersonaConsultPoll,
} from "../lib/personaConsultPolling.js";
import { executeSlashCommand, parseSlashCommand } from "../lib/slashCommands.js";
import { resolveChatLauncherChipAction } from "../lib/chatLauncherChips.js";
import { holdableShelfPages } from "../lib/chatLayout.js";
import {
  filterSlashCommandPalette,
  formatSlashCommandInsert,
  shouldShowSlashCommandPalette,
} from "../lib/slashCommandPalette.js";
import {
  normalizeQuickPickError,
  normalizeQuickPickResult,
  quickPickMoodQuery,
  quickPickToAssistantMessage,
  resolveQuickPickMood,
} from "../lib/quickPick.js";
import { resolveActivePersonaId } from "../lib/resolveActivePersona.js";
import { preferYouthFriendlyPersona } from "../lib/youthPersona.js";
import {
  easterEggAlreadyFired,
  easterEggResponse,
  isReversedCuratorName,
  markEasterEggFired,
} from "../lib/easterEggs.js";
import {
  chatFromRailItems,
  chatFromRailPrompt,
  isRateFlowRequest,
  recommendLikePrompt,
  stripChatFromRailParam,
  stripRecommendLikeParam,
  stripRateFlowParam,
} from "../lib/backNav.js";
import { mergeRailSeedCards, takeRailSeed } from "../lib/railChatSeed.js";
import {
  ADD_FEEDBACK_DISMISS_MS,
  THREAD_DELETE_UNDO_MS,
  appendPerfectPickAck,
  chatErrorMessage,
} from "../lib/chatSession.js";

export default function useChatSession({
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
  setMobileNavOpen = () => {},
}) {
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
  const [addProgress, setAddProgress] = useState(null);
  const [addFeedback, setAddFeedback] = useState(null);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [chatError, setChatError] = useState("");
  const [activeContext, setActiveContext] = useState(null);
  const [typingLabel, setTypingLabel] = useState("");
  const [agentActivityLog, setAgentActivityLog] = useState([]);
  const [activityPanelOpen, setActivityPanelOpen] = useState(false);
  const [composerPlaceholder, setComposerPlaceholder] = useState("");
  const [quickPickLoading, setQuickPickLoading] = useState(false);
  const [surpriseMood, setSurpriseMood] = useState("");
  const [undoToast, setUndoToast] = useState(null);
  const [personas, setPersonas] = useState([]);
  const [activePersonaId, setActivePersonaId] = useState(null);
  const [defaultPersonaId, setDefaultPersonaId] = useState(null);
  const helpfulCountRef = useRef(0);
  const perfectPickPendingRef = useRef(false);
  const tokenNoteLoggedRef = useRef(false);
  const inputRef = useRef("");
  const pendingDeleteRef = useRef(null);
  const rateFlowStartedRef = useRef(false);
  const recommendLikeStartedRef = useRef(false);
  const chatFromRailStartedRef = useRef(false);
  const chatFromRailSeedRef = useRef(null);
  const savedLibraryStartedRef = useRef(false);
  const [slashPaletteIndex, setSlashPaletteIndex] = useState(0);
  const [savedShelf, setSavedShelf] = useState([]);

  inputRef.current = input;

  useEffect(() => {
    setSlashPaletteIndex(0);
  }, [input]);

  const plexCollectionsEnabled = Boolean(features?.features?.plex_collections_enabled);
  const slashPaletteItems = useMemo(
    () => filterSlashCommandPalette(input, { plexCollectionsEnabled }),
    [input, plexCollectionsEnabled],
  );
  const showSlashPalette =
    shouldShowSlashCommandPalette(input) && slashPaletteItems.length > 0 && !loading && threadsReady;
  const refreshPersonas = useCallback(async () => {
    try {
      const data = await getPersonas();
      const list = data.items || data || [];
      setPersonas(list);
      const def = list.find((p) => p.is_default);
      let nextDefaultId = def?.id ?? null;
      if (isYouth) {
        nextDefaultId = preferYouthFriendlyPersona(list, nextDefaultId);
      }
      setDefaultPersonaId(nextDefaultId);
      return { list, defaultPersonaId: nextDefaultId };
    } catch (error) {
      console.error(error);
      return { list: [], defaultPersonaId: null };
    }
  }, [isYouth]);

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

  const personaConsultPending = useMemo(
    () => hasPendingPersonaConsult(messages),
    [messages],
  );

  useEffect(() => {
    if (!personaConsultPending || loading || !activeSessionId) return undefined;
    let stopped = false;
    let timer;
    const deadline = Date.now() + PERSONA_CONSULT_POLL_WINDOW_MS;

    const poll = async () => {
      const pollStartedAt = Date.now();
      try {
        const data = await getThreadMessages(activeSessionId);
        if (!stopped) {
          setMessages((current) =>
            mergeThreadMessagesById(current, data.messages || []),
          );
        }
      } catch (error) {
        if (!error.message?.includes("Thread not found")) {
          console.error(error);
        }
      } finally {
        if (
          !stopped &&
          shouldSchedulePersonaConsultPoll({ pollStartedAt, deadline })
        ) {
          timer = setTimeout(poll, PERSONA_CONSULT_POLL_MS);
        }
      }
    };

    timer = setTimeout(poll, PERSONA_CONSULT_FIRST_POLL_MS);
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [activeSessionId, loading, personaConsultPending]);

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

  const refreshSavedShelf = useCallback(() => {
    listLibraryPages("")
      .then((pages) => setSavedShelf(holdableShelfPages(pages)))
      .catch(() => setSavedShelf([]));
  }, []);

  const handleSaveToLibrary = useCallback(
    async (message) => {
      const name =
        threads.find((thread) => thread.id === activeSessionId)?.thread_title || "Curator response";
      try {
        await saveLibraryPage({
          name,
          source_session_id: activeSessionId,
          source_message_id: message.id,
          content: { blocks: message.blocks },
        });
        refreshSavedShelf();
      } catch (error) {
        setChatError(formatApiError(error));
      }
    },
    [activeSessionId, refreshSavedShelf, threads],
  );
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
    refreshPersonas();
    refreshSavedShelf();
  }, [refreshPersonas, refreshSavedShelf]);

  useEffect(() => {
    if (!loading) return;
    // Neutral wait chip bound to the active thread persona — not a canned phrase lottery.
    const waitLabel = persona?.curator_name || "Curator";
    setTypingLabel(waitLabel);
    setAgentActivityLog((prev) => {
      if (prev.some((entry) => entry.kind === "status")) return prev;
      return appendActivityLog(prev, createActivityEvent({ kind: "status", label: "Working…" }));
    });
  }, [loading, persona?.curator_name]);

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
    const message = chatErrorMessage(reason, snark);
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

  async function handleQuickPick(moodOverride) {
    if (quickPickLoading) return;
    setQuickPickLoading(true);
    const mood = resolveQuickPickMood(moodOverride, surpriseMood);
    if (mood) setSurpriseMood(mood);
    try {
      const result = await api(`/library/quick-pick${quickPickMoodQuery(mood)}`);
      const message = {
        id: createId(),
        ...quickPickToAssistantMessage(normalizeQuickPickResult(result)),
      };
      setMessages((prev) => [...prev, message]);
      speakAssistantMessageRef.current?.(message);
      setSurpriseMood("");
    } catch (error) {
      const message = {
        id: createId(),
        ...quickPickToAssistantMessage(normalizeQuickPickError(error, formatApiError)),
      };
      setMessages((prev) => [...prev, message]);
      speakAssistantMessageRef.current?.(message);
    } finally {
      setQuickPickLoading(false);
    }
  }
  async function handleOpenAgentResultsGrid({ heading, items }) {
    const result = await materializeAgentResultList({
      heading,
      items,
      createList: createCuratedList,
      addItem: addCuratedListItem,
    });
    navigate(`/lists/${encodeURIComponent(result.list.id)}`);
    return result;
  }

  function handleContextChip(chip) {
    const action = resolveChatLauncherChipAction(chip);
    if (!action) return;
    if (action.type === "resume" && action.threadId) {
      switchThread(action.threadId);
      return;
    }
    if (action.type === "send") {
      sendMessage(action.prompt);
      return;
    }
    if (action.type === "prefill") {
      setInput(action.text);
      composerRef.current?.focus();
    }
  }

  function handleSlashPaletteSelect(entry) {
    setInput(formatSlashCommandInsert(entry.command));
    setSlashPaletteIndex(0);
    composerRef.current?.focus();
  }

  async function sendMessage(text) {
    if (!text.trim() || loading) return;
    stopVoiceListeningRef.current?.();
    stopTtsRef.current?.();
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
      speakAssistantMessageRef.current?.(eggMessage);
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
        speakAssistantMessageRef.current?.(assistantMessage);
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
          // Activity log stays factual; do not overwrite the persona wait chip with
          // mechanical "Searching…" / "is thinking" labels mid-turn.
          setAgentActivityLog((prev) =>
            appendActivityLog(prev, activityEventFromToolCall({ name, status, args, summary })),
          );
        },
        onDone: (data) => {
          let assistantMessage = mergeStreamedBlocks(data.message, streamAccumulated);
          const railSeed = chatFromRailSeedRef.current;
          if (railSeed?.length) {
            assistantMessage = mergeRailSeedCards(assistantMessage, railSeed);
            chatFromRailSeedRef.current = null;
          }
          if (perfectPickPendingRef.current) {
            assistantMessage = appendPerfectPickAck(assistantMessage);
            perfectPickPendingRef.current = false;
            helpfulCountRef.current = 0;
          }
          setMessages((prev) =>
            prev.map((msg) => (msg.id === streamPlaceholderId ? assistantMessage : msg)),
          );
          speakAssistantMessageRef.current?.(assistantMessage);
          setPendingTokens(normalizePendingTokens(data.pending_tokens));
          if (Array.isArray(data.pending_tokens) && data.pending_tokens.length >= 1) {
            setPendingBulk(null);
            setPendingAdd(null);
          }
          setAgentActivityLog((prev) =>
            appendActivityLog(prev, createActivityEvent({ kind: "status", label: "Response ready" })),
          );
          setActivityPanelOpen((open) => nextActivityPanelExpanded({ streamDone: true, expanded: open }));
          refreshJobs();
          if (data?.context_label) {
            setActiveContext((prev) => ({
              context_hash: prev?.context_hash || "general",
              inferred_label: String(data.context_label),
            }));
          }
          refreshThreads().then((threadList) => {
            const active = (threadList || []).find((thread) => thread.id === activeSessionId);
            if (active?.context_label) {
              setActiveContext({
                context_hash: active.context_hash || "general",
                inferred_label: active.context_label,
              });
              return;
            }
            if (!data?.context_label) {
              getActiveContext()
                .then(setActiveContext)
                .catch(() => {});
            }
          });
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
    const pageId = searchParams.get("saved_library");
    const followUp = searchParams.get("follow_up");
    if (!pageId) {
      savedLibraryStartedRef.current = false;
      return;
    }
    if (!authReady || !threadsReady || loading || savedLibraryStartedRef.current) return;
    savedLibraryStartedRef.current = true;
    searchParams.delete("saved_library");
    searchParams.delete("follow_up");
    setSearchParams(searchParams, { replace: true });
    getLibraryPage(pageId)
      .then((page) => {
        const source = JSON.stringify(page.content?.blocks || []).slice(0, 8000);
        const continuation = followUp ? `\n\nThe user selected this next step: ${followUp}` : "";
        return sendMessage(
          `Continue this saved curator response, keeping its recommendations and analysis as context:\n\n${source}${continuation}`,
        );
      })
      .catch((error) => appendChatError(formatApiError(error)));
  }, [authReady, threadsReady, loading, searchParams, setSearchParams]);

  useEffect(() => {
    if (!authReady || !threadsReady || loading || recommendLikeStartedRef.current) return;
    if (String(searchParams.get("from_rail") || "") === "1") return;
    const prompt = recommendLikePrompt(searchParams);
    if (!prompt) {
      recommendLikeStartedRef.current = false;
      return;
    }
    recommendLikeStartedRef.current = true;
    setSearchParams(stripRecommendLikeParam(searchParams), { replace: true });
    sendMessage(prompt);
  }, [authReady, threadsReady, loading, searchParams, setSearchParams]);

  useEffect(() => {
    if (!authReady || !threadsReady || loading || chatFromRailStartedRef.current) return;
    const prompt = chatFromRailPrompt(searchParams);
    if (!prompt) {
      chatFromRailStartedRef.current = false;
      return;
    }
    chatFromRailStartedRef.current = true;
    const packedItems = chatFromRailItems(searchParams);
    const stashed = takeRailSeed();
    chatFromRailSeedRef.current =
      stashed?.items?.length ? stashed.items : packedItems.length ? packedItems : null;
    setSearchParams(stripChatFromRailParam(searchParams), { replace: true });
    sendMessage(prompt);
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
    if (pendingTokens.length < 1 || addInProgress) return;
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
    const progressId = startBulkProgress({
      label: target === "seerr" ? "Requesting titles in Seerr" : `Adding titles to ${service}`,
      total: items.length,
      asynchronous: true,
    });

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
      } finally {
        updateBulkProgress(progressId, index + 1);
      }
    }

    setAddInProgress(false);
    setAddProgress(null);
    setPendingBulk(null);

    if (successCount === items.length) {
      const summary = target === "seerr"
        ? `Requested ${successCount} title${successCount === 1 ? "" : "s"} in Seerr.`
        : `Added ${successCount} title${successCount === 1 ? "" : "s"} to ${service}.`;
      finishBulkProgress(progressId, { label: summary });
      setAddFeedback({
        type: "success",
        message: summary,
      });
      return;
    }

    if (successCount > 0) {
      const summary = `Added ${successCount} of ${items.length} to ${service}. ${failures.length} failed.`;
      finishBulkProgress(progressId, { label: summary, state: "error" });
      setAddFeedback({
        type: "error",
        message: summary,
      });
      return;
    }

    const summary = failures[0]?.message || `Could not add titles to ${service}.`;
    finishBulkProgress(progressId, { label: summary, state: "error" });
    setAddFeedback({
      type: "error",
      message: summary,
    });
  }

  async function executeConfirmAllTokens() {
    const tokens = [...pendingTokens];
    let successCount = 0;
    const failures = [];

    setAddInProgress(true);
    setAddProgress({ current: 0, total: tokens.length });
    const progressId = startBulkProgress({
      label: "Confirming bulk actions",
      total: tokens.length,
      asynchronous: true,
    });

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
      } finally {
        updateBulkProgress(progressId, index + 1);
      }
    }

    setAddInProgress(false);
    setAddProgress(null);
    setPendingTokens([]);

    if (successCount === tokens.length) {
      const summary = tokenConfirmSuccessMessage(successCount, tokens);
      finishBulkProgress(progressId, { label: summary });
      setAddFeedback({
        type: "success",
        message: summary,
      });
      return;
    }

    if (successCount > 0) {
      const summary = `Confirmed ${successCount} of ${tokens.length}. ${failures.length} failed.`;
      finishBulkProgress(progressId, { label: summary, state: "error" });
      setAddFeedback({
        type: "error",
        message: summary,
      });
      return;
    }

    const summary = failures[0] || tokenConfirmFailureMessage(tokens);
    finishBulkProgress(progressId, { label: summary, state: "error" });
    setAddFeedback({
      type: "error",
      message: summary,
    });
  }

  async function confirmActiveAction() {
    if (pendingBulk) {
      await executeBulkAdd(pendingBulk.items, pendingBulk.target);
      return;
    }
    if (pendingTokens.length >= 1) {
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
    if (pendingTokens.length >= 1) {
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

  return {
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
    refreshSavedShelf,
    refreshThreads,
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
    executeSingleAdd,
    handleAdd,
    handleConfirmAllItems,
    handleConfirmAllTokens,
    cancelPendingBulk,
    cancelPendingTokens,
    cancelPendingAdd,
    confirmActiveAction,
    cancelActiveAction,
    confirmPendingAdd,
    dismissAddFeedback,
  };
}
