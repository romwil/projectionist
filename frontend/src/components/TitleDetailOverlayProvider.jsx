import { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";
import TitleDetailDrawer from "./TitleDetailDrawer";
import { titleDetailTargetFromItem } from "../lib/titleDetailDrawer.js";

const TitleDetailOverlayContext = createContext(null);

/**
 * App-wide title detail overlay. Poster/card clicks open the drawer modal in
 * place so chat/explore/search scroll position stays underneath.
 */
export function TitleDetailOverlayProvider({ children }) {
  const [target, setTarget] = useState(null);
  const [drawerOptions, setDrawerOptions] = useState({});
  const returnFocusRef = useRef(null);

  const closeTitleDetail = useCallback(() => {
    setTarget(null);
    setDrawerOptions({});
  }, []);

  const openTitleDetail = useCallback((itemOrTarget, options = {}) => {
    const targetFromItem = titleDetailTargetFromItem(itemOrTarget);
    const nextTarget =
      targetFromItem ||
      (itemOrTarget?.mediaType && itemOrTarget?.itemId
        ? {
            mediaType: itemOrTarget.mediaType === "show" ? "show" : "movie",
            itemId: String(itemOrTarget.itemId),
            idType: itemOrTarget.idType || "tmdb",
          }
        : null);
    if (!nextTarget) return false;
    if (options.triggerEl) {
      returnFocusRef.current = options.triggerEl;
    }
    setDrawerOptions({
      onDeleted: options.onDeleted,
      deleteDefaultMode: options.deleteDefaultMode,
      deleteSurface: options.deleteSurface,
    });
    setTarget(nextTarget);
    return true;
  }, []);

  const value = useMemo(
    () => ({
      openTitleDetail,
      closeTitleDetail,
      isOpen: Boolean(target),
    }),
    [closeTitleDetail, openTitleDetail, target],
  );

  return (
    <TitleDetailOverlayContext.Provider value={value}>
      {children}
      <TitleDetailDrawer
        open={Boolean(target)}
        target={target}
        returnFocusRef={returnFocusRef}
        onClose={closeTitleDetail}
        onDeleted={drawerOptions.onDeleted}
        deleteDefaultMode={drawerOptions.deleteDefaultMode}
        deleteSurface={drawerOptions.deleteSurface || ""}
      />
    </TitleDetailOverlayContext.Provider>
  );
}

export function useTitleDetailOverlay() {
  const context = useContext(TitleDetailOverlayContext);
  if (!context) {
    throw new Error("useTitleDetailOverlay must be used inside TitleDetailOverlayProvider");
  }
  return context;
}

/** Soft lookup for optional wiring (e.g. source-scanned helpers). */
export function useTitleDetailOverlayOptional() {
  return useContext(TitleDetailOverlayContext);
}
