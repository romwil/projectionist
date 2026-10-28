import { useEffect, useLayoutEffect, useRef, useState, type KeyboardEvent, type MouseEvent, type ReactElement, type ReactNode } from "react";
import { createPortal } from "react-dom";
import TitleDetailLink from "../TitleDetailLink";
import { buildProgramHoverModel } from "../../lib/liveProgramDetail.js";
import { placeProgramHoverCard } from "../../lib/liveProgramHover.js";

export type LiveProgramHoverKind = "now" | "next" | "guide";

export type LiveProgramHoverAnchor = {
  top: number;
  bottom: number;
  left: number;
};

export type LiveProgramHoverCardProps = {
  program?: Record<string, unknown> | null;
  kind?: LiveProgramHoverKind;
  open?: boolean;
  anchor?: LiveProgramHoverAnchor | null;
  x?: number;
  y?: number;
  onClose?: (...args: any[]) => void;
  onKeepAlive?: (...args: any[]) => void;
  onDigIn?: (item: Record<string, unknown>) => void;
};

type HoverPlacement = {
  top: number;
  left: number;
  maxHeight: number;
  visibleHeight: number;
  openUp: boolean;
  viewLinkTop: number;
  viewLinkBottom: number;
  bodyMax: number;
  key: string;
};

type HoverBounds = {
  top: number;
  right: number;
  bottom: number;
  left: number;
};

type HoverModel = {
  title?: string;
  overview?: string;
  eyebrow?: string;
  subtitle?: string;
  rating?: string;
  digInItem?: Record<string, unknown> | null;
};

// Sibling TitleDetailLink still infers replaceOverlayItem as required (no default).
const TitleLink = TitleDetailLink as unknown as (props: {
  item: Record<string, unknown>;
  className?: string;
  onClick?: (event: MouseEvent<HTMLAnchorElement>) => void;
  children?: ReactNode;
}) => ReactElement | null;

/**
 * Visible guide (or Live page) box the card must stay inside.
 * The card is portaled to document.body, so this is read from the page.
 */
function visibleHoverBounds(): HoverBounds | null {
  if (typeof document === "undefined") return null;
  const boundsEl =
    document.querySelector("[data-testid='live-guide']") ||
    document.querySelector("[data-testid='live-page']") ||
    document.querySelector("[data-testid='live-watch-page']");
  const rect = boundsEl?.getBoundingClientRect?.();
  if (rect && rect.height > 0 && rect.width > 0) {
    return { top: rect.top, right: rect.right, bottom: rect.bottom, left: rect.left };
  }
  if (typeof window === "undefined") return null;
  return { top: 0, right: window.innerWidth, bottom: window.innerHeight, left: 0 };
}

/**
 * Hover / focus popup for a Live guide pod or Up-next chip.
 * Clickable when a dig-in target exists (opens the chat-style title overlay).
 * Portaled so an overflow:hidden page shell cannot clip the synopsis or the view link.
 */
export default function LiveProgramHoverCard({
  program,
  kind = "guide",
  open,
  anchor = null,
  x = 0,
  y = 0,
  onClose,
  onKeepAlive,
  onDigIn,
}: LiveProgramHoverCardProps) {
  const model = buildProgramHoverModel(program, { kind }) as HoverModel | null;
  const cardRef = useRef<HTMLDivElement | null>(null);
  const [placed, setPlaced] = useState<HoverPlacement | null>(null);
  const anchorTop = anchor?.top ?? y;
  const anchorBottom = anchor?.bottom ?? y;
  const anchorLeft = anchor?.left ?? x;
  const anchorKey = `${anchorTop}|${anchorBottom}|${anchorLeft}|${model?.title || ""}|${model?.overview || ""}`;

  useEffect(() => {
    if (!open) return undefined;
    function onKey(event: KeyboardEvent | globalThis.KeyboardEvent) {
      if (event.key === "Escape") onClose?.();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  useLayoutEffect(() => {
    if (!open || !model) {
      setPlaced(null);
      return;
    }
    const el = cardRef.current;
    const bounds = visibleHoverBounds();
    if (!el || !bounds) return;
    const hint = el.querySelector(".live-program-hover-hint") as HTMLElement | null;
    const linkHeight = hint ? hint.offsetHeight : 0;
    const border = el.offsetHeight - el.clientHeight;
    const next = placeProgramHoverCard({
      anchor: { top: anchorTop, bottom: anchorBottom, left: anchorLeft },
      cardWidth: el.offsetWidth,
      cardHeight: el.offsetHeight,
      bounds,
      linkHeight,
    });
    const bodyMax = Math.max(0, next.maxHeight - linkHeight - border);
    setPlaced((prev) => {
      if (
        prev &&
        prev.key === anchorKey &&
        prev.top === next.top &&
        prev.left === next.left &&
        prev.bodyMax === bodyMax &&
        prev.openUp === next.openUp
      ) {
        return prev;
      }
      return { ...next, bodyMax, key: anchorKey };
    });
  }, [open, model, anchorKey, anchorTop, anchorBottom, anchorLeft]);

  if (!model || !open || typeof document === "undefined") return null;

  const metaBits = [model.rating].filter(Boolean);

  const copy = (
    <div
      className="live-program-hover-body"
      style={placed && placed.key === anchorKey ? { maxHeight: placed.bodyMax } : undefined}
    >
      <p className="live-program-hover-eyebrow">{model.eyebrow}</p>
      <strong className="live-program-hover-title">{model.title}</strong>
      {model.subtitle ? <p className="live-program-hover-subtitle">{model.subtitle}</p> : null}
      {metaBits.length ? <p className="live-program-hover-meta">{metaBits.join(" · ")}</p> : null}
      {model.overview ? <p className="live-program-hover-overview">{model.overview}</p> : null}
    </div>
  );

  const hint = model.digInItem ? (
    <p className="live-program-hover-hint">Open title details</p>
  ) : null;

  const ready = placed && placed.key === anchorKey;
  const style = ready
    ? { left: placed.left, top: placed.top, visibility: "visible" as const }
    : { left: anchorLeft, top: anchorBottom, visibility: "hidden" as const };

  const inner = model.digInItem ? (
    <TitleLink
      item={model.digInItem}
      className="live-program-hover-link"
      onClick={(event) => {
        event.stopPropagation();
        onDigIn?.(model.digInItem as Record<string, unknown>);
        onClose?.();
      }}
    >
      {copy}
      {hint}
    </TitleLink>
  ) : (
    <div className="live-program-hover-link" role="dialog" aria-label={model.title}>
      {copy}
      {hint}
    </div>
  );

  return createPortal(
    <div
      className="live-program-hover"
      data-testid="live-program-hover"
      data-placement={ready ? (placed.openUp ? "above" : "below") : "pending"}
      style={style}
      ref={cardRef}
      onMouseEnter={() => onKeepAlive?.()}
      onMouseLeave={() => onClose?.()}
    >
      {inner}
    </div>,
    document.body,
  );
}
