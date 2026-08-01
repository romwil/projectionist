import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { listHouseholdPeers, saveLibraryPage, shareLibraryPage } from "../api/client";
import { useAnchoredPopover } from "../hooks/useAnchoredPopover";
import { libraryShareFlash, librarySharePrivacyNote } from "../lib/householdSocial.js";

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
  allowHouseholdShare = true,
}) {
  const [savedPage, setSavedPage] = useState(page || null);
  const [flash, setFlash] = useState("");
  const [householdOpen, setHouseholdOpen] = useState(false);
  const [peers, setPeers] = useState([]);
  const [selectedPeers, setSelectedPeers] = useState(() => new Set());
  const [peersLoading, setPeersLoading] = useState(false);
  const [peersError, setPeersError] = useState("");
  const [sharingHousehold, setSharingHousehold] = useState(false);
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
    setHouseholdOpen(false);
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
      })
        .then((created) => {
          setSavedPage(created);
          onSaved?.(created);
          return created;
        })
        .finally(() => {
          savePromiseRef.current = null;
        });
    }
    return savePromiseRef.current;
  }

  async function openHouseholdShare() {
    setPeersError("");
    setSelectedPeers(new Set());
    setHouseholdOpen(true);
    setPeersLoading(true);
    try {
      await ensureSaved();
      const data = await listHouseholdPeers();
      setPeers(data.items || []);
      if (!(data.items || []).length) {
        setPeersError("No other household members yet.");
      }
    } catch (error) {
      setPeersError(error.message || "Could not load household members.");
    } finally {
      setPeersLoading(false);
    }
  }

  function togglePeer(id) {
    setSelectedPeers((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function sendHouseholdShare() {
    if (!selectedPeers.size) {
      setPeersError("Pick at least one person.");
      return;
    }
    setSharingHousehold(true);
    setPeersError("");
    try {
      const item = await ensureSaved();
      await shareLibraryPage(item.id, { to_user_ids: [...selectedPeers] });
      showFlash(libraryShareFlash("share-household"));
    } catch (error) {
      setPeersError(error.message || "Could not share with household.");
    } finally {
      setSharingHousehold(false);
    }
  }

  async function run(action) {
    try {
      const item = await ensureSaved();
      const url = libraryUrl(item.id);
      if (action === "save") showFlash(libraryShareFlash("save"));
      if (action === "copy") {
        await navigator.clipboard?.writeText(url);
        showFlash(libraryShareFlash("copy"));
      }
      if (action.startsWith("export:")) {
        window.open(
          `/api/saved-library/${encodeURIComponent(item.id)}/export?format=${action.slice(7)}`,
          "_blank",
          "noopener",
        );
        showFlash(libraryShareFlash(action));
      }
      if (action === "pdf") {
        window.open(`${url}?print=1`, "_blank", "noopener");
        showFlash(libraryShareFlash("pdf"));
      }
      if (action === "household") {
        await openHouseholdShare();
        return;
      }
      if (action === "more") {
        if (navigator.share) {
          await navigator.share({
            title: item.name,
            text: librarySharePrivacyNote(),
            url,
          });
          showFlash(libraryShareFlash("more"));
        } else {
          await navigator.clipboard?.writeText(url);
          showFlash(libraryShareFlash("copy"));
        }
      }
    } catch (error) {
      showFlash(error.message || "Could not prepare this library item.");
    }
  }

  const popover =
    open && typeof document !== "undefined"
      ? createPortal(
          <div
            className="share-action-popover"
            ref={popoverRef}
            role="menu"
            style={popoverStyle || { visibility: "hidden" }}
          >
            <p className="share-action-privacy" data-testid="share-action-privacy">
              {librarySharePrivacyNote()}
            </p>
            <button type="button" onClick={() => run("save")}>
              <span className="material-symbols-outlined">bookmark_add</span>Save to library
            </button>
            <button type="button" onClick={() => run("copy")}>
              <span className="material-symbols-outlined">content_copy</span>Copy household link
            </button>
            {allowHouseholdShare ? (
              <button type="button" data-testid="share-action-household" onClick={() => run("household")}>
                <span className="material-symbols-outlined">group</span>Share with household…
              </button>
            ) : null}
            <button type="button" onClick={() => run("export:markdown")}>
              <span className="material-symbols-outlined">download</span>Export Markdown
            </button>
            <button type="button" onClick={() => run("export:json")}>
              <span className="material-symbols-outlined">data_object</span>Export JSON
            </button>
            <button type="button" onClick={() => run("export:txt")}>
              <span className="material-symbols-outlined">description</span>Export text
            </button>
            <button type="button" onClick={() => run("pdf")}>
              <span className="material-symbols-outlined">print</span>Print / PDF
            </button>
            <button type="button" onClick={() => run("more")}>
              <span className="material-symbols-outlined">ios_share</span>More…
            </button>
            {householdOpen ? (
              <div className="share-household-panel" data-testid="share-household-panel">
                <p className="share-household-lead">Notify household members (they open your private page).</p>
                {peersLoading ? <p className="status status-secondary">Loading household…</p> : null}
                {!peersLoading && peers.length ? (
                  <ul className="share-household-peers">
                    {peers.map((peer) => {
                      const checked = selectedPeers.has(peer.id);
                      return (
                        <li key={peer.id}>
                          <label className={checked ? "selected" : undefined}>
                            <input
                              type="checkbox"
                              checked={checked}
                              onChange={() => togglePeer(peer.id)}
                              data-testid={`share-household-peer-${peer.id}`}
                            />
                            <span>{peer.display_name}</span>
                          </label>
                        </li>
                      );
                    })}
                  </ul>
                ) : null}
                {peersError ? (
                  <p className="status status-error" data-testid="share-household-error">
                    {peersError}
                  </p>
                ) : null}
                <div className="share-household-actions">
                  <button type="button" className="ghost" onClick={() => setHouseholdOpen(false)}>
                    Cancel
                  </button>
                  <button
                    type="button"
                    data-testid="share-household-send"
                    disabled={sharingHousehold || !peers.length || !selectedPeers.size}
                    onClick={sendHouseholdShare}
                  >
                    {sharingHousehold ? "Sharing…" : "Send"}
                  </button>
                </div>
              </div>
            ) : null}
            {extraActions.length ? (
              <div className="share-action-extra">
                {extraActions.map((action) => (
                  <button
                    key={action.label}
                    type="button"
                    onClick={() => {
                      action.onClick();
                      setOpen(false);
                    }}
                  >
                    {action.icon ? <span className="material-symbols-outlined">{action.icon}</span> : null}
                    {action.label}
                  </button>
                ))}
              </div>
            ) : null}
          </div>,
          document.body,
        )
      : null;

  const flashToast =
    flash && typeof document !== "undefined"
      ? createPortal(
          <div className="menu-action-flash" role="status" aria-live="polite" data-testid="share-action-flash">
            {flash}
          </div>,
          document.body,
        )
      : null;

  return (
    <div className="share-action-menu" ref={rootRef}>
      <button
        type="button"
        className="share-action-grip app-topbar-icon"
        data-tooltip={label}
        aria-label={label}
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <span className="material-symbols-outlined" aria-hidden="true">
          more_vert
        </span>
      </button>
      {popover}
      {flashToast}
    </div>
  );
}
