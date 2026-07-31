import { tokenConfirmButtonLabel } from "../lib/addActions";

export default function ConfirmAllButton({ count, target, onClick, disabled = false, variant, tokenActions = [] }) {
  const resolvedVariant = variant || (target ? target : "tokens");
  // Token confirms (agent propose → confirm) support a single pending action;
  // title-card "Confirm all" batches still require 2+ addable items.
  const minCount = resolvedVariant === "tokens" ? 1 : 2;
  if (count < minCount) return null;

  const label =
    resolvedVariant === "tokens"
      ? tokenConfirmButtonLabel(count, tokenActions)
      : resolvedVariant === "seerr"
        ? `Confirm all ${count} in Seerr`
        : resolvedVariant === "sonarr"
          ? `Confirm all ${count} to Sonarr`
          : `Confirm all ${count} to Radarr`;

  return (
    <button
      type="button"
      className="confirm-all-button"
      data-testid={resolvedVariant === "tokens" ? "confirm-all-tokens" : `confirm-all-${resolvedVariant}`}
      onClick={onClick}
      disabled={disabled}
    >
      {label}
    </button>
  );
}
