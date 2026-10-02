import {
  QUEUE_PAD_FEEDS,
  QUEUE_PAD_UP_TO,
  queuePadDraft,
  queuePadSummary,
} from "../../lib/liveQueuePad.js";

/**
 * Rotation padding for a channel: keep up to N titles on rotation (1–5) and
 * fill spare slots from Recently added / Recently released after what's
 * playing. Used in the channel creator and in channel settings.
 */
export default function QueuePadControl({
  value,
  onChange,
  playing = null,
  disabled = false,
  testIdPrefix = "live-queue-pad",
}) {
  const draft = queuePadDraft(value);
  const off = draft.queue_up_to <= 0;
  return (
    <div className="live-queue-pad" data-testid={testIdPrefix}>
      <div className="live-queue-pad-fields">
        <label>
          <span>Keep on rotation</span>
          <select
            data-testid={`${testIdPrefix}-up-to`}
            value={String(draft.queue_up_to)}
            disabled={disabled}
            onChange={(event) => onChange({ ...draft, queue_up_to: Number(event.target.value) })}
          >
            <option value="0">No padding</option>
            {QUEUE_PAD_UP_TO.map((n) => (
              <option key={n} value={String(n)}>
                Up to {n} {n === 1 ? "title" : "titles"}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Fill spare slots from</span>
          <select
            data-testid={`${testIdPrefix}-feed`}
            value={draft.queue_feed}
            disabled={disabled || off}
            onChange={(event) => onChange({ ...draft, queue_feed: event.target.value })}
          >
            {QUEUE_PAD_FEEDS.map((feed) => (
              <option key={feed.id} value={feed.id}>
                {feed.label}
              </option>
            ))}
          </select>
        </label>
      </div>
      <p className="live-studio-hint" data-testid={`${testIdPrefix}-summary`}>
        {queuePadSummary(draft, playing)}
      </p>
    </div>
  );
}
