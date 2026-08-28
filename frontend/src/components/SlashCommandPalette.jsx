export default function SlashCommandPalette({ items = [], activeIndex = 0, onSelect, onHover }) {
  if (!items.length) return null;
  return (
    <ul className="slash-command-palette" role="listbox" aria-label="Slash commands" data-testid="slash-command-palette">
      {items.map((entry, index) => (
        <li key={entry.command} role="presentation">
          <button type="button" role="option" aria-selected={index === activeIndex} className={`slash-command-palette-item${index === activeIndex ? " is-active" : ""}`} data-testid={`slash-command-${entry.command}`} onMouseEnter={() => onHover?.(index)} onMouseDown={(e) => { e.preventDefault(); onSelect?.(entry); }}>
            <span className="slash-command-palette-cmd">/{entry.command}</span>
            <span className="slash-command-palette-summary">{entry.summary}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}
