type ManageToggleProps = {
  on: boolean;
  onToggle: () => void;
  testId: string;
  disabled?: boolean;
};

/** UX-005: owner-only switch that reveals destructive bulk actions on a results toolbar. */
export default function ManageToggle({ on, onToggle, testId, disabled = false }: ManageToggleProps) {
  return (
    <button
      type="button"
      className="ghost"
      data-testid={testId}
      aria-pressed={on}
      disabled={disabled}
      onClick={onToggle}
    >
      {on ? "Done managing" : "Manage"}
    </button>
  );
}
