import { useState } from "react";

import { seasonalCardMeta } from "../lib/seasonalShelves.js";
import LibraryMediaCard from "./LibraryMediaCard";
import PosterRailLoader from "./PosterRailLoader";
import SeasonalPickChatPane from "./SeasonalPickChatPane";

/**
 * Explore seasonal rail: curator notes under posters + docked "Chat about this".
 * Primary household surface for agent-curated seasonal shelves.
 */
/** Props for SeasonalSpotlightRail. `any` = API/handler bags until Wave 4 client generics. */
type SeasonalSpotlightRailProps = {
  items?: any;
  loading?: boolean;
  seasonLabel?: string;
  scopeId?: string;
  onRecommend?: (...args: any[]) => void;
  showRecommend?: boolean;
  testId?: string;
};

export default function SeasonalSpotlightRail({
  items = [],
  loading = false,
  seasonLabel = "",
  scopeId = "",
  onRecommend,
  showRecommend = false,
  testId = "explore-seasonal-spotlight-rail",
}: SeasonalSpotlightRailProps) {
  const [chatItem, setChatItem] = useState<any | null>(null);

  if (loading) {
    return <PosterRailLoader testId={`${testId}-loader`} />;
  }
  if (!items.length) return null;

  const chatOpen = Boolean(chatItem);

  return (
    <div
      className={`explore-seasonal-rail${chatOpen ? " explore-seasonal-rail--chat-open" : ""}`}
      data-testid={`${testId}-wrap`}
    >
      <div className="explore-seasonal-rail-main">
        <div className="explore-card-rail" data-testid={testId}>
          {items.map((item: any) => {
            const key = item.id || item.rating_key || `${item.media_type}-${item.tmdb_id || item.title}`;
            const meta = seasonalCardMeta(item);
            return (
              <div key={key} className="explore-seasonal-card">
                <LibraryMediaCard
                  item={item}
                  meta={meta}
                  onRecommend={onRecommend}
                  showRecommend={showRecommend}
                  testId={`${testId}-card-${item.id || item.rating_key || "title"}`}
                />
                <button
                  type="button"
                  className="ghost explore-seasonal-chat-btn"
                  data-testid={`${testId}-chat-${item.id || item.rating_key || "title"}`}
                  onClick={() => setChatItem(item)}
                >
                  Chat about this
                </button>
              </div>
            );
          })}
        </div>
      </div>
      {chatOpen ? (
        <SeasonalPickChatPane
          seasonLabel={seasonLabel}
          scopeId={scopeId}
          title={chatItem}
          onClose={() => setChatItem(null)}
          testId={`${testId}-chat-pane`}
        />
      ) : null}
    </div>
  );
}
