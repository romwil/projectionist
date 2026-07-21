import { collectAddableFromMessage } from "../lib/addActions";
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

function renderBulkConfirmActions(message, handlers, showTokenConfirm, viewportBlock) {
  const { radarr, sonarr, seerr } = collectAddableFromMessage(message, {
    requestPath: handlers.requestPath,
    role: handlers.userRole,
    multiUserEnabled: handlers.multiUserEnabled,
  });
  const actions = [];

  if (showTokenConfirm && handlers.pendingTokenCount >= 2) {
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

function renderBlock(block, handlers, role, message, blockIndex, blocks) {
  if (block.type === "text") {
    return <MessageText content={block.content} markdown={role === "assistant"} />;
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
    return (
      <>
        <div className="inline-cards">
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
          ? renderBulkConfirmActions(message, handlers, handlers.pendingTokenCount >= 2, nextViewport)
          : null}
      </>
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
      <div className="review-batch-strip" data-testid="review-batch-strip">
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
                    },
                    message.role,
                    message,
                    index,
                    message.blocks
                  )}
                </div>
              ))}
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
