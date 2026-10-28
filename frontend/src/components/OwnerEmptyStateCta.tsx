import { Link } from "react-router-dom";
import { ownerEmptyStateCta } from "../lib/exploreFeeds.js";

type OwnerEmptyStateCtaProps = {
  note?: unknown;
  isOwner?: boolean;
  testId?: string;
};

/**
 * Honest empty note plus owner-only deep link to Scheduled Tasks when caches are cold.
 */
export default function OwnerEmptyStateCta({
  note,
  isOwner = false,
  testId = "explore-owner-empty-cta",
}: OwnerEmptyStateCtaProps) {
  const cta = ownerEmptyStateCta(note, { isOwner });
  if (!cta) return null;
  return (
    <Link to={cta.href} className="explore-owner-cta" data-testid={testId}>
      {cta.label}
    </Link>
  );
}
