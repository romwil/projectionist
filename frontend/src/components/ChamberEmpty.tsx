import { Link } from "react-router-dom";

type ChamberEmptyProps = {
  title?: any;
  body?: React.ReactNode;
  ctaLabel?: React.ReactNode;
  ctaTo?: string;
  testId?: string;
  children?: React.ReactNode;
};

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
}: ChamberEmptyProps) {
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
