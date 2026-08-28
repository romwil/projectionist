const DEFAULT_GREETING = "Hi — I'm {curator_name}. What should we dig into today?";
const DEFAULT_STARTERS = [
  "Suggest something unwatched from my library",
  "What's good for a cozy Sunday?",
  "Find neo-noir films under two hours",
];

export default function WelcomePanel({
  curatorName = "Curator",
  greeting,
  starters,
  onStarterSelect,
  contextChips,
  onContextChip,
}) {
  const resolvedGreeting =
    greeting ||
    DEFAULT_GREETING.replace("{curator_name}", curatorName);
  const resolvedStarters = starters?.length ? starters : DEFAULT_STARTERS;

  return (
    <section className="welcome-panel" data-testid="welcome-panel" aria-label="Welcome">
      <p className="welcome-panel-greeting">{resolvedGreeting}</p>
      <p className="welcome-panel-hint">
        Try a starter prompt, or type `/help` for slash commands. Sync your Plex library from Config when you are ready.
      </p>
      {contextChips?.length ? (
        <div className="welcome-panel-context" data-testid="welcome-panel-context">
          {contextChips.map((chip) => (
            <button
              key={chip.id}
              type="button"
              className="welcome-context-chip"
              data-testid={chip.testId}
              onClick={() => onContextChip?.(chip)}
            >
              {chip.label}
            </button>
          ))}
        </div>
      ) : null}
      <div className="welcome-panel-starters">
        {resolvedStarters.map((prompt) => (
          <button
            key={prompt}
            type="button"
            className="welcome-starter-chip"
            onClick={() => onStarterSelect?.(prompt)}
          >
            {prompt}
          </button>
        ))}
      </div>
    </section>
  );
}
