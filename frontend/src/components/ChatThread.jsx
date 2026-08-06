import { useState } from "react";
import { collectAddableFromMessage } from "../lib/addActions";
import {
  buildAgentRailPrompt,
  harvestResultListItems,
  lastMarkdownHeading,
} from "../lib/agentResultLists.js";
import { filterDisplayableCards, turnstyleItemCount } from "../lib/turnstyleItems.js";
import AgentAvatar from "./AgentAvatar";
import ReviewPromptCard from "./ReviewPromptCard";
import ReviewConflictBanner from "./ReviewConflictBanner";
import ConfirmAllButton from "./ConfirmAllButton";
import DoubleFeatureCard from "./DoubleFeatureCard";
import MessageReactions from "./MessageReactions";
import TitleCard from "./TitleCard";
import InlineAlert from "./InlineAlert";
import MessageText from "./MessageText";
import ShareActionMenu from "./ShareActionMenu";
import { chatMediaStripClassName } from "../lib/chatCardScroll.js";
import { titleRefsFromBlocks } from "../lib/titleDigIn.js";

function AgentResultListActions({ heading, items, handlers, disabled = false }) {
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const harvestItems = harvestResultListItems(heading, items);
  const harvestDisabled = harvestItems.length === 0;
  const controlDisabled = disabled || Boolean(busy) || harvestDisabled;
  const emptyGapHint = harvestDisabled
    ? "No gap cards to save — ask the agent to show missing titles as cards."
    : "";

  async function openGrid() {
    if (busy || disabled || harvestDisabled) return;
    setBusy("grid");
    setError("");
    try {
      await handlers.onOpenAsGrid?.({ heading, items: harvestItems });
    } catch (err) {
      setError(err.message || "Could not open these results as a grid.");
    } finally {
      setBusy("");
    }
  }

  function createRail() {
    if (busy || disabled || harvestDisabled) return;
    handlers.onCreateRail?.({
      heading,
      items: harvestItems,
      prompt: buildAgentRailPrompt({ heading, items: harvestItems }),
    });
  }

  return (
    <span className="agent-media-heading-tools" aria-label="Result list actions">
      <button
        type="button"
        className="agent-media-heading-action"
        aria-label="Create a rail from these results"
        title={emptyGapHint || "Create a rail"}
        disabled={controlDisabled}
        onClick={createRail}
      >
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M4 6h13M4 12h13M4 18h9M20 4v6M17 7h6" />
        </svg>
      </button>
      <button
        type="button"
        className="agent-media-heading-action"
        aria-label="Open these results as a grid"
        title={emptyGapHint || "Open as grid"}
        disabled={controlDisabled}
        onClick={openGrid}
      >
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <rect x="4" y="4" width="6" height="6" rx="1" />
          <rect x="14" y="4" width="6" height="6" rx="1" />
          <rect x="4" y="14" width="6" height="6" rx="1" />
          <rect x="14" y="14" width="6" height="6" rx="1" />
        </svg>
      </button>
      {busy === "grid" ? <span className="sr-only" role="status">Opening grid…</span> : null}
      {harvestDisabled ? (
        <span className="agent-media-heading-error" role="status">{emptyGapHint}</span>
      ) : null}
      {error ? <span className="agent-media-heading-error" role="alert">{error}</span> : null}
    </span>
  );
}

function renderBulkConfirmActions(message, handlers, showTokenConfirm, viewportBlock) {
  const { radarr, sonarr, seerr } = collectAddableFromMessage(message, {
    requestPath: handlers.requestPath,
    role: handlers.userRole,
    multiUserEnabled: handlers.multiUserEnabled,
  });
  const actions = [];

  if (showTokenConfirm && handlers.pendingTokenCount >= 1) {
    actions.push(
      <ConfirmAllButton
        key="tokens"
        count={handlers.pendingTokenCount}
        variant="tokens"
        tokenActions={handlers.pendingTokenActions}
        onClick={() => handlers.onConfirmAllTokens?.()}
        disabled={handlers.actionsDisabled}
      />
    );
  } else {
    if (seerr.length >= 2) {
      actions.push(
        <ConfirmAllButton
          key="seerr"
          count={seerr.length}
          target="seerr"
          onClick={() => handlers.onConfirmAllItems?.(seerr, "seerr")}
          disabled={handlers.actionsDisabled}
        />
      );
    }
    if (radarr.length >= 2) {
      actions.push(
        <ConfirmAllButton
          key="radarr"
          count={radarr.length}
          target="radarr"
          onClick={() => handlers.onConfirmAllItems?.(radarr, "radarr")}
          disabled={handlers.actionsDisabled}
        />
      );
    }
    if (sonarr.length >= 2) {
      actions.push(
        <ConfirmAllButton
          key="sonarr"
          count={sonarr.length}
          target="sonarr"
          onClick={() => handlers.onConfirmAllItems?.(sonarr, "sonarr")}
          disabled={handlers.actionsDisabled}
        />
      );
    }
  }

  if (viewportBlock) {
    const viewportItems = filterDisplayableCards(viewportBlock.payload?.items);
    const expandCount = turnstyleItemCount(viewportItems);
    actions.push(
      <button
        key="viewport"
        type="button"
        className="confirm-all-button viewport-expand-btn"
        data-testid="expand-title-cards"
        onClick={() =>
          handlers.onOpenViewport?.({
            ...viewportBlock.payload,
            items: viewportItems,
          })
        }
      >
        Expand {expandCount} titles in turnstyle view
      </button>
    );
  }

  return actions.length ? <div className="bulk-confirm-actions">{actions}</div> : null;
}

function enrichTitleCard(item, reviewLookup = {}) {
  if (!item || item.user_stars) return item;
  const key = item.rating_key || (item.tmdb_id ? `${item.media_type}:${item.tmdb_id}` : null);
  const stars = key ? reviewLookup[key] : undefined;
  if (!stars) return item;
  return { ...item, user_stars: stars };
}

function renderBlock(block, handlers, role, message, blockIndex, blocks, streaming) {
  const titleRefs = handlers.titleRefs || titleRefsFromBlocks(blocks);
  if (block.type === "text") {
    const nextBlock = blocks[blockIndex + 1];
    const nextItems = nextBlock?.type === "title_cards"
      ? filterDisplayableCards(nextBlock.items)
      : [];
    const heading = role === "assistant" && nextItems.length
      ? (String(nextBlock.heading || "").trim() || lastMarkdownHeading(block.content))
      : "";
    return (
      <MessageText
        content={block.content}
        markdown={role === "assistant"}
        titleRefs={titleRefs}
        headingActionLabel={heading}
        headingActions={heading ? (
          <AgentResultListActions
            heading={heading}
            items={nextItems}
            handlers={handlers}
            disabled={streaming || handlers.actionsDisabled}
          />
        ) : null}
      />
    );
  }
  if (block.type === "error") {
    return <MessageText content={block.content} className="message-text message-error-text" />;
  }
  if (block.type === "double_feature" && block.payload) {
    return (
      <DoubleFeatureCard
        titleA={block.payload.title_a}
        titleB={block.payload.title_b}
        bridgeText={block.payload.bridge_text}
        combinedRuntime={block.payload.combined_runtime}
        onAdd={handlers.onAdd}
        onDismiss={handlers.onDismiss}
        requestPath={handlers.requestPath}
        userRole={handlers.userRole}
        multiUserEnabled={handlers.multiUserEnabled}
      />
    );
  }
  if (block.type === "title_cards") {
    const items = filterDisplayableCards(block.items).map((item) =>
      enrichTitleCard(item, handlers.reviewLookup),
    );
    if (!items.length) return null;
    const isLastTitleCards = !blocks.slice(blockIndex + 1).some((entry) => entry.type === "title_cards");
    const nextViewport = blocks.slice(blockIndex + 1).find(
      (entry) => entry.type === "action_prompt" && entry.action === "open_viewport"
    );
    const prevBlock = blocks[blockIndex - 1];
    const sectionHeading = String(block.heading || "").trim();
    const precedingHeading = lastMarkdownHeading(prevBlock?.content);
    const actionHeading = sectionHeading || precedingHeading || "Results";
    // Text blocks already mount rail/grid on the following cards; only show chrome for
    // orphan / subsequent section-scoped card strips.
    const showActionsChrome = role === "assistant" && prevBlock?.type !== "text";
    return (
      <>
        {showActionsChrome ? (
          <div className="agent-media-heading agent-media-heading-fallback">
            <span>{actionHeading}</span>
            <AgentResultListActions
              heading={actionHeading}
              items={items}
              handlers={handlers}
              disabled={streaming || handlers.actionsDisabled}
            />
          </div>
        ) : null}
        <div className={chatMediaStripClassName("inline-cards", { streaming })}>
          {items.map((item) => (
            <TitleCard
              key={`${item.media_type}-${item.tmdb_id || item.tvdb_id || item.title}`}
              item={item}
              compact
              requestPath={handlers.requestPath}
              userRole={handlers.userRole}
              multiUserEnabled={handlers.multiUserEnabled}
              onAdd={handlers.onAdd}
              onDismiss={handlers.onDismiss}
              onTogglePin={item.card_kind === "purge" ? undefined : handlers.onTogglePin}
              onRecommend={handlers.onRecommend}
              pinRecord={handlers.watchlistLookup?.byItemKey?.get(
                `${item.media_type}:${item.tmdb_id ?? ""}:${item.tvdb_id ?? ""}`
              )}
              draggableToDock={handlers.draggableToDock}
            />
          ))}
        </div>
        {role === "assistant" && isLastTitleCards
          ? renderBulkConfirmActions(message, handlers, handlers.pendingTokenCount >= 1, nextViewport)
          : null}
      </>
    );
  }
  if (block.type === "persona_consult" && block.payload?.pending) {
    const name = String(block.payload.persona || "Curator").trim() || "Curator";
    return (
      <aside
        className="persona-consult-quote persona-consult-pending"
        data-testid="persona-consult-pending"
        data-persona={name}
        aria-label={`Waiting on ${name}`}
      >
        <p className="persona-consult-lead">{`Left a message for ${name}…`}</p>
        <p className="persona-consult-pending-copy">
          They may call back here with a separate addendum.
        </p>
      </aside>
    );
  }
  if (block.type === "persona_consult" && block.payload?.answer) {
    const name = String(block.payload.persona || "Curator").trim() || "Curator";
    const lead = String(block.payload.lead || `I asked ${name} and they said`).trim();
    const question = String(block.payload.question || "").trim();
    return (
      <aside
        className="persona-consult-quote"
        data-testid="persona-consult-quote"
        data-persona={name}
        data-specialty={block.payload.specialty || ""}
        aria-label={`Consulted ${name}`}
      >
        <p className="persona-consult-lead">{lead}…</p>
        <div className="persona-consult-answer">
          <MessageText content={block.payload.answer} markdown={role === "assistant"} titleRefs={titleRefs} />
        </div>
        {question ? (
          <details className="persona-consult-asked" data-testid="persona-consult-asked">
            <summary>{`What I asked ${name}`}</summary>
            <p className="persona-consult-asked-body">{question}</p>
          </details>
        ) : null}
      </aside>
    );
  }
  if (block.type === "suggested_replies" && role === "assistant") {
    const replies = Array.isArray(block.payload?.replies) ? block.payload.replies.filter(Boolean).slice(0, 4) : [];
    if (!replies.length) return null;
    return (
      <div className="suggested-replies" aria-label="Suggested replies">
        {replies.map((reply) => (
          <button
            key={reply}
            type="button"
            className="suggested-reply-chip"
            disabled={handlers.actionsDisabled}
            onClick={() => handlers.onSuggestedReply?.(reply)}
          >
            {reply}
          </button>
        ))}
      </div>
    );
  }
  if (block.type === "review_batch" && Array.isArray(block.payload?.prompts)) {
    return (
      <div
        className={chatMediaStripClassName("review-batch-strip", { streaming })}
        data-testid="review-batch-strip"
      >
        {block.payload.prompts.map((prompt) => (
          <ReviewPromptCard
            key={prompt.id || prompt.rating_key}
            prompt={prompt}
            curatorName={handlers.curatorName}
            reviewPromptTemplates={handlers.reviewPromptTemplates}
            sessionId={handlers.sessionId}
            onSaved={handlers.onReviewSave}
            onDismissed={handlers.onReviewDismiss}
            disabled={handlers.actionsDisabled}
            compact
          />
        ))}
      </div>
    );
  }
  if (block.type === "review_prompt" && block.payload?.prompt) {
    return (
      <ReviewPromptCard
        prompt={block.payload.prompt}
        curatorName={handlers.curatorName}
        reviewPromptTemplates={handlers.reviewPromptTemplates}
        sessionId={handlers.sessionId}
        onSaved={handlers.onReviewSave}
        onDismissed={handlers.onReviewDismiss}
        disabled={handlers.actionsDisabled}
        compact={Boolean(block.payload?.compact)}
      />
    );
  }
  if (block.type === "plex_rating_conflict" && block.payload) {
    return (
      <ReviewConflictBanner
        payload={block.payload}
        sessionId={handlers.sessionId}
        onResolved={handlers.onReviewConflictResolved}
        disabled={handlers.actionsDisabled}
      />
    );
  }
  if (block.type === "action_prompt" && block.action === "open_viewport") {
    // Already rendered inline with the preceding title_cards bulk actions row
    const precedingHasTitleCards = blocks.slice(0, blockIndex).some((entry) => entry.type === "title_cards");
    if (precedingHasTitleCards) return null;
    const viewportItems = filterDisplayableCards(block.payload?.items);
    return (
      <button
        type="button"
        className="confirm-all-button viewport-expand-btn"
        data-testid="expand-title-cards"
        onClick={() => handlers.onOpenViewport?.({ ...block.payload, items: viewportItems })}
      >
        Expand {turnstyleItemCount(viewportItems)} titles in turnstyle view
      </button>
    );
  }
  return null;
}

export default function ChatThread({
  messages,
  chatError,
  sessionId,
  curatorName = "Curator",
  reviewPromptTemplates,
  reviewLookup = {},
  messageFeedback = {},
  onFeedbackChange,
  onReviewSave,
  onReviewDismiss,
  onReviewConflictResolved,
  onAdd,
  onDismiss,
  onOpenViewport,
  onConfirmAllItems,
  onConfirmAllTokens,
  pendingTokenCount = 0,
  pendingTokenActions = [],
  actionsDisabled = false,
  onTogglePin,
  onRecommend,
  watchlistLookup,
  requestPath = "arr",
  userRole,
  multiUserEnabled = true,
  showErrors = true,
  draggableToDock = false,
  onSaveToLibrary,
  onSuggestedReply,
  onCreateRail,
  onOpenAsGrid,
}) {
  const lastAssistantId = [...messages].reverse().find((message) => message.role === "assistant")?.id;

  return (
    <div className="chat-thread">
      {showErrors && chatError ? <InlineAlert type="error" message={chatError} /> : null}
      {messages.map((message) => {
        const isAssistant = message.role === "assistant";
        const streaming = Boolean(message._streaming);
        return (
          <div
            key={message.id}
            className={`message message-contained ${message.role}${streaming ? " is-streaming" : ""}`}
            data-testid={`chat-message-${message.role}`}
            data-message-id={message.id}
            data-message-role={message.role}
            data-message-kind={
              String(message.id || "").startsWith("review-prompt-") ? "review-prompt" : "chat"
            }
          >
            {isAssistant ? (
              <div className="message-agent-meta">
                <AgentAvatar name={curatorName} streaming={streaming} />
                <span className="message-agent-name">{curatorName}</span>
              </div>
            ) : null}
            <div className="message-inner">
              {message.blocks.map((block, index) => (
                <div key={index}>
                  {renderBlock(
                    block,
                    {
                      onAdd,
                      onDismiss,
                      onOpenViewport,
                      onConfirmAllItems,
                      onConfirmAllTokens,
                      pendingTokenCount: message.id === lastAssistantId ? pendingTokenCount : 0,
                      pendingTokenActions: message.id === lastAssistantId ? pendingTokenActions : [],
                      actionsDisabled,
                      onTogglePin,
                      onRecommend,
                      watchlistLookup,
                      reviewLookup,
                      reviewPromptTemplates,
                      curatorName,
                      sessionId,
                      onReviewSave,
                      onReviewDismiss,
                      onReviewConflictResolved,
                      requestPath,
                      userRole,
                      multiUserEnabled,
                      draggableToDock,
                      onSuggestedReply,
                      onCreateRail,
                      onOpenAsGrid,
                      titleRefs: titleRefsFromBlocks(message.blocks),
                    },
                    message.role,
                    message,
                    index,
                    message.blocks,
                    streaming,
                  )}
                </div>
              ))}
              {isAssistant &&
              message.id === lastAssistantId &&
              pendingTokenCount >= 1 &&
              !message.blocks.some((block) => block.type === "title_cards")
                ? renderBulkConfirmActions(
                    message,
                    {
                      onConfirmAllItems,
                      onConfirmAllTokens,
                      pendingTokenCount,
                      pendingTokenActions,
                      actionsDisabled,
                      requestPath,
                      userRole,
                      multiUserEnabled,
                    },
                    true,
                    null,
                  )
                : null}
              {isAssistant ? (
                <div className="message-response-actions">
                  <MessageReactions
                    messageId={message.id}
                    sessionId={sessionId}
                    initialFeedback={messageFeedback[message.id]}
                    onFeedbackChange={onFeedbackChange}
                  />
                  <ShareActionMenu
                    content={{ blocks: message.blocks }}
                    name={`${curatorName} response`}
                    sourceSessionId={sessionId}
                    sourceMessageId={message.id}
                    label="Save, share, print, or export"
                  />
                </div>
              ) : null}
            </div>
          </div>
        );
      })}
    </div>
  );
}
