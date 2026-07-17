/** Card panel for a Settings section (matches Admin config-panel patterns). */
export default function SettingsPanel({ title, lead, children, testId, footer }) {
  return (
    <section className="settings-panel config-panel" data-testid={testId}>
      {title || lead ? (
        <header className="config-panel-header settings-panel-header">
          {title ? <h3>{title}</h3> : null}
          {lead ? <p className="config-panel-lead">{lead}</p> : null}
        </header>
      ) : null}
      <div className="settings-panel-body">{children}</div>
      {footer ? <footer className="config-panel-footer settings-panel-footer">{footer}</footer> : null}
    </section>
  );
}
