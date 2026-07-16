import { useState } from "react";
import { groupAddableItems } from "../lib/addActions";
import { filterDisplayableCards } from "../lib/turnstyleItems.js";
import ConfirmAllButton from "./ConfirmAllButton";
import TitleCard from "./TitleCard";

export default function TurnstyleResultsOverlay({
  payload,
  onClose,
  onAdd,
  onDismiss,
  onConfirmAllItems,
  onTogglePin,
  watchlistLookup,
  actionsDisabled = false,
  requestPath = "arr",
  draggableToDock = false,
}) {
  const [cinemaMode, setCinemaMode] = useState(false);
  const items = filterDisplayableCards(payload?.items);
  if (!items.length) return null;

  // Bulk confirm counts use the same displayable candidate set as the track.
  const { radarr, sonarr, seerr } = groupAddableItems(items, { requestPath });

  return (
    <div
      className={`viewport-overlay ${cinemaMode ? "cinema-mode" : ""}`}
      data-testid="turnstyle-results-overlay"
      onClick={onClose}
    >
      <div
        className={`viewport ${cinemaMode ? "cinema-mode" : ""}`}
        role="dialog"
        aria-modal="true"
        aria-label={payload?.title || "Recommendations"}
        onClick={(event) => event.stopPropagation()}
      >
        <header>
          <div>
            <p className="eyebrow">Turnstyle view</p>
            <h2>{payload?.title || "Recommendations"}</h2>
          </div>
          <div className="viewport-header-actions">
            <button
              type="button"
              className={`ghost cinema-mode-toggle ${cinemaMode ? "active" : ""}`}
              data-testid="cinema-mode-toggle"
              onClick={() => setCinemaMode((value) => !value)}
              aria-pressed={cinemaMode}
            >
              {cinemaMode ? "Exit cinema" : "Cinema mode"}
            </button>
            <button type="button" className="ghost" data-testid="close-turnstyle-results" onClick={onClose}>
              Close
            </button>
          </div>
        </header>
        {(seerr.length >= 2 || radarr.length >= 2 || sonarr.length >= 2) && onConfirmAllItems ? (
          <div className="bulk-confirm-actions viewport-bulk-actions">
            {seerr.length >= 2 ? (
              <ConfirmAllButton
                count={seerr.length}
                target="seerr"
                onClick={() => onConfirmAllItems(seerr, "seerr")}
                disabled={actionsDisabled}
              />
            ) : null}
            {radarr.length >= 2 ? (
              <ConfirmAllButton
                count={radarr.length}
                target="radarr"
                onClick={() => onConfirmAllItems(radarr, "radarr")}
                disabled={actionsDisabled}
              />
            ) : null}
            {sonarr.length >= 2 ? (
              <ConfirmAllButton
                count={sonarr.length}
                target="sonarr"
                onClick={() => onConfirmAllItems(sonarr, "sonarr")}
                disabled={actionsDisabled}
              />
            ) : null}
          </div>
        ) : null}
        <div className="turnstyle-track">
          {items.map((item) => (
            <TitleCard
              key={`${item.media_type}-${item.tmdb_id || item.tvdb_id || item.title}`}
              item={item}
              requestPath={requestPath}
              onAdd={onAdd}
              onDismiss={onDismiss}
              onTogglePin={item.card_kind === "purge" ? undefined : onTogglePin}
              pinRecord={watchlistLookup?.byItemKey?.get(
                `${item.media_type}:${item.tmdb_id ?? ""}:${item.tvdb_id ?? ""}`
              )}
              draggableToDock={draggableToDock}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
