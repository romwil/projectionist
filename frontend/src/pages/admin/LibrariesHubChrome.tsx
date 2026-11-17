import Button from "../../components/Button";
import {
  LIBRARIES_HUB_TABS,
  type LibrariesAttentionItem,
  type LibrariesHubTabId,
} from "../../lib/librariesHub.js";

type LibrariesHubChromeProps = {
  activeTab: LibrariesHubTabId;
  attention: LibrariesAttentionItem[];
  badges?: Partial<Record<LibrariesHubTabId, number>>;
  onSelectTab: (tabId: LibrariesHubTabId) => void;
};

/** Sticky subnav + attention strip for Admin → Libraries hub. */
export default function LibrariesHubChrome({
  activeTab,
  attention,
  badges = {},
  onSelectTab,
}: LibrariesHubChromeProps) {
  return (
    <div className="libraries-hub-chrome" data-testid="libraries-hub-chrome">
      {attention.length ? (
        <section
          className="libraries-attention"
          data-testid="libraries-attention"
          aria-labelledby="libraries-attention-title"
        >
          <div className="libraries-attention-head">
            <h2 id="libraries-attention-title" className="libraries-attention-title">
              Attention ({attention.length})
            </h2>
          </div>
          <ul className="libraries-attention-list">
            {attention.map((item) => (
              <li
                key={item.id}
                className={`libraries-attention-row severity-${item.severity}`}
                data-testid={`libraries-attention-${item.id}`}
              >
                <div className="libraries-attention-text">
                  <span className="libraries-attention-row-title">{item.title}</span>
                  <span className="libraries-attention-row-detail">{item.detail}</span>
                </div>
                <Button
                  variant="secondary"
                  size="sm"
                  data-testid={`libraries-attention-cta-${item.id}`}
                  onClick={() => onSelectTab(item.tabId)}
                >
                  {item.ctaLabel}
                </Button>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <nav
        className="libraries-hub-subnav"
        data-testid="libraries-hub-subnav"
        aria-label="Libraries sections"
      >
        {LIBRARIES_HUB_TABS.map((tab) => {
          const count = badges[tab.id];
          const showBadge = typeof count === "number" && count > 0;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              className={`libraries-hub-tab ${isActive ? "is-active" : ""}`}
              data-testid={`libraries-hub-tab-${tab.id}`}
              aria-current={isActive ? "page" : undefined}
              onClick={() => onSelectTab(tab.id)}
            >
              <span>{tab.label}</span>
              {showBadge ? (
                <span className="libraries-hub-tab-badge" aria-label={`${count} open`}>
                  {count > 99 ? "99+" : count}
                </span>
              ) : null}
            </button>
          );
        })}
      </nav>
    </div>
  );
}
