type InlineAlertProps = {
  type?: string;
  message?: React.ReactNode;
  testId?: string;
  onDismiss?: (...args: any[]) => void;
};

export default function InlineAlert({ type, message, testId, onDismiss }: InlineAlertProps) {
  if (!message || (type !== "success" && type !== "error")) return null;
  return (
    <div
      className={`inline-alert inline-alert-${type}`}
      role="alert"
      data-testid={testId || `inline-alert-${type}`}
    >
      <span className="inline-alert-message">{message}</span>
      {onDismiss ? (
        <button
          type="button"
          className="inline-alert-dismiss ghost"
          data-testid={testId ? `${testId}-dismiss` : "inline-alert-dismiss"}
          onClick={onDismiss}
          aria-label="Dismiss"
        >
          ×
        </button>
      ) : null}
    </div>
  );
}
