import TitleCard from "./TitleCard";

export default function DoubleFeatureCard({
  titleA,
  titleB,
  bridgeText,
  combinedRuntime,
  onAdd,
  onDismiss,
  requestPath = "arr",
  userRole,
  multiUserEnabled = true,
}) {
  return (
    <div className="double-feature-card" data-testid="double-feature-card">
      <div className="double-feature-pair">
        <div className="double-feature-slot">
          <TitleCard
            item={titleA}
            compact
            onAdd={onAdd}
            onDismiss={onDismiss}
            requestPath={requestPath}
            userRole={userRole}
            multiUserEnabled={multiUserEnabled}
          />
        </div>
        <div className="double-feature-bridge" data-testid="double-feature-bridge">
          <span className="double-feature-bridge-icon" aria-hidden="true">⟷</span>
          <p className="double-feature-bridge-text">{bridgeText}</p>
        </div>
        <div className="double-feature-slot">
          <TitleCard
            item={titleB}
            compact
            onAdd={onAdd}
            onDismiss={onDismiss}
            requestPath={requestPath}
            userRole={userRole}
            multiUserEnabled={multiUserEnabled}
          />
        </div>
      </div>
      {combinedRuntime ? (
        <p className="double-feature-runtime" data-testid="double-feature-runtime">
          Combined runtime: {Math.floor(combinedRuntime / 60)}h {combinedRuntime % 60}m
        </p>
      ) : null}
    </div>
  );
}
