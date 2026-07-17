/** Shared Settings page title + lead copy. */
export default function SettingsPageHeader({ title, children, testId }) {
  return (
    <header className="settings-page-header" data-testid={testId}>
      <h2 className="settings-page-title">{title}</h2>
      {children ? <p className="settings-page-lead">{children}</p> : null}
    </header>
  );
}
