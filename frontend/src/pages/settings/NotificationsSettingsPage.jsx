import { useEffect, useState } from "react";
import { generateWeeklyNewsletter, getAuthMe, patchAuthMe } from "../../api/client";
import SettingsPageHeader from "../../components/settings/SettingsPageHeader";
import SettingsPanel from "../../components/settings/SettingsPanel";
import SettingsToggle from "../../components/settings/SettingsToggle";
import {
  newsletterConfirmMessage,
  newsletterResultMessage,
} from "../../lib/weeklyNewsletter.js";

export default function NotificationsSettingsPage() {
  const [notificationEmail, setNotificationEmail] = useState("");
  const [inboxOn, setInboxOn] = useState(true);
  const [emailOn, setEmailOn] = useState(false);
  const [newsletterOn, setNewsletterOn] = useState(false);
  const [nudgeOn, setNudgeOn] = useState(false);
  const [isOwner, setIsOwner] = useState(false);
  const [status, setStatus] = useState(null);
  const [saving, setSaving] = useState(false);
  const [ready, setReady] = useState(false);
  const [sendingSelf, setSendingSelf] = useState(false);
  const [selfStatus, setSelfStatus] = useState(null);

  useEffect(() => {
    getAuthMe()
      .then((payload) => {
        const user = payload?.user || {};
        setNotificationEmail(user.notification_email || user.email || "");
        setInboxOn(user.notify_channel_inbox !== false);
        setEmailOn(Boolean(user.notify_channel_email));
        setNewsletterOn(Boolean(user.newsletter_opt_in));
        setNudgeOn(Boolean(user.nudge_opt_in));
        setIsOwner(user.role === "owner");
        setReady(true);
      })
      .catch(() => setReady(true));
  }, []);

  async function handleSave(event) {
    event.preventDefault();
    setSaving(true);
    setStatus(null);
    try {
      const result = await patchAuthMe({
        notification_email: notificationEmail.trim() || null,
        notify_channel_inbox: inboxOn,
        notify_channel_email: emailOn,
        newsletter_opt_in: newsletterOn,
        nudge_opt_in: nudgeOn,
      });
      const user = result.user || {};
      setNotificationEmail(user.notification_email || user.email || "");
      setInboxOn(user.notify_channel_inbox !== false);
      setEmailOn(Boolean(user.notify_channel_email));
      setNewsletterOn(Boolean(user.newsletter_opt_in));
      setNudgeOn(Boolean(user.nudge_opt_in));
      setStatus({ type: "success", message: "Notification preferences saved." });
    } catch (error) {
      setStatus({ type: "error", message: error.message || "Could not save." });
    } finally {
      setSaving(false);
    }
  }

  async function handleSendSelf() {
    if (!newsletterOn) {
      setSelfStatus({
        type: "error",
        message: "Turn on Weekly newsletter and save before sending yourself a copy.",
      });
      return;
    }
    if (!window.confirm(newsletterConfirmMessage("self"))) return;
    setSendingSelf(true);
    setSelfStatus(null);
    try {
      const result = await generateWeeklyNewsletter({ scope: "self" });
      setSelfStatus({ type: "success", message: newsletterResultMessage(result) });
    } catch (error) {
      setSelfStatus({
        type: "error",
        message: error.message || "Could not send the newsletter.",
      });
    } finally {
      setSendingSelf(false);
    }
  }

  if (!ready) {
    return (
      <div className="settings-stack" data-testid="settings-notifications">
        <SettingsPageHeader title="Notifications">Loading…</SettingsPageHeader>
      </div>
    );
  }

  return (
    <div className="settings-stack" data-testid="settings-notifications">
      <SettingsPageHeader title="Notifications">
        Choose where CuratorX reaches you — the in-app inbox, optional email, and the weekly newsletter.
      </SettingsPageHeader>

      <form onSubmit={handleSave}>
        <SettingsPanel title="Delivery">
          <label className="settings-field">
            <span>Notification email</span>
            <input
              type="email"
              value={notificationEmail}
              onChange={(e) => setNotificationEmail(e.target.value)}
              placeholder="you@example.com"
              data-testid="notifications-email-input"
              autoComplete="email"
            />
            <span className="settings-field-hint">
              Used for optional email alerts. Leave blank to fall back to your account email.
            </span>
          </label>

          <SettingsToggle
            id="notify-inbox"
            checked={inboxOn}
            onChange={setInboxOn}
            label="In-app inbox"
            help="Show recommendations, arrivals, digests, and nudges in CuratorX."
            testId="notifications-inbox-toggle"
          />
          <SettingsToggle
            id="notify-email"
            checked={emailOn}
            onChange={setEmailOn}
            label="Email alerts"
            help="Also send matching alerts by email when the owner has mail configured."
            testId="notifications-email-toggle"
          />
          <SettingsToggle
            id="notify-newsletter"
            checked={newsletterOn}
            onChange={setNewsletterOn}
            label="Weekly newsletter"
            help="Opt in to a personalized weekly note in your default curator’s voice."
            testId="notifications-newsletter-toggle"
          />
          <SettingsToggle
            id="notify-nudge"
            checked={nudgeOn}
            onChange={setNudgeOn}
            label="Curator nudges"
            help="Opt in to occasional “you have to see this” nudges (inbox + email if enabled). Never live session alerts."
            testId="notifications-nudge-toggle"
          />
        </SettingsPanel>

        {status ? (
          <p
            className={`status ${status.type === "error" ? "status-error" : "status-success"}`}
            data-testid="notifications-status"
          >
            {status.message}
          </p>
        ) : null}

        <div className="settings-actions">
          <button type="submit" className="primary" disabled={saving} data-testid="notifications-save">
            {saving ? "Saving…" : "Save preferences"}
          </button>
        </div>
      </form>

      {isOwner ? (
        <SettingsPanel title="Send me this week’s newsletter">
          <p className="settings-field-hint">
            Owners can also push to selected members or everyone under Admin → Mail. This only
            sends to you, and only if Weekly newsletter is on.
          </p>
          <button
            type="button"
            className="ghost"
            onClick={handleSendSelf}
            disabled={sendingSelf}
            data-testid="notifications-newsletter-self-send"
          >
            {sendingSelf ? "Sending…" : "Send to me now"}
          </button>
          {selfStatus ? (
            <p
              className={`status ${selfStatus.type === "error" ? "status-error" : "status-success"}`}
              data-testid="notifications-newsletter-self-status"
            >
              {selfStatus.message}
            </p>
          ) : null}
        </SettingsPanel>
      ) : null}
    </div>
  );
}
