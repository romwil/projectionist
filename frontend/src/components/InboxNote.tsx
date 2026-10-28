import { useState } from "react";
import TitleDetailLink from "./TitleDetailLink";
import {
  formatInboxWhen,
  inboxFullMessage,
  inboxReplySubmission,
  isAgentInboxNote,
} from "../lib/inboxMailbox.js";
import { digestPicks, isEnthusiastNudge, normalizeRecommendation } from "../lib/recommendationInbox.js";
import { titleDetailPath } from "../lib/titleLinks.js";

type InboxPick = {
  title?: string;
  tmdb_id?: string | number;
  rating_key?: string | number;
};

type InboxReply = {
  id?: string | number;
  role?: string;
  text?: React.ReactNode;
};

type InboxNoteItem = {
  kind?: string;
} & Record<string, unknown>;

type InboxNoteProps = {
  item?: InboxNoteItem | null;
  personaName?: string;
  replies?: InboxReply[];
  streaming?: string;
  replyError?: string;
  onSubmit?: (text: string) => void | Promise<void>;
  onBack?: (...args: any[]) => void;
  onDismiss?: (item?: InboxNoteItem | null) => void;
};

/**
 * The open note. Agent messages include a composer that sends in place.
 */
export default function InboxNote({
  item,
  personaName = "your curator",
  replies = [],
  streaming = "",
  replyError = "",
  onSubmit,
  onBack,
  onDismiss,
}: InboxNoteProps) {
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const full = inboxFullMessage(item);
  const agent = isAgentInboxNote(item);
  const when = formatInboxWhen(full.when);
  const normalized = normalizeRecommendation(item);
  const openTitle = !agent && (isEnthusiastNudge(item) || item?.kind === "recommendation" || item?.kind === "arrival");
  const picks: any = digestPicks(item);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    const text = draft.trim();
    if (!text || sending) return;
    const submission = inboxReplySubmission();
    if (!submission.stayOnInbox || submission.route) return;
    setSending(true);
    try {
      await onSubmit?.(text);
      setDraft("");
    } finally {
      setSending(false);
    }
  }

  return (
    <article className="inbox-note" data-testid="inbox-note">
      <div className="inbox-note-toolbar">
        <button type="button" className="ghost inbox-hit" onClick={onBack} data-testid="inbox-note-back">
          Back to inbox
        </button>
        <button
          type="button"
          className="ghost inbox-hit"
          onClick={() => onDismiss?.(item)}
          data-testid="inbox-note-dismiss"
        >
          Dismiss
        </button>
      </div>
      <header className="inbox-note-header">
        <h2>{full.title}</h2>
        {when ? <p className="inbox-note-when">{when}</p> : null}
      </header>
      {full.body ? (
        <div className="inbox-note-body" data-testid="inbox-message-body">
          {full.body}
        </div>
      ) : null}
      {full.titles.length ? (
        <ul className="inbox-note-titles">
          {full.titles.map((title: string) => (
            <li key={title}>{title}</li>
          ))}
        </ul>
      ) : null}
      {picks.length ? (
        <div className="inbox-note-picks">
          {picks.map((pick: InboxPick) => {
            const path = titleDetailPath(pick);
            return path ? (
              <TitleDetailLink key={`${pick.title}-${pick.tmdb_id || pick.rating_key}`} item={pick} className="inbox-hit">
                {pick.title}
              </TitleDetailLink>
            ) : (
              <span key={pick.title}>{pick.title}</span>
            );
          })}
        </div>
      ) : null}
      {openTitle && titleDetailPath(normalized) ? (
        <p className="inbox-note-actions">
          <TitleDetailLink item={normalized} className="btn-link inbox-hit" data-testid="inbox-open-title">
            Open title
          </TitleDetailLink>
        </p>
      ) : null}
      {agent ? (
        <section className="inbox-note-thread" aria-label={`Reply to ${personaName}`}>
          {replies.map((reply: InboxReply) => (
            <p
              key={reply.id}
              className={`inbox-note-reply inbox-note-reply--${reply.role === "assistant" ? "agent" : "user"}`}
              data-testid={`inbox-reply-${reply.id}`}
            >
              {reply.text}
            </p>
          ))}
          {streaming ? (
            <p className="inbox-note-reply inbox-note-reply--agent" data-testid="inbox-reply-streaming">
              {streaming}
            </p>
          ) : null}
          {replyError ? <p className="status status-error">{replyError}</p> : null}
          <form className="inbox-note-composer" data-testid="inbox-note-composer" onSubmit={handleSubmit}>
            <label className="inbox-note-label" htmlFor="inbox-note-reply">
              Reply to {personaName}
            </label>
            <textarea
              id="inbox-note-reply"
              value={draft}
              rows={3}
              onChange={(event) => setDraft(event.target.value)}
              placeholder={`Reply to ${personaName}`}
            />
            <button type="submit" className="primary inbox-hit" disabled={sending || !draft.trim()}>
              {sending ? "Sending…" : "Send"}
            </button>
          </form>
        </section>
      ) : null}
    </article>
  );
}
