import { Link } from "react-router-dom";
import { helpAnchor } from "../lib/backNav.js";

/**
 * Unobtrusive contextual help link that jumps to a specific Help section.
 *
 * Keeps the app's icon-first chrome: renders a subtle "?" affordance by default
 * (icon variant) or a small text link. Pass a Help anchor slug (see
 * frontend/src/lib/helpAnchors.js) matching a docs/HELP.md heading.
 *
 * Examples:
 *   <HelpHint anchor="what-knowledge-coverage-means" label="What this means" />
 *   <HelpHint anchor="why-on-posters" variant="icon" title="Why on posters" />
 */
export default function HelpHint({
  anchor,
  label,
  title = "Learn more in Help",
  variant = "icon",
  className = "",
  testId,
  onClick,
}) {
  const to = helpAnchor(anchor);
  const isIcon = variant === "icon" && !label;
  const classes = [
    "help-hint",
    isIcon ? "help-hint-icon" : "help-hint-link",
    className,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <Link
      to={to}
      className={classes}
      title={title}
      aria-label={isIcon ? title : undefined}
      data-testid={testId}
      onClick={onClick}
    >
      {isIcon ? (
        <span className="material-symbols-outlined" aria-hidden="true">
          help
        </span>
      ) : (
        label
      )}
    </Link>
  );
}
