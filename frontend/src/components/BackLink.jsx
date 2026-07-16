import { Link, useLocation } from "react-router-dom";
import { backLabelForPath, resolveBackTarget, ROUTES } from "../lib/backNav.js";

/**
 * Consistent return link. Prefer location.state.from; otherwise use fallbackTo.
 */
export default function BackLink({
  fallbackTo = ROUTES.chat,
  label,
  className = "title-detail-back",
  testId = "back-link",
}) {
  const location = useLocation();
  const to = resolveBackTarget(location.state, fallbackTo);
  const text = label || `← ${backLabelForPath(to)}`;
  return (
    <Link to={to} className={className} data-testid={testId}>
      {text.startsWith("←") ? text : `← ${text}`}
    </Link>
  );
}
