import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getWeeklyLetter, saveWeeklyLetterSettings, sendWeeklyLetterNow } from "../../api/client";
import InlineAlert from "../InlineAlert";
import SettingsPanel from "../settings/SettingsPanel";

/**
 * Owner controls for the weekly household letter (Ops → Newsletters).
 * The letter lands in the owner's inbox each week; email is an extra opt-in
 * that only works once Mail is configured. Never required for inbox delivery.
 */
export default function WeeklyLetterPanel({ testIdPrefix = "newsletters" }) {
  const [state, setState] = useState(null);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState(null);

  useEffect(() => {
    let cancelled = false;
    getWeeklyLetter()
      .then((data) => {
        if (!cancelled) setState(data);
      })
      .catch((error) => {
        if (!cancelled) {
          setStatus({ type: "error", message: error?.message || "Could not load the weekly letter." });
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function save(patch) {
    setBusy(true);
    setStatus(null);
    try {
      const next = await saveWeeklyLetterSettings(patch);
      setState((prev) => ({ ...(prev || {}), ...next }));
    } catch (error) {
      setStatus({ type: "error", message: error?.message || "Could not save." });
    } finally {
      setBusy(false);
    }
  }

  async function sendNow() {
    setBusy(true);
    setStatus(null);
    try {
      const result = await sendWeeklyLetterNow();
      setState((prev) => ({ ...(prev || {}), ...result }));
      setStatus({
        type: "success",
        message: result?.emailed
          ? "This week’s letter is in your inbox and on its way by email."
          : "This week’s letter is in your inbox.",
      });
    } catch (error) {
      setStatus({ type: "error", message: error?.message || "Could not send the letter." });
    } finally {
      setBusy(false);
    }
  }

  const mailReady = Boolean(state?.mail_configured);
  const letter = state?.letter;

  return (
    <SettingsPanel
      title="Weekly household letter"
      lead="A short letter about the house — unwatched hours, dead weight, and disk — lands in your inbox once a week. It never starts a purge; open Health when you want the house lighter."
      testId={`${testIdPrefix}-letter-panel`}
    >
      <label className="settings-toggle" data-testid={`${testIdPrefix}-letter-weekly`}>
        <input
          type="checkbox"
          checked={Boolean(state?.weekly)}
          disabled={!state || busy}
          onChange={(event) => save({ weekly: event.target.checked })}
        />
        <span>Send me the letter every week</span>
      </label>
      <label className="settings-toggle" data-testid={`${testIdPrefix}-letter-email`}>
        <input
          type="checkbox"
          checked={Boolean(state?.email) && mailReady}
          disabled={!state || busy || !mailReady}
          onChange={(event) => save({ email: event.target.checked })}
        />
        <span>Also email it to me</span>
      </label>
      <p className="settings-field-hint" data-testid={`${testIdPrefix}-letter-email-hint`}>
        {mailReady ? (
          "Uses the same outbound mail as the newsletters."
        ) : (
          <>
            Email is off until <Link to="/admin/mail">Mail</Link> is configured. The letter still
            arrives in your inbox.
          </>
        )}
      </p>
      {letter?.body ? (
        <details className="settings-details" data-testid={`${testIdPrefix}-letter-preview`}>
          <summary>Preview this week’s letter</summary>
          <p>{letter.salutation}</p>
          {String(letter.body)
            .split(/\n{2,}/)
            .map((para, index) => (
              <p key={index}>{para}</p>
            ))}
          <p>{letter.signoff}</p>
        </details>
      ) : null}
      <div className="settings-actions">
        <button
          type="button"
          className="ghost"
          onClick={sendNow}
          disabled={!state || busy}
          data-testid={`${testIdPrefix}-letter-send`}
        >
          Put this week’s letter in my inbox now
        </button>
      </div>
      <InlineAlert
        type={status?.type || null}
        message={status?.message || null}
        testId={`${testIdPrefix}-letter-status`}
        onDismiss={() => setStatus(null)}
      />
    </SettingsPanel>
  );
}
