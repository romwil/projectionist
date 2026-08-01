import { useEffect } from "react";
import TitleDetailLink from "../TitleDetailLink.jsx";
import { buildProgramHoverModel } from "../../lib/liveProgramDetail.js";

/**
 * Hover / focus popup for a Live guide pod or Up-next chip.
 * Clickable when a dig-in target exists (opens the chat-style title overlay).
 */
export default function LiveProgramHoverCard({
  program,
  kind = "guide",
  open,
  x = 0,
  y = 0,
  onClose,
  onKeepAlive,
  onDigIn,
}) {
  const model = buildProgramHoverModel(program, { kind });

  useEffect(() => {
    if (!open) return undefined;
    function onKey(event) {
      if (event.key === "Escape") onClose?.();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!model || !open) return null;

  const metaBits = [
    model.rating,
    model.year && model.subtitle !== model.year ? model.year : "",
  ].filter(Boolean);

  const body = (
    <>
      <p className="live-program-hover-eyebrow">{model.eyebrow}</p>
      <strong className="live-program-hover-title">{model.title}</strong>
      {model.subtitle ? (
        <p className="live-program-hover-subtitle">{model.subtitle}</p>
      ) : null}
      {metaBits.length ? (
        <p className="live-program-hover-meta">{metaBits.join(" · ")}</p>
      ) : null}
      {model.overview ? (
        <p className="live-program-hover-overview">{model.overview}</p>
      ) : null}
      {model.digInItem ? (
        <p className="live-program-hover-hint">Open title details</p>
      ) : null}
    </>
  );

  const style = {
    left: Math.max(
      8,
      Math.min(x, (typeof window !== "undefined" ? window.innerWidth : 400) - 280),
    ),
    top: Math.max(8, y),
  };

  const sharedProps = {
    className: "live-program-hover",
    "data-testid": "live-program-hover",
    style,
    onMouseEnter: () => onKeepAlive?.(),
    onMouseLeave: () => onClose?.(),
  };

  if (model.digInItem) {
    return (
      <TitleDetailLink
        item={model.digInItem}
        {...sharedProps}
        onClick={(event) => {
          event.stopPropagation();
          onDigIn?.(model.digInItem);
          onClose?.();
        }}
      >
        {body}
      </TitleDetailLink>
    );
  }

  return (
    <div {...sharedProps} role="dialog" aria-label={model.title}>
      {body}
    </div>
  );
}
