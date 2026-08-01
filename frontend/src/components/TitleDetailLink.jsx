import { Link, useLocation } from "react-router-dom";
import { shouldOpenTitleOverlayClick } from "../lib/titleDetailDrawer.js";
import { titleDetailTo } from "../lib/titleLinks.js";
import { useTitleDetailOverlayOptional } from "./TitleDetailOverlayProvider.jsx";

/**
 * Title detail link that opens the in-place overlay on a plain click.
 * Modified clicks (cmd/ctrl/shift/middle) still navigate to the full page with
 * return-to state for contextual back.
 */
export default function TitleDetailLink({
  item,
  className,
  children,
  onClick,
  replaceOverlayItem,
  ...rest
}) {
  const location = useLocation();
  const overlay = useTitleDetailOverlayOptional();
  const to = titleDetailTo(item, location);
  if (!to) {
    return children;
  }

  return (
    <Link
      to={to}
      className={className}
      onClick={(event) => {
        onClick?.(event);
        if (event.defaultPrevented) return;
        if (!overlay || !shouldOpenTitleOverlayClick(event)) return;
        const opened = overlay.openTitleDetail(replaceOverlayItem || item, {
          triggerEl: event.currentTarget,
        });
        if (opened) event.preventDefault();
      }}
      {...rest}
    >
      {children}
    </Link>
  );
}
