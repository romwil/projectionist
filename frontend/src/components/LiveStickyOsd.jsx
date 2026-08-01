import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { liveWatchHref } from "../lib/liveChannels.js";
import { clearLiveStickyOsd, loadLiveStickyOsd } from "../lib/liveTuneLink.js";

/**
 * Cross-route sticky mini OSD — returns to Live Watch without keeping HLS on every page.
 * Full video stays on /live or the pop-out window (CSP-safe).
 */
export default function LiveStickyOsd() {
  const location = useLocation();
  const [state, setState] = useState(() => loadLiveStickyOsd());

  useEffect(() => {
    setState(loadLiveStickyOsd());
    function onStorage() {
      setState(loadLiveStickyOsd());
    }
    window.addEventListener("storage", onStorage);
    window.addEventListener("projectionist:live-sticky", onStorage);
    return () => {
      window.removeEventListener("storage", onStorage);
      window.removeEventListener("projectionist:live-sticky", onStorage);
    };
  }, [location.pathname]);

  if (!state?.channelId) return null;
  // Hide on Live routes — the real player OSD is there.
  if (String(location.pathname || "").startsWith("/live")) return null;

  return (
    <aside className="live-sticky-osd" data-testid="live-sticky-osd" aria-label="Still tuned">
      <div className="live-sticky-osd-meta">
        <p className="live-sticky-osd-label">Still tuned</p>
        <p className="live-sticky-osd-title">
          {state.channelName}
          {state.nowTitle ? ` · ${state.nowTitle}` : ""}
        </p>
      </div>
      <div className="live-sticky-osd-actions">
        <Link
          className="primary"
          to={liveWatchHref(state.channelId)}
          data-testid="live-sticky-osd-return"
        >
          Back to Live
        </Link>
        <button
          type="button"
          className="ghost"
          data-testid="live-sticky-osd-dismiss"
          onClick={() => {
            clearLiveStickyOsd();
            setState(null);
            window.dispatchEvent(new Event("projectionist:live-sticky"));
          }}
        >
          Dismiss
        </button>
      </div>
    </aside>
  );
}
