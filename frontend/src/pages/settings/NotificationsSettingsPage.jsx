import { useEffect, useState } from "react";
import {
  generateWeeklyNewsletter,
  getAuthMe,
  getFeatures,
  patchAuthMe,
} from "../../api/client";
import AppriseDestinationsEditor from "../../components/settings/AppriseDestinationsEditor";
import SettingsPageHeader from "../../components/settings/SettingsPageHeader";
import SettingsPanel from "../../components/settings/SettingsPanel";
import SettingsToggle from "../../components/settings/SettingsToggle";
import {
  parseAppriseDestinationRows,
  serializeAppriseDestinationRows,
} from "../../lib/appriseDestinations.js";
import {
  newsletterConfirmMessage,
  newsletterResultMessage,
} from "../../lib/weeklyNewsletter.js";

function ChannelRequirementBadge({ requiresOwner, available, ownerConfigured }) {
  if (requiresOwner) {
    return (
      <span
        className={`settings-channel-badge ${available ? "is-ready" : "is-owner-required"}`}
        data-testid="channel-badge-owner-required"
      >
        {available ? "Owner configured" : "Needs owner setup"}
      </span>
    );
  }
  if (ownerConfigured) {
    return (
      <span className="settings-channel-badge is-ready" data-testid="channel-badge-self-serve">
        Self-serve · household URLs on
      </span>
    );
  }
  return (
    <span className="settings-channel-badge is-self-serve" data-testid="channel-badge-self-serve">
      Self-serve
    </span>
  );
}

export default function NotificationsSettingsPage() {
  const [notificationEmail, setNotificationEmail] = useState("");
  const [inboxOn, setInboxOn] = useState(true);
  const [emailOn, setEmailOn] = useState(false);
  const [appriseOn, setAppriseOn] = useState(false);
  const [appriseRows, setAppriseRows] = useState([]);
  const [newsletterOn, setNewsletterOn] = useState(false);
  const [nudgeOn, setNudgeOn] = useState(false);
  const [isOwner, setIsOwner] = useState(false);
  const [channels, setChannels] = useState([]);
  const [mailConfigured, setMailConfigured] = useState(false);
  const [status, setStatus] = useState(null);
  const [saving, setSaving] = useState(false);
  const [ready, setReady] = useState(false);
  const [sendingSelf, setSendingSelf] = useState(false);
  const [selfStatus, setSelfStatus] = useState(null);

  useEffect(() => {
    Promise.all([getAuthMe(), getFeatures().catch(() => null)])
      .then(([payload, features]) => {
        const user = payload?.user || {};
        setNotificationEmail(user.notification_email || user.email || "");
        setInboxOn(user.notify_channel_inbox !== false);
        setEmailOn(Boolean(user.notify_channel_email));
        setAppriseOn(Boolean(user.notify_channel_apprise));
        setAppriseRows(parseAppriseDestinationRows(user.apprise_urls || ""));
        setNewsletterOn(Boolean(user.newsletter_opt_in));
        setNudgeOn(Boolean(user.nudge_opt_in));
        setIsOwner(user.role === "owner");
        const offerings = features?.notifications?.channels;
        setChannels(Array.isArray(offerings) ? offerings : []);
        setMailConfigured(Boolean(features?.notifications?.mail_configured));
        setReady(true);
      })
      .catch(() => setReady(true));
  }, []);

  function channelMeta(id) {
    return channels.find((entry) => entry.id === id) || null;
  }

  async function handleSave(event) {
    event.preventDefault();
    setSaving(true);
    setStatus(null);
    try {
      const result = await patchAuthMe({
        notification_email: notificationEmail.trim() || null,
        notify_channel_inbox: inboxOn,
        notify_channel_email: emailOn,
        notify_channel_apprise: appriseOn,
        apprise_urls: serializeAppriseDestinationRows(appriseRows) || null,
        newsletter_opt_in: newsletterOn,
        nudge_opt_in: nudgeOn,
      });
      const user = result.user || {};
      setNotificationEmail(user.notification_email || user.email || "");
      setInboxOn(user.notify_channel_inbox !== false);
      setEmailOn(Boolean(user.notify_channel_email));
      setAppriseOn(Boolean(user.notify_channel_apprise));
      setAppriseRows(parseAppriseDestinationRows(user.apprise_urls || ""));
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

  const emailMeta = channelMeta("email");
  const appriseMeta = channelMeta("apprise");
  const emailAvailable = emailMeta ? Boolean(emailMeta.available) : mailConfigured;
  const appriseAvailable = appriseMeta ? Boolean(appriseMeta.available) : true;

  return (
    <div className="settings-stack" data-testid="settings-notifications">
      <SettingsPageHeader title="Notifications">
        Choose where Projectionist reaches you — inbox, email, Apprise destinations, and the weekly
        newsletter. Badges mark channels that need owner/server setup versus ones you can configure
        yourself.
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

          <div className="settings-channel-row">
            <SettingsToggle
              id="notify-inbox"
              checked={inboxOn}
              onChange={setInboxOn}
              label="In-app inbox"
              help="Show recommendations, arrivals, digests, and nudges in Projectionist."
              testId="notifications-inbox-toggle"
            />
            <ChannelRequirementBadge requiresOwner={false} available />
          </div>

          <div className="settings-channel-row">
            <SettingsToggle
              id="notify-email"
              checked={emailOn}
              onChange={setEmailOn}
              disabled={!emailAvailable && !emailOn}
              label="Email alerts"
              help={
                emailAvailable
                  ? "Also send matching alerts by email when Admin → Mail is configured."
                  : "Email needs the owner to configure Admin → Mail (SMTP or Resend) first."
              }
              testId="notifications-email-toggle"
            />
            <ChannelRequirementBadge requiresOwner available={emailAvailable} />
          </div>

          <div className="settings-channel-row">
            <SettingsToggle
              id="notify-apprise"
              checked={appriseOn}
              onChange={setAppriseOn}
              disabled={!appriseAvailable && !appriseOn}
              label="Apprise alerts"
              help={
                appriseAvailable
                  ? "Send matching alerts to your Apprise destinations (Discord, Telegram, push, and more). Optional household URLs come from the owner under Admin → Mail."
                  : "Apprise package is not installed on this server yet — ask the owner to reinstall with web extras."
              }
              testId="notifications-apprise-toggle"
            />
            <ChannelRequirementBadge
              requiresOwner={false}
              available={appriseAvailable}
              ownerConfigured={Boolean(appriseMeta?.owner_configured)}
            />
          </div>

          <AppriseDestinationsEditor
            rows={appriseRows}
            onChange={setAppriseRows}
            ownerConfigured={Boolean(appriseMeta?.owner_configured)}
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
            help="Opt in to occasional “you have to see this” nudges (inbox + email/Apprise if enabled). Never live session alerts."
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
