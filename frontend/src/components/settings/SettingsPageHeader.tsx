type SettingsPageHeaderProps = {
  title?: any;
  children?: React.ReactNode;
  testId?: string;
  lead?: React.ReactNode;
};

/** Shared Settings page title + lead copy. */
export default function SettingsPageHeader({ title, children, testId, lead }: SettingsPageHeaderProps) {
  const copy = children ?? lead;
  return (
    <header className="settings-page-header" data-testid={testId}>
      <h2 className="settings-page-title">{title}</h2>
      {copy ? <p className="settings-page-lead">{copy}</p> : null}
    </header>
  );
}
