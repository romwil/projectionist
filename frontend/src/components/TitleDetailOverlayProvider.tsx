import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import TitleDetailDrawer from "./TitleDetailDrawer";
import { titleDetailTargetFromItem } from "../lib/titleDetailDrawer.js";

type TitleDetailTarget = {
  mediaType: "movie" | "show";
  itemId: string;
  idType?: string;
};

type OpenTitleDetailOptions = {
  triggerEl?: HTMLElement | null;
  onDeleted?: (info?: unknown) => void;
  deleteDefaultMode?: string;
  deleteSurface?: string;
};

type TitleDetailOverlayApi = {
  openTitleDetail: (itemOrTarget: unknown, options?: OpenTitleDetailOptions) => boolean;
  closeTitleDetail: () => void;
  isOpen: boolean;
};

const TitleDetailOverlayContext = createContext<TitleDetailOverlayApi | null>(null);

type TitleDetailOverlayProviderProps = {
  children?: React.ReactNode;
};

/**
 * App-wide title detail overlay. Poster/card clicks open the drawer modal in
 * place so chat/explore/search scroll position stays underneath.
 */
export function TitleDetailOverlayProvider({ children }: TitleDetailOverlayProviderProps) {
  const location = useLocation();
  const [target, setTarget] = useState<TitleDetailTarget | null>(null);
  const [drawerOptions, setDrawerOptions] = useState<OpenTitleDetailOptions>({});
  const returnFocusRef = useRef<any>(null);

  const closeTitleDetail = useCallback(() => {
    setTarget(null);
    setDrawerOptions({});
  }, []);

  useEffect(() => {
    const path = location.pathname || "";
    if (path.startsWith("/watch/") || path === "/live/watch" || path === "/live/popout") {
      closeTitleDetail();
    }
  }, [location.pathname, closeTitleDetail]);

  const openTitleDetail = useCallback((itemOrTarget: unknown, options: OpenTitleDetailOptions = {}) => {
    const targetFromItem = titleDetailTargetFromItem(itemOrTarget);
    const raw = itemOrTarget as { mediaType?: string; itemId?: string | number; idType?: string } | null;
    const nextTarget: any =
      targetFromItem ||
      (raw?.mediaType && raw?.itemId
        ? {
            mediaType: raw.mediaType === "show" ? "show" : "movie",
            itemId: String(raw.itemId),
            idType: raw.idType || "tmdb",
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
