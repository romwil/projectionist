import { collectAddableFromMessage } from "../lib/addActions";
import ReviewPromptCard from "./ReviewPromptCard";
import ReviewConflictBanner from "./ReviewConflictBanner";
import ConfirmAllButton from "./ConfirmAllButton";
import MessageReactions from "./MessageReactions";
import TitleCard from "./TitleCard";
import InlineAlert from "./InlineAlert";
import MessageText from "./MessageText";

function isDisplayableCard(item) {
  return Boolean(item?.title || item?.tmdb_id || item?.tvdb_id || item?.rating_key);
}

function renderBulkConfirmActions(message, handlers, showTokenConfirm) {
  const { radarr, sonarr, seerr } = collectAddableFromMessage(message, {
    requestPath: handlers.requestPath,
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
    return actions.length ? <div className="bulk-confirm-actions">{actions}</div> : null;
  }

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
  if (block.type === "title_cards") {
    const items = (block.items || []).filter(isDisplayableCard).map((item) => enrichTitleCard(item, handlers.reviewLookup));
    if (!items.length) return null;
    const isLastTitleCards = !blocks.slice(blockIndex + 1).some((entry) => entry.type === "title_cards");
    return (
      <>
        <div className="inline-cards">
          {items.map((item) => (
            <TitleCard
              key={`${item.media_type}-${item.tmdb_id || item.tvdb_id || item.title}`}
              item={item}
              compact
              requestPath={handlers.requestPath}
              onAdd={handlers.onAdd}
              onDismiss={handlers.onDismiss}
              onTogglePin={item.card_kind === "purge" ? undefined : handlers.onTogglePin}
              pinRecord={handlers.watchlistLookup?.byItemKey?.get(
                `${item.media_type}:${item.tmdb_id ?? ""}:${item.tvdb_id ?? ""}`
              )}
              draggableToDock={handlers.draggableToDock}
            />
          ))}
        </div>
        {role === "assistant" && isLastTitleCards
          ? renderBulkConfirmActions(message, handlers, handlers.pendingTokenCount >= 2)
          : null}
      </>
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
    return (
      <button type="button" className="viewport-link" data-testid="expand-title-cards" onClick={() => handlers.onOpenViewport?.(block.payload)}>
        Expand {block.payload?.items?.length || 0} titles in turnstyle view
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
  watchlistLookup,
  requestPath = "arr",
  showErrors = true,
  draggableToDock = false,
}) {
  const lastAssistantId = [...messages].reverse().find((message) => message.role === "assistant")?.id;

  return (
    <div className="chat-thread">
      {showErrors && chatError ? <InlineAlert type="error" message={chatError} /> : null}
      {messages.map((message) => (
        <div
          key={message.id}
          className={`message ${message.role}`}
          data-testid={`chat-message-${message.role}`}
          data-message-id={message.id}
          data-message-role={message.role}
        >
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
                    watchlistLookup,
                    reviewLookup,
                    reviewPromptTemplates,
                    curatorName,
                    sessionId,
                    onReviewSave,
                    onReviewDismiss,
                    onReviewConflictResolved,
                    requestPath,
                    draggableToDock,
                  },
                  message.role,
                  message,
                  index,
                  message.blocks
                )}
              </div>
            ))}
            {message.role === "assistant" ? (
              <MessageReactions
                messageId={message.id}
                sessionId={sessionId}
                initialFeedback={messageFeedback[message.id]}
                onFeedbackChange={onFeedbackChange}
              />
            ) : null}
          </div>
        </div>
      ))}
    </div>
  );
}
