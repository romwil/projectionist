import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { saveLibraryPage } from "../api/client";
import { useAnchoredPopover } from "../hooks/useAnchoredPopover";

function libraryUrl(id) {
  return new URL(`/library/${encodeURIComponent(id)}`, window.location.origin).toString();
}

function placeShareMenu(anchor, menu) {
  const margin = 8;
  return {
    top: `${Math.max(margin, Math.min(anchor.bottom + margin, window.innerHeight - menu.height - margin))}px`,
    left: `${Math.max(margin, Math.min(anchor.right - menu.width, window.innerWidth - menu.width - margin))}px`,
  };
}

export default function ShareActionMenu({
  page,
  content,
  name = "Curator response",
  sourceSessionId,
  sourceMessageId,
  extraActions = [],
  onSaved,
  label = "Share and export",
}) {
  const [savedPage, setSavedPage] = useState(page || null);
  const [flash, setFlash] = useState("");
  const savePromiseRef = useRef(null);
  const flashTimerRef = useRef(null);
  const { open, setOpen, rootRef, popoverRef, popoverStyle } = useAnchoredPopover({
    closeOnEscape: true,
    anchorSelector: ".share-action-grip",
    placement: placeShareMenu,
  });

  useEffect(() => setSavedPage(page || null), [page]);

  useEffect(() => {
    return () => {
      if (flashTimerRef.current) clearTimeout(flashTimerRef.current);
    };
  }, []);

  function showFlash(message) {
    setOpen(false);
    setFlash(message);
    if (flashTimerRef.current) clearTimeout(flashTimerRef.current);
    flashTimerRef.current = setTimeout(() => setFlash(""), 2800);
  }

  async function ensureSaved() {
    if (savedPage?.id) return savedPage;
    if (!savePromiseRef.current) {
      savePromiseRef.current = saveLibraryPage({
        name,
        source_session_id: sourceSessionId,
        source_message_id: sourceMessageId,
        content,
      }).then((created) => {
        setSavedPage(created);
        onSaved?.(created);
        return created;
      }).finally(() => {
        savePromiseRef.current = null;
      });
    }
    return savePromiseRef.current;
  }

  async function run(action) {
    try {
      const item = await ensureSaved();
      const url = libraryUrl(item.id);
      if (action === "save") showFlash("Saved to your library.");
      if (action === "copy") {
        await navigator.clipboard?.writeText(url);
        showFlash("Library link copied.");
      }
      if (action.startsWith("export:")) {
        window.open(`/api/saved-library/${encodeURIComponent(item.id)}/export?format=${action.slice(7)}`, "_blank", "noopener");
        showFlash("Export opened.");
      }
      if (action === "pdf") {
        window.open(`${url}?print=1`, "_blank", "noopener");
        showFlash("Print view opened.");
      }
      if (action === "more") {
        if (navigator.share) {
          await navigator.share({ title: item.name, url });
          showFlash("Shared.");
        } else {
          await navigator.clipboard?.writeText(url);
          showFlash("System share is unavailable; link copied.");
        }
      }
    } catch (error) {
      showFlash(error.message || "Could not prepare this library item.");
    }
  }

  const popover = open && typeof document !== "undefined" ? createPortal(
    <div className="share-action-popover" ref={popoverRef} role="menu" style={popoverStyle || { visibility: "hidden" }}>
      <button type="button" onClick={() => run("save")}><span className="material-symbols-outlined">bookmark_add</span>Save to library</button>
      <button type="button" onClick={() => run("copy")}><span className="material-symbols-outlined">content_copy</span>Copy link</button>
      <button type="button" onClick={() => run("export:markdown")}><span className="material-symbols-outlined">download</span>Export Markdown</button>
      <button type="button" onClick={() => run("export:json")}><span className="material-symbols-outlined">data_object</span>Export JSON</button>
      <button type="button" onClick={() => run("export:txt")}><span className="material-symbols-outlined">description</span>Export text</button>
      <button type="button" onClick={() => run("pdf")}><span className="material-symbols-outlined">print</span>Print / PDF</button>
      <button type="button" onClick={() => run("more")}><span className="material-symbols-outlined">ios_share</span>More…</button>
      {extraActions.length ? <div className="share-action-extra">{extraActions.map((action) => (
        <button key={action.label} type="button" onClick={() => { action.onClick(); setOpen(false); }}>
          {action.icon ? <span className="material-symbols-outlined">{action.icon}</span> : null}{action.label}
        </button>
      ))}</div> : null}
    </div>,
    document.body,
  ) : null;

  const flashToast = flash && typeof document !== "undefined" ? createPortal(
    <div className="menu-action-flash" role="status" aria-live="polite" data-testid="share-action-flash">
      {flash}
    </div>,
    document.body,
  ) : null;

  return <div className="share-action-menu" ref={rootRef}>
    <button type="button" className="share-action-grip app-topbar-icon" data-tooltip={label} aria-label={label} aria-expanded={open} onClick={() => setOpen((value) => !value)}>
      <span className="material-symbols-outlined" aria-hidden="true">more_vert</span>
    </button>
    {popover}
    {flashToast}
  </div>;
}
