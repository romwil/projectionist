import { Link } from "react-router-dom";
import { agentPulseTitle, curatorxBrandAriaLabel } from "../lib/agentPulse.js";

/**
 * Clickable CuratorX wordmark for the chat top bar.
 * The trailing X reflects agent activity (idle / thinking / error).
 */
export default function CuratorXBrand({ pulse = "idle", chatError = "", homeTo = "/" }) {
  const statusLabel = agentPulseTitle(pulse, chatError);
  const ariaLabel = curatorxBrandAriaLabel(pulse, chatError);

  return (
    <Link
      to={homeTo}
      className="curatorx-brand app-topbar-titles"
      aria-label={ariaLabel}
      data-testid="curatorx-brand"
    >
      <h1 className="curatorx-brand-wordmark">
        Curator
        <span
          className={`curatorx-brand-x agent-pulse-x ${pulse}`}
          title={statusLabel}
          aria-hidden="true"
          data-testid="agent-pulse"
        >
          X
        </span>
      </h1>
    </Link>
  );
}
