const SHORTCUTS = [
  { keys: "/", description: "Focus the composer" },
  { keys: "Enter", description: "Send the message" },
  { keys: "Shift + Enter", description: "Insert a newline" },
  { keys: "⌘/Ctrl + N", description: "Start a new conversation" },
  { keys: "Esc", description: "Close the title results overlay" },
  { keys: "?", description: "Show this keyboard shortcut help" },
];

export default function KeyboardHelpModal({ open, onClose, plexCollectionsEnabled = false }) {
  if (!open) return null;

  return (
    <div className="keyboard-help-backdrop" data-testid="keyboard-help-modal" onClick={onClose}>
      <div
        className="keyboard-help-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="keyboard-help-title"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="keyboard-help-header">
          <h2 id="keyboard-help-title">Keyboard shortcuts</h2>
          <button type="button" className="ghost keyboard-help-close" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>
        <ul className="keyboard-help-list">
          {SHORTCUTS.map((entry) => (
            <li key={entry.keys}>
              <kbd>{entry.keys}</kbd>
              <span>{entry.description}</span>
            </li>
          ))}
        </ul>
        <p className="keyboard-help-footnote">
          Slash commands: `/help`, `/stats`, `/sync`, `/purge`{plexCollectionsEnabled ? ", `/collections`" : ""}
        </p>
        <p className="keyboard-help-footnote keyboard-help-privacy">
          <a href="/privacy" data-testid="keyboard-help-privacy-link">
            Privacy &amp; data use
          </a>
        </p>
      </div>
    </div>
  );
}
