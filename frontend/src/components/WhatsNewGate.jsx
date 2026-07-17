import { useEffect, useState } from "react";
import { getHealth } from "../api/client";
import {
  fetchReleaseNotes,
  findReleaseByVersion,
  getLastSeenVersion,
  normalizeReleaseNotes,
  setLastSeenVersion,
  shouldShowWhatsNew,
} from "../lib/releaseNotes.js";
import WhatsNewModal from "./WhatsNewModal";

/**
 * Compares runtime /api/health version to localStorage last-seen.
 * Shows What’s New for the newest release only after an upgrade.
 */
export default function WhatsNewGate() {
  const [open, setOpen] = useState(false);
  const [version, setVersion] = useState("");
  const [release, setRelease] = useState(null);

  useEffect(() => {
    let cancelled = false;

    async function evaluate() {
      try {
        const health = await getHealth();
        const runtimeVersion = String(health?.version || "").trim();
        if (!runtimeVersion || cancelled) return;

        const lastSeen = getLastSeenVersion();
        if (!lastSeen) {
          // First visit: remember current version without interrupting onboarding.
          setLastSeenVersion(runtimeVersion);
          return;
        }

        if (!shouldShowWhatsNew(runtimeVersion, lastSeen)) return;

        let matched = null;
        try {
          const payload = await fetchReleaseNotes();
          const releases = normalizeReleaseNotes(payload);
          matched =
            findReleaseByVersion(releases, runtimeVersion) ||
            releases[0] ||
            null;
        } catch {
          matched = null;
        }

        if (cancelled) return;
        setVersion(runtimeVersion);
        setRelease(matched);
        setOpen(true);
      } catch {
        // Health unavailable — skip quietly.
      }
    }

    evaluate();
    return () => {
      cancelled = true;
    };
  }, []);

  function dismiss() {
    if (version) setLastSeenVersion(version);
    setOpen(false);
  }

  function onReadFull() {
    if (version) setLastSeenVersion(version);
    setOpen(false);
  }

  return (
    <WhatsNewModal
      open={open}
      version={version}
      release={release}
      onDismiss={dismiss}
      onReadFull={onReadFull}
    />
  );
}
