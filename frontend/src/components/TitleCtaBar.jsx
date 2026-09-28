import { createPortal } from "react-dom";
import { Link } from "react-router-dom";
import { useAnchoredPopover } from "../hooks/useAnchoredPopover";
import {
  placeTitleCtaMoreMenu,
  TITLE_CTA_COPY,
  TITLE_CTA_ICONS,
  TITLE_CTA_PHONE_OVERFLOW,
  watchedCtaPresentation,
} from "../lib/titleCta.js";

function CtaIcon({ name }) {
  return (
    <span className="material-symbols-outlined" aria-hidden="true">
      {name}
    </span>
  );
}

function SecondaryAction({
  as: Comp = "button",
  className = "",
  icon,
  label,
  tooltip,
  testId,
  phoneOverflow = false,
  compact,
  children,
  ...rest
}) {
  const overflowClass = phoneOverflow ? " title-detail-cta-desktop-only" : "";
  return (
    <Comp
      className={`title-cta title-cta-ghost title-cta-secondary title-cta-icon-forward${overflowClass} ${className}`.trim()}
      data-testid={testId}
      title={tooltip || label}
      aria-label={tooltip || label}
      data-compact={compact ? "true" : undefined}
      {...rest}
    >
      <CtaIcon name={icon} />
      <span className="title-cta-secondary-label">{children ?? label}</span>
    </Comp>
  );
}

/**
 * Shared title CTA row: one gold primary, icon-forward secondaries, portaled More.
 * Used by full title page, mini sheet/drawer, and episode detail.
 */
export default function TitleCtaBar({
  compact = false,
  playTo = null,
  playTestId = "title-detail-play",
  onPlayClick,
  addPrimary = null,
  askOwner = null,
  trailerKey = "",
  onOpenTrailer,
  reviewsCta = null,
  onOpenReview,
  canToggleWatched = false,
  detail = null,
  watchStatus = null,
  onToggleWatched,
  chatHref = "",
  multiUserEnabled = false,
  onOpenRecommend,
  secondaryAdd = null,
  plexHref = "",
  plexTestId = "watch-on-plex-button",
  canDeleteLibrary = false,
  markingBadMedia = false,
  deleting = false,
  onOpenMarkBadMedia,
  onOpenDelete,
  extraMoreItems = null,
  testId = "title-detail-cta-row",
  moreTestId = "title-detail-cta-more",
}) {
  const { open, setOpen, rootRef, popoverRef, popoverStyle } = useAnchoredPopover({
    closeOnEscape: true,
    anchorSelector: `[data-testid='${moreTestId}']`,
    placement: placeTitleCtaMoreMenu,
  });

  const hasPrimary = Boolean(playTo || addPrimary || askOwner);
  const watched = canToggleWatched ? watchedCtaPresentation(detail) : null;
  const hasPhoneOverflow =
    Boolean(chatHref) || multiUserEnabled || Boolean(secondaryAdd);
  const showMore =
    Boolean(plexHref) || hasPhoneOverflow || canDeleteLibrary || Boolean(extraMoreItems);

  function closeMore() {
    setOpen(false);
  }

  const moreMenu =
    open && typeof document !== "undefined"
      ? createPortal(
          <div
            className="title-detail-cta-menu title-detail-cta-menu--portal"
            ref={popoverRef}
            role="menu"
            style={popoverStyle || { visibility: "hidden" }}
            data-testid={`${moreTestId}-menu`}
          >
            {plexHref ? (
              <a
                href={plexHref}
                className="title-detail-cta-menu-item"
                data-testid={plexTestId}
                target="_blank"
                rel="noopener noreferrer"
                role="menuitem"
                onClick={closeMore}
              >
                <CtaIcon name={TITLE_CTA_ICONS.openInPlex} />
                {TITLE_CTA_COPY.openInPlex.label}
              </a>
            ) : null}
            {chatHref ? (
              <Link
                to={chatHref}
                className="title-detail-cta-menu-item title-detail-cta-phone-only"
                data-testid="chat-about-title-link-more"
                role="menuitem"
                onClick={closeMore}
              >
                <CtaIcon name={TITLE_CTA_ICONS.chat} />
                {TITLE_CTA_COPY.chat.tooltip}
              </Link>
            ) : null}
            {multiUserEnabled ? (
              <button
                type="button"
                className="title-detail-cta-menu-item title-detail-cta-phone-only"
                data-testid="recommend-title-button-more"
                role="menuitem"
                onClick={() => {
                  closeMore();
                  onOpenRecommend?.();
                }}
              >
                <CtaIcon name={TITLE_CTA_ICONS.watchTogether} />
                {TITLE_CTA_COPY.watchTogether.tooltip}
              </button>
            ) : null}
            {secondaryAdd ? (
              <button
                type="button"
                className="title-detail-cta-menu-item title-detail-cta-phone-only"
                data-testid="title-detail-add-button-more"
                role="menuitem"
                disabled={secondaryAdd.disabled}
                onClick={() => {
                  closeMore();
                  secondaryAdd.onClick?.();
                }}
              >
                <CtaIcon name={TITLE_CTA_ICONS.add} />
                {secondaryAdd.label}
              </button>
            ) : null}
            {extraMoreItems}
            {canDeleteLibrary ? (
              <>
                <button
                  type="button"
                  className="title-detail-cta-menu-item"
                  data-testid="title-detail-mark-bad-media-button"
                  disabled={markingBadMedia || deleting}
                  role="menuitem"
                  onClick={() => {
                    closeMore();
                    onOpenMarkBadMedia?.();
                  }}
                >
                  <CtaIcon name={TITLE_CTA_ICONS.markBadMedia} />
                  {TITLE_CTA_COPY.markBadMedia.label}
                </button>
                <button
                  type="button"
                  className="title-detail-cta-menu-item is-danger"
                  data-testid="title-detail-delete-button"
                  disabled={deleting || markingBadMedia}
                  role="menuitem"
                  onClick={() => {
                    closeMore();
                    onOpenDelete?.();
                  }}
                >
                  <CtaIcon name={TITLE_CTA_ICONS.delete} />
                  {TITLE_CTA_COPY.delete.label}
                </button>
              </>
            ) : null}
          </div>,
          document.body,
        )
      : null;

  return (
    <div className="title-detail-cta-row" data-testid={testId} ref={rootRef}>
      {hasPrimary ? (
        <div className="title-detail-cta-primary">
          {playTo ? (
            <Link
              to={playTo}
              className="title-cta title-cta-primary"
              aria-label={TITLE_CTA_COPY.play.tooltip}
              title={TITLE_CTA_COPY.play.tooltip}
              data-testid={playTestId}
              onClick={onPlayClick}
            >
              <CtaIcon name={TITLE_CTA_ICONS.play} />
              {TITLE_CTA_COPY.play.label}
            </Link>
          ) : null}
          {!playTo && addPrimary ? (
            <button
              type="button"
              className="title-cta title-cta-primary"
              data-testid="title-detail-add-button"
              title={addPrimary.tooltip || TITLE_CTA_COPY.add.tooltip}
              disabled={addPrimary.disabled}
              onClick={addPrimary.onClick}
            >
              <CtaIcon name={TITLE_CTA_ICONS.add} />
              {addPrimary.label}
            </button>
          ) : null}
          {!playTo && askOwner ? (
            <span
              className="title-cta title-cta-ghost title-cta-disabled"
              data-testid="title-detail-ask-owner"
              title={askOwner.tooltip || "Guests cannot request or add media"}
            >
              <CtaIcon name={TITLE_CTA_ICONS.lock} />
              {askOwner.label}
            </span>
          ) : null}
        </div>
      ) : null}

      <div className="title-detail-cta-secondary">
        {trailerKey ? (
          <SecondaryAction
            type="button"
            icon={TITLE_CTA_ICONS.trailer}
            label={TITLE_CTA_COPY.trailer.label}
            tooltip={TITLE_CTA_COPY.trailer.tooltip}
            testId="watch-trailer-button"
            compact={compact}
            onClick={onOpenTrailer}
          />
        ) : null}
        {reviewsCta?.kind === "rate" ? (
          <SecondaryAction
            type="button"
            icon={TITLE_CTA_ICONS.review}
            label={TITLE_CTA_COPY.review.label}
            tooltip={TITLE_CTA_COPY.review.tooltip}
            testId="title-reviews-cta"
            compact={compact}
            onClick={onOpenReview}
          />
        ) : null}
        {watched ? (
          <SecondaryAction
            type="button"
            icon={watched.icon}
            label={watched.label}
            tooltip={watchStatus === "loading" ? "Updating…" : watched.tooltip}
            testId="title-watched-cta"
            compact={compact}
            disabled={watchStatus === "loading"}
            onClick={onToggleWatched}
          >
            {watchStatus === "loading" ? "…" : watched.label}
          </SecondaryAction>
        ) : null}
        {chatHref ? (
          <SecondaryAction
            as={Link}
            to={chatHref}
            icon={TITLE_CTA_ICONS.chat}
            label={TITLE_CTA_COPY.chat.label}
            tooltip={TITLE_CTA_COPY.chat.tooltip}
            testId="chat-about-title-link"
            phoneOverflow={TITLE_CTA_PHONE_OVERFLOW.includes("chat")}
            compact={compact}
          />
        ) : null}
        {multiUserEnabled ? (
          <SecondaryAction
            type="button"
            icon={TITLE_CTA_ICONS.watchTogether}
            label={TITLE_CTA_COPY.watchTogether.label}
            tooltip={TITLE_CTA_COPY.watchTogether.tooltip}
            testId="recommend-title-button"
            phoneOverflow={TITLE_CTA_PHONE_OVERFLOW.includes("watchTogether")}
            compact={compact}
            onClick={onOpenRecommend}
          />
        ) : null}
        {secondaryAdd ? (
          <SecondaryAction
            type="button"
            icon={TITLE_CTA_ICONS.add}
            label={secondaryAdd.label}
            tooltip={secondaryAdd.tooltip || TITLE_CTA_COPY.add.tooltip}
            testId="title-detail-add-button"
            phoneOverflow={TITLE_CTA_PHONE_OVERFLOW.includes("add")}
            compact={compact}
            disabled={secondaryAdd.disabled}
            onClick={secondaryAdd.onClick}
          />
        ) : null}

        {showMore ? (
          <button
            type="button"
            className="title-cta title-cta-ghost title-cta-secondary title-cta-icon-forward"
            data-testid={moreTestId}
            aria-label={TITLE_CTA_COPY.more.tooltip}
            title={TITLE_CTA_COPY.more.tooltip}
            aria-expanded={open}
            aria-haspopup="menu"
            onClick={() => setOpen((value) => !value)}
          >
            <CtaIcon name={TITLE_CTA_ICONS.more} />
            <span className="title-cta-secondary-label">{TITLE_CTA_COPY.more.label}</span>
          </button>
        ) : null}
      </div>

      {moreMenu}
    </div>
  );
}
