import { useEffect, useState } from "react";

type InstallPrompt = Event & {
  prompt: () => Promise<void>;
  userChoice?: Promise<{ outcome?: string }>;
};

function runningInstalled() {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return false;
  return (
    window.matchMedia("(display-mode: standalone)").matches ||
    window.matchMedia("(display-mode: window-controls-overlay)").matches
  );
}

/**
 * Quiet install entry. It appears only after the browser offers to install,
 * and it never asks for a notification permission.
 */
export default function InstallProjectionist({ className }: { className: string }) {
  const [promptEvent, setPromptEvent] = useState<InstallPrompt | null>(null);
  const [installed, setInstalled] = useState(runningInstalled);

  useEffect(() => {
    function onPrompt(event: Event) {
      event.preventDefault();
      const candidate = event as InstallPrompt;
      if (typeof candidate.prompt !== "function") return;
      setPromptEvent(candidate);
    }
    function onInstalled() {
      setPromptEvent(null);
      setInstalled(true);
    }
    window.addEventListener("beforeinstallprompt", onPrompt);
    window.addEventListener("appinstalled", onInstalled);
    return () => {
      window.removeEventListener("beforeinstallprompt", onPrompt);
      window.removeEventListener("appinstalled", onInstalled);
    };
  }, []);

  if (installed || !promptEvent) return null;

  return (
    <button
      type="button"
      className={className}
      data-testid="install-projectionist"
      onClick={() => {
        const pending = promptEvent;
        setPromptEvent(null);
        pending.prompt().catch(() => {});
      }}
    >
      Install Projectionist
    </button>
  );
}
