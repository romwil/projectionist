import { Link } from "react-router-dom";

/**
 * Shared empty-state grammar: Fraunces headline, DM Sans body, optional amber CTA.
 * Matches `/live` and Explore empty-block rhythm for Inbox / My Journey / peers.
 */
export default function ChamberEmpty({
  title,
  body,
  ctaLabel,
  ctaTo,
  testId = "chamber-empty",
  children = null,
}) {
  return (
    <div className="explore-empty-block chamber-empty" data-testid={testId}>
      {title ? <h2 className="chamber-empty-title">{title}</h2> : null}
      {body ? <p className="explore-empty status status-secondary">{body}</p> : null}
      {children}
      {ctaLabel && ctaTo ? (
        <Link to={ctaTo} className="explore-owner-cta" data-testid={`${testId}-cta`}>
          {ctaLabel}
        </Link>
      ) : null}
    </div>
  );
}
