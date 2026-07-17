/** Accessible toggle switch for Settings boolean prefs. */
export default function SettingsToggle({
  checked,
  disabled,
  onChange,
  label,
  help,
  testId,
  id,
}) {
  const inputId = id || testId;
  return (
    <div className="settings-toggle-field" data-testid={testId}>
      <label className="settings-switch" htmlFor={inputId}>
        <input
          id={inputId}
          type="checkbox"
          role="switch"
          checked={Boolean(checked)}
          disabled={disabled}
          onChange={(event) => onChange?.(event.target.checked)}
        />
        <span className="settings-switch-track" aria-hidden="true" />
        <span className="settings-switch-label">{label}</span>
      </label>
      {help ? <p className="field-help settings-toggle-help">{help}</p> : null}
    </div>
  );
}
