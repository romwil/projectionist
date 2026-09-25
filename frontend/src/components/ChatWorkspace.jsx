import { Link } from "react-router-dom";
import ChatThread from "./ChatThread";
import InlineAlert from "./InlineAlert";
import PersonaSelector from "./PersonaSelector";
import KeyboardHelpModal from "./KeyboardHelpModal";
import NewReplyChip from "./NewReplyChip";
import RecommendModal from "./RecommendModal";
import StatusDock from "./StatusDock";
import PrimaryTopbar from "./PrimaryTopbar";
import ThreadList from "./ThreadList";
import TurnstyleResultsOverlay from "./TurnstyleResultsOverlay";
import TypingIndicator from "./TypingIndicator";
import UndoToast from "./UndoToast";
import WatchlistPanel from "./WatchlistPanel";
import WelcomePanel from "./WelcomePanel";
import WhisperInboxLink from "./WhisperInboxLink";
import SlashCommandPalette from "./SlashCommandPalette";
import OnThisDayCard from "./OnThisDayCard";
import LibraryGlanceCard from "./LibraryGlanceCard";
import { lastAssistantHasTitleCards } from "../lib/addActions.js";
import { shouldSubmitComposerOnEnter } from "../lib/composerKeyboard.js";
import { createId } from "../lib/id.js";
import { createKonamiTracker, easterEggResponse } from "../lib/easterEggs.js";
import { SURPRISE_MOOD_CHIPS } from "../lib/quickPick.js";

/**
 * Chat workspace chrome — topbar, sidebar, transcript, composer, overlays.
 * Extracted from App.jsx (H1 remaining shell carve after chatLayout).
 */
export default function ChatWorkspace({
authReady,
  isYouth,
  ambientAccent,
  isOwner,
  userRole,
  multiUserEnabled,
  seerrEnabled,
  liveChannelsReady,
  appNavOpen,
  setAppNavOpen,
  agentPulse,
  chatError,
  inboxUnreadCount,
  uiTheme,
  setUiTheme,
  nightOwl,
  mobileNavOpen,
  setMobileNavOpen,
  setup,
  sidebarCollapsed,
  handleCreateThread,
  toggleSidebarRail,
  threads,
  activeSessionId,
  switchThread,
  handleDeleteThread,
  personaLookup,
  undoToast,
  handleUndoDeleteThread,
  commitPendingDelete,
  stats,
  watchlistPins,
  jobs,
  personaUi,
  pendingAdd,
  pendingBulk,
  pendingTokens,
  messages,
  addInProgress,
  addProgress,
  addFeedback,
  confirmActiveAction,
  cancelActiveAction,
  dismissAddFeedback,
  dockDropEnabled,
  handleDockDrop,
  radarrConnected,
  sonarrConnected,
  scrollRef,
  showWelcomePanel,
  anniversaries,
  libraryGlance,
  glanceShown,
  handleDismissGlance,
  curatorName,
  sendMessage,
  homeChips,
  handleContextChip,
  shelfPages,
  displayMessages,
  reviewLookup,
  messageFeedback,
  handleMessageFeedbackChange,
  handleReviewSave,
  handleReviewDismiss,
  handleAdd,
  handleDismiss,
  setTurnstyleResults,
  handleConfirmAllItems,
  handleConfirmAllTokens,
  loading,
  handleToggleWatchlistPin,
  handleRecommendTitle,
  watchlistLookup,
  requestPath,
  handleReviewConflictResolved,
  handleSaveToLibrary,
  handleOpenAgentResultsGrid,
  agentActivityLog,
  typingLabel,
  activityPanelOpen,
  setActivityPanelOpen,
  showNewReplyChip,
  scrollToLatestTurn,
  input,
  contextLabel,
  showSlashPalette,
  slashPaletteItems,
  slashPaletteIndex,
  handleSlashPaletteSelect,
  setSlashPaletteIndex,
  composerRef,
  setInput,
  konamiTrackerRef,
  persona,
  setMessages,
  speakAssistantMessage,
  threadsReady,
  voiceListening,
  composerPlaceholder,
  personas,
  activePersonaId,
  setActivePersonaId,
  handleCreatePersona,
  handleUpdatePersona,
  handleDeletePersona,
  handleSetDefaultPersona,
  defaultPersonaId,
  showMic,
  toggleListening,
  voiceSpeaking,
  ttsMuted,
  unmuteTts,
  muteTts,
  surpriseMood,
  quickPickLoading,
  handleQuickPick,
  voiceStatus,
  turnstyleResults,
  keyboardHelpOpen,
  setKeyboardHelpOpen,
  features,
  recommendItem,
  setRecommendItem,
}) {
  if (!authReady) {
    return (
      <div className="app-root workspace app-loading" data-testid="app-auth-loading">
        <p className="login-lede">Loading…</p>
      </div>
    );
  }

  return (
    <div
      className={`app-root workspace${isYouth ? " app-root--youth youth-shell" : ""}`}
      style={{ "--ambient-accent": ambientAccent }}
      data-shell={isYouth ? "youth" : "default"}
    >
      <PrimaryTopbar
        showNavToggle
        isOwner={isOwner}
        isYouth={isYouth}
        role={userRole}
        multiUserEnabled={multiUserEnabled}
        seerrEnabled={seerrEnabled}
        authReady={authReady}
        liveChannelsReady={liveChannelsReady}
        navOpen={appNavOpen}
        onNavOpenChange={setAppNavOpen}
        brandPulse={agentPulse}
        chatError={chatError}
        inboxUnreadCount={inboxUnreadCount}
        uiTheme={uiTheme}
        onThemeChange={setUiTheme}
        className={`${nightOwl ? "night-owl" : ""} ${isYouth ? "youth-shell-topbar" : ""}`}
        leadingExtra={
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
              forum
            </span>
          </button>
        }
      />

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
              <WatchlistPanel count={watchlistPins.length} />
            </div>
          </div>
          <StatusDock
            jobs={jobs}
            jobStatusPhrases={personaUi?.job_status_phrases}
            pendingAdd={pendingAdd}
            pendingBulk={pendingBulk}
            pendingTokens={
              pendingTokens.length >= 1 && !lastAssistantHasTitleCards(messages)
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
                  contextChips={homeChips}
                  onContextChip={handleContextChip}
                />
                <WhisperInboxLink />
                {shelfPages.length ? (
                  <div className="holdable-shelf" data-testid="holdable-shelf">
                    {shelfPages.map((page) => (
                      <Link
                        key={page.id}
                        to={`/?saved_library=${encodeURIComponent(page.id)}`}
                        className="holdable-shelf-chip"
                        data-testid="holdable-shelf-chip"
                      >
                        {page.name}
                      </Link>
                    ))}
                  </div>
                ) : null}
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
              onSaveToLibrary={handleSaveToLibrary}
              onSuggestedReply={sendMessage}
              onCreateRail={({ prompt }) => sendMessage(prompt)}
              onOpenAsGrid={handleOpenAgentResultsGrid}
            />
            {loading || agentActivityLog.length > 0 ? (
              <TypingIndicator
                label={loading ? typingLabel || curatorName : "Agent activity"}
                activityLog={agentActivityLog}
                expanded={activityPanelOpen}
                onToggle={() => setActivityPanelOpen((open) => !open)}
                interactive
                streaming={loading}
              />
            ) : null}
          </div>
          <NewReplyChip visible={showNewReplyChip} onClick={() => scrollToLatestTurn("smooth")} />

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
                {showSlashPalette ? (
                  <SlashCommandPalette
                    items={slashPaletteItems}
                    activeIndex={slashPaletteIndex}
                    onSelect={handleSlashPaletteSelect}
                    onHover={setSlashPaletteIndex}
                  />
                ) : null}
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

                    if (showSlashPalette) {
                      if (event.key === "ArrowDown") {
                        event.preventDefault();
                        setSlashPaletteIndex((index) =>
                          Math.min(index + 1, slashPaletteItems.length - 1),
                        );
                        return;
                      }
                      if (event.key === "ArrowUp") {
                        event.preventDefault();
                        setSlashPaletteIndex((index) => Math.max(index - 1, 0));
                        return;
                      }
                      if (event.key === "Tab" || event.key === "Enter") {
                        const entry = slashPaletteItems[slashPaletteIndex];
                        if (entry) {
                          event.preventDefault();
                          handleSlashPaletteSelect(entry);
                          return;
                        }
                      }
                      if (event.key === "Escape") {
                        event.preventDefault();
                        setSlashPaletteIndex(0);
                        return;
                      }
                    }

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
                    <div className="composer-mood-row" data-testid="surprise-mood-chips">
                      {SURPRISE_MOOD_CHIPS.map((chip) => (
                        <button
                          key={chip.id}
                          type="button"
                          className={`composer-mood-chip ghost${surpriseMood === chip.id ? " is-active" : ""}`}
                          data-testid={`surprise-mood-${chip.id}`}
                          disabled={loading || !threadsReady || quickPickLoading}
                          aria-pressed={surpriseMood === chip.id}
                          aria-label={`Surprise me — ${chip.label} mood`}
                          title={`Surprise me with a ${chip.label.toLowerCase()} mood (this pick only)`}
                          onClick={() => handleQuickPick(chip.id)}
                        >
                          {chip.label}
                        </button>
                      ))}
                    </div>
                    <button
                      type="button"
                      className={`composer-surprise ghost ${quickPickLoading ? "is-loading" : ""}`}
                      data-testid="surprise-me-button"
                      disabled={loading || !threadsReady || quickPickLoading}
                      aria-busy={quickPickLoading}
                      aria-label={
                        quickPickLoading
                          ? "Picking a surprise…"
                          : surpriseMood
                            ? `Surprise me — ${surpriseMood} mood`
                            : "Surprise me"
                      }
                      title={
                        surpriseMood
                          ? `Surprise me — ${surpriseMood} mood (one-shot, no profile change)`
                          : "Surprise me — random pick"
                      }
                      onClick={() => handleQuickPick()}
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
    </div>
  );
}
