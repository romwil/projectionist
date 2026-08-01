import { useMemo, useState } from "react";
import { liveTuneAbsoluteUrl, tuneLinkCardDataUrl } from "../../lib/liveTuneLink.js";

/**
 * Copy station tune deep-link (+ visual link card) for multi-room couch handoff.
 */
export default function LiveTuneShare({ channelId, channelName = "" }) {
  const [copied, setCopied] = useState(false);
  const [open, setOpen] = useState(false);
  const url = useMemo(() => liveTuneAbsoluteUrl(channelId), [channelId]);
  const card = useMemo(() => tuneLinkCardDataUrl(url), [url]);

  if (!channelId || !url) return null;

  async function copyLink() {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  }

  return (
    <div className="live-tune-share" data-testid="live-tune-share">
      <button
        type="button"
        className="live-chrome-icon-btn"
        data-testid="live-tune-share-toggle"
        aria-label="Copy tune link for another screen"
        data-tooltip="Tune link"
        title="Copy tune link"
        onClick={() => setOpen((v) => !v)}
      >
        <span className="material-symbols-outlined" aria-hidden="true">
          qr_code_2
        </span>
      </button>
      {open ? (
        <div className="live-tune-share-popover" data-testid="live-tune-share-popover">
          <p className="live-tune-share-lede">
            Hand off {channelName || "this station"} to another phone or TV in the house.
          </p>
          <code className="live-tune-share-url" data-testid="live-tune-share-url">
            {url}
          </code>
          {card ? (
            <img
              className="live-tune-share-card"
              src={card}
              alt="Tune link card"
              data-testid="live-tune-share-card"
            />
          ) : null}
          <button
            type="button"
            className="primary"
            data-testid="live-tune-share-copy"
            onClick={copyLink}
          >
            {copied ? "Copied" : "Copy tune link"}
          </button>
        </div>
      ) : null}
    </div>
  );
}
