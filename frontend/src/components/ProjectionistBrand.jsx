import { Link } from "react-router-dom";
import { agentPulseTitle, projectionistBrandAriaLabel } from "../lib/agentPulse.js";

/**
 * Clickable Projectionist wordmark for the chat top bar.
 * The projector-lamp / aperture glyph reflects agent activity (idle / thinking / error).
 */
function LampGlyph({ pulse, statusLabel }) {
  return (
    <span
      className={`projectionist-brand-lamp agent-pulse-lamp ${pulse}`}
      title={statusLabel}
      aria-hidden="true"
      data-testid="projectionist-brand-lamp"
    >
      <svg
        className="projectionist-brand-lamp-svg"
        viewBox="0 0 20 20"
        width="1em"
        height="1em"
        focusable="false"
      >
        {/* Outer aperture ring */}
        <circle cx="10" cy="10" r="7.5" fill="none" stroke="currentColor" strokeWidth="1.4" />
        {/* Iris blades suggestion */}
        <path
          d="M10 3.2 L11.6 8.4 L16.8 10 L11.6 11.6 L10 16.8 L8.4 11.6 L3.2 10 L8.4 8.4 Z"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.1"
          strokeLinejoin="round"
        />
        {/* Lamp core / beam hotspot */}
        <circle className="projectionist-brand-lamp-core" cx="10" cy="10" r="2.2" fill="currentColor" />
      </svg>
    </span>
  );
}

export default function ProjectionistBrand({ pulse = "idle", chatError = "", homeTo = "/" }) {
  const statusLabel = agentPulseTitle(pulse, chatError);
  const ariaLabel = projectionistBrandAriaLabel(pulse, chatError);

  return (
    <Link
      to={homeTo}
      className="projectionist-brand app-topbar-titles"
      aria-label={ariaLabel}
      data-testid="projectionist-brand"
    >
      <h1 className="projectionist-brand-wordmark">
        Projectionist
        <LampGlyph pulse={pulse} statusLabel={statusLabel} />
      </h1>
    </Link>
  );
}
