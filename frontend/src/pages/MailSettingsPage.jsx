import { useEffect, useState } from "react";
import {
  generateWeeklyNewsletter,
  getSettings,
  listUsers,
  saveSettings,
  testAppriseSend,
  testMailSend,
} from "../api/client";
import InlineAlert from "../components/InlineAlert";
import SettingsPageHeader from "../components/settings/SettingsPageHeader";
import SettingsPanel from "../components/settings/SettingsPanel";
import SettingsToggle from "../components/settings/SettingsToggle";
import {
  appriseTestResultMessage,
  appriseUrlsLabel,
  mailTestResultMessage,
  savedSecretLabel,
} from "../lib/mailSettingsUi.js";
import {
  NEWSLETTER_SCOPES,
  newsletterConfirmMessage,
  newsletterResultMessage,
} from "../lib/weeklyNewsletter.js";

const PROVIDERS = [
  { value: "off", label: "Off" },
  { value: "smtp", label: "SMTP" },
  { value: "resend", label: "Resend" },
];

const EMPTY_APPRISE = {
  enabled: false,
  urls: "",
  config: "",
  tag: "",
  urls_set: false,
  url_count: 0,
  config_set: false,
  configured: false,
  package_available: true,
};

export default function MailSettingsPage() {
  const [mail, setMail] = useState({
    enabled: false,
    provider: "off",
    from_email: "",
    from_name: "Projectionist",
    smtp_host: "",
    smtp_port: 587,
    smtp_username: "",
    smtp_password: "",
    smtp_use_tls: true,
    resend_api_key: "",
    subject_prefix: "[Projectionist]",
    footer_text: "",
    logo_url: "",
    smtp_password_set: false,
    resend_api_key_set: false,
  });
  const [apprise, setApprise] = useState(EMPTY_APPRISE);
  const [testTo, setTestTo] = useState("");
  const [appriseTestUrls, setAppriseTestUrls] = useState("");
  const [saveStatus, setSaveStatus] = useState(null);
  const [mailTestStatus, setMailTestStatus] = useState(null);
  const [appriseTestStatus, setAppriseTestStatus] = useState(null);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testingApprise, setTestingApprise] = useState(false);
  const [ready, setReady] = useState(false);
  const [newsletterScope, setNewsletterScope] = useState("self");
  const [members, setMembers] = useState([]);
  const [selectedIds, setSelectedIds] = useState([]);
  const [sendingNewsletter, setSendingNewsletter] = useState(false);
  const [newsletterStatus, setNewsletterStatus] = useState(null);

  useEffect(() => {
    getSettings()
      .then((data) => {
        setMail((prev) => ({ ...prev, ...(data.mail || {}) }));
        setApprise((prev) => ({ ...prev, ...(data.apprise || {}) }));
        setReady(true);
      })
      .catch((error) => {
        setSaveStatus({ type: "error", message: error.message || "Could not load settings." });
        setReady(true);
      });
    listUsers()
      .then((data) => {
        const items = Array.isArray(data?.items) ? data.items : Array.isArray(data) ? data : [];
        setMembers(
          items.filter((u) => u && !u.disabled).map((u) => ({
            id: String(u.id),
            label: u.preferred_name || u.display_name || u.email || String(u.id),
            optedIn: Boolean(u.newsletter_opt_in),
          })),
        );
      })
      .catch(() => setMembers([]));
  }, []);

  function patchMail(patch) {
    setMail((prev) => ({ ...prev, ...patch }));
  }

  function patchApprise(patch) {
    setApprise((prev) => ({ ...prev, ...patch }));
  }

  function toggleMember(id) {
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  }

  async function handleSave(event) {
    event.preventDefault();
    setSaving(true);
    setSaveStatus(null);
    try {
      const current = await getSettings();
      const result = await saveSettings({
        ...current,
        mail: {
          enabled: Boolean(mail.enabled),
          provider: mail.provider || "off",
          from_email: mail.from_email || "",
          from_name: mail.from_name || "Projectionist",
          smtp_host: mail.smtp_host || "",
          smtp_port: Number(mail.smtp_port) || 587,
          smtp_username: mail.smtp_username || "",
          smtp_password: mail.smtp_password || "",
          smtp_use_tls: mail.smtp_use_tls !== false,
          resend_api_key: mail.resend_api_key || "",
          subject_prefix: mail.subject_prefix || "",
          footer_text: mail.footer_text || "",
          logo_url: mail.logo_url || "",
        },
        apprise: {
          enabled: Boolean(apprise.enabled),
          urls: apprise.urls || "",
          config: apprise.config || "",
          tag: apprise.tag || "",
        },
      });
      setMail((prev) => ({ ...prev, ...(result.mail || {}), smtp_password: "", resend_api_key: "" }));
      setApprise((prev) => ({ ...prev, ...(result.apprise || {}), urls: "", config: "" }));
      setSaveStatus({ type: "success", message: "Mail & Apprise settings saved." });
    } catch (error) {
      setSaveStatus({ type: "error", message: error.message || "Could not save." });
    } finally {
      setSaving(false);
    }
  }

  async function handleTest() {
    setTesting(true);
    setMailTestStatus(null);
    try {
      const result = await testMailSend(testTo.trim() ? { to_email: testTo.trim() } : {});
      setMailTestStatus({ type: "success", message: mailTestResultMessage(result) });
    } catch (error) {
      setMailTestStatus({ type: "error", message: error.message || "Test send failed." });
    } finally {
      setTesting(false);
    }
  }

  async function handleAppriseTest() {
    setTestingApprise(true);
    setAppriseTestStatus(null);
    try {
      const result = await testAppriseSend(
        appriseTestUrls.trim() ? { urls: appriseTestUrls.trim() } : {},
      );
      setAppriseTestStatus({ type: "success", message: appriseTestResultMessage(result) });
    } catch (error) {
      setAppriseTestStatus({ type: "error", message: error.message || "Apprise test failed." });
    } finally {
      setTestingApprise(false);
    }
  }

  async function handleSendNewsletter() {
    if (newsletterScope === "users" && selectedIds.length === 0) {
      setNewsletterStatus({ type: "error", message: "Select at least one member." });
      return;
    }
    const confirmed = window.confirm(
      newsletterConfirmMessage(newsletterScope, selectedIds.length),
    );
    if (!confirmed) return;
    setSendingNewsletter(true);
    setNewsletterStatus(null);
    try {
      const payload =
        newsletterScope === "users"
          ? { scope: "users", user_ids: selectedIds }
          : { scope: newsletterScope };
      const result = await generateWeeklyNewsletter(payload);
      setNewsletterStatus({ type: "success", message: newsletterResultMessage(result) });
    } catch (error) {
      setNewsletterStatus({
        type: "error",
        message: error.message || "Could not send the weekly newsletter.",
      });
    } finally {
      setSendingNewsletter(false);
    }
  }

  if (!ready) {
    return (
      <div className="settings-stack" data-testid="admin-mail">
        <SettingsPageHeader title="Mail & alerts">Loading…</SettingsPageHeader>
      </div>
    );
  }

  const mailTransportOpen = Boolean(mail.enabled) || (mail.provider && mail.provider !== "off");

  return (
    <div className="settings-stack" data-testid="admin-mail">
      <SettingsPageHeader title="Mail & alerts">
        Household email and installation Apprise. Members choose channels under Settings →
        Notifications.
      </SettingsPageHeader>

      <form onSubmit={handleSave} className="mail-settings-form">
        <SettingsPanel
          title="Outbound email"
          lead="SMTP or Resend for digests and alerts. When off, notifications stay in the in-app inbox."
          testId="mail-transport-panel"
        >
          <SettingsToggle
            id="mail-enabled"
            checked={Boolean(mail.enabled)}
            onChange={(v) => patchMail({ enabled: v })}
            label="Enable outbound mail"
            help="Turn on to deliver email when members opt in."
            testId="mail-enabled-toggle"
          />
          <label className="settings-field">
            <span>Provider</span>
            <select
              value={mail.provider || "off"}
              onChange={(e) => patchMail({ provider: e.target.value })}
              data-testid="mail-provider-select"
            >
              {PROVIDERS.map((p) => (
                <option key={p.value} value={p.value}>
                  {p.label}
                </option>
              ))}
            </select>
          </label>

          {mailTransportOpen ? (
            <div className="settings-field-grid">
              <label className="settings-field">
                <span>From email</span>
                <input
                  type="email"
                  value={mail.from_email || ""}
                  onChange={(e) => patchMail({ from_email: e.target.value })}
                  placeholder="alerts@example.com"
                  data-testid="mail-from-email"
                />
              </label>
              <label className="settings-field">
                <span>From name</span>
                <input
                  type="text"
                  value={mail.from_name || ""}
                  onChange={(e) => patchMail({ from_name: e.target.value })}
                  placeholder="Projectionist"
                  data-testid="mail-from-name"
                />
              </label>
            </div>
          ) : null}

          {mail.provider === "smtp" ? (
            <div className="settings-subsection" data-testid="mail-smtp-section">
              <h4 className="settings-subsection-title">SMTP</h4>
              <div className="settings-field-grid">
                <label className="settings-field">
                  <span>Host</span>
                  <input
                    type="text"
                    value={mail.smtp_host || ""}
                    onChange={(e) => patchMail({ smtp_host: e.target.value })}
                    placeholder="smtp.example.com"
                    data-testid="mail-smtp-host"
                  />
                </label>
                <label className="settings-field">
                  <span>Port</span>
                  <input
                    type="number"
                    value={mail.smtp_port ?? 587}
                    onChange={(e) => patchMail({ smtp_port: Number(e.target.value) || 587 })}
                    data-testid="mail-smtp-port"
                  />
                </label>
                <label className="settings-field">
                  <span>Username</span>
                  <input
                    type="text"
                    value={mail.smtp_username || ""}
                    onChange={(e) => patchMail({ smtp_username: e.target.value })}
                    data-testid="mail-smtp-username"
                    autoComplete="off"
                  />
                </label>
                <label className="settings-field">
                  <span>{savedSecretLabel("Password", Boolean(mail.smtp_password_set))}</span>
                  <input
                    type="password"
                    value={mail.smtp_password || ""}
                    onChange={(e) => patchMail({ smtp_password: e.target.value })}
                    data-testid="mail-smtp-password"
                    autoComplete="new-password"
                    placeholder={mail.smtp_password_set ? "••••••••" : ""}
                  />
                </label>
              </div>
              <SettingsToggle
                id="mail-smtp-tls"
                checked={mail.smtp_use_tls !== false}
                onChange={(v) => patchMail({ smtp_use_tls: v })}
                label="Use STARTTLS"
                testId="mail-smtp-tls-toggle"
              />
            </div>
          ) : null}

          {mail.provider === "resend" ? (
            <div className="settings-subsection" data-testid="mail-resend-section">
              <h4 className="settings-subsection-title">Resend</h4>
              <label className="settings-field">
                <span>{savedSecretLabel("API key", Boolean(mail.resend_api_key_set))}</span>
                <input
                  type="password"
                  value={mail.resend_api_key || ""}
                  onChange={(e) => patchMail({ resend_api_key: e.target.value })}
                  data-testid="mail-resend-api-key"
                  autoComplete="new-password"
                  placeholder={mail.resend_api_key_set ? "••••••••" : "re_…"}
                />
              </label>
            </div>
          ) : null}

          <details className="settings-advanced">
            <summary>Email template</summary>
            <div className="settings-advanced-body">
              <label className="settings-field">
                <span>Subject prefix</span>
                <input
                  type="text"
                  value={mail.subject_prefix || ""}
                  onChange={(e) => patchMail({ subject_prefix: e.target.value })}
                  placeholder="[Projectionist]"
                  data-testid="mail-subject-prefix"
                />
              </label>
              <label className="settings-field">
                <span>Footer text</span>
                <textarea
                  rows={3}
                  value={mail.footer_text || ""}
                  onChange={(e) => patchMail({ footer_text: e.target.value })}
                  placeholder="Optional sign-off shown at the bottom of emails"
                  data-testid="mail-footer-text"
                />
              </label>
              <label className="settings-field">
                <span>Logo URL</span>
                <input
                  type="url"
                  value={mail.logo_url || ""}
                  onChange={(e) => patchMail({ logo_url: e.target.value })}
                  data-testid="mail-logo-url"
                  placeholder="https://…"
                />
              </label>
            </div>
          </details>

          <div className="settings-subsection" data-testid="mail-test-section">
            <h4 className="settings-subsection-title">Send a test</h4>
            <label className="settings-field">
              <span>Send test to</span>
              <input
                type="email"
                value={testTo}
                onChange={(e) => setTestTo(e.target.value)}
                placeholder="Defaults to your notification email"
                data-testid="mail-test-to"
              />
            </label>
            <div className="settings-actions">
              <button
                type="button"
                className="ghost"
                onClick={handleTest}
                disabled={testing}
                data-testid="mail-test-send"
              >
                {testing ? "Sending…" : "Send test email"}
              </button>
            </div>
            <InlineAlert
              type={mailTestStatus?.type}
              message={mailTestStatus?.message}
              testId="mail-test-status"
              onDismiss={() => setMailTestStatus(null)}
            />
          </div>
        </SettingsPanel>

        <SettingsPanel
          title="Apprise (installation)"
          lead="Optional household destinations for members who enable Apprise. Personal URLs stay self-serve."
          testId="mail-apprise-panel"
        >
          <p className="settings-panel-meta">
            <span className="settings-channel-badge is-owner-required">Owner / server setup</span>
          </p>
          {!apprise.package_available ? (
            <InlineAlert
              type="error"
              message='The Apprise package is not installed on this server. Reinstall with the web extras (pip install ".[web]") and restart.'
              testId="apprise-package-missing"
            />
          ) : null}
          <SettingsToggle
            id="apprise-enabled"
            checked={Boolean(apprise.enabled)}
            onChange={(v) => patchApprise({ enabled: v })}
            label="Enable installation Apprise URLs"
            help="When on, opted-in members also get alerts on these household destinations."
            testId="apprise-enabled-toggle"
          />
          <label className="settings-field">
            <span>{appriseUrlsLabel(apprise)}</span>
            <textarea
              rows={4}
              value={apprise.urls || ""}
              onChange={(e) => patchApprise({ urls: e.target.value })}
              placeholder={"discord://…\ntgram://…"}
              data-testid="apprise-urls"
              spellCheck={false}
              className="settings-code-input"
            />
            <span className="settings-field-hint">One URL per line. Leave blank on save to keep stored URLs.</span>
            <details className="settings-learn-more">
              <summary>Learn more</summary>
              <p>
                See{" "}
                <a
                  href="https://github.com/caronc/apprise#supported-notifications"
                  target="_blank"
                  rel="noreferrer"
                >
                  Apprise notification types
                </a>{" "}
                for Discord, Telegram, and other schemes.
              </p>
            </details>
          </label>

          <details className="settings-advanced">
            <summary>Advanced config</summary>
            <div className="settings-advanced-body">
              <label className="settings-field">
                <span>{savedSecretLabel("Apprise config (YAML/JSON)", Boolean(apprise.config_set))}</span>
                <textarea
                  rows={5}
                  value={apprise.config || ""}
                  onChange={(e) => patchApprise({ config: e.target.value })}
                  placeholder={"urls:\n  - json://hostname/path"}
                  data-testid="apprise-config"
                  spellCheck={false}
                  className="settings-code-input"
                />
              </label>
              <label className="settings-field">
                <span>Tag filter</span>
                <input
                  type="text"
                  value={apprise.tag || ""}
                  onChange={(e) => patchApprise({ tag: e.target.value })}
                  placeholder="Optional — blank means all tags"
                  data-testid="apprise-tag"
                />
              </label>
            </div>
          </details>

          <div className="settings-subsection" data-testid="apprise-test-section">
            <h4 className="settings-subsection-title">Send a test</h4>
            <details className="settings-advanced settings-advanced-nested">
              <summary>Override URLs for this test</summary>
              <div className="settings-advanced-body">
                <label className="settings-field">
                  <span>Test URLs</span>
                  <textarea
                    rows={2}
                    value={appriseTestUrls}
                    onChange={(e) => setAppriseTestUrls(e.target.value)}
                    placeholder="Leave blank to use saved installation URLs/config"
                    data-testid="apprise-test-urls"
                    spellCheck={false}
                    className="settings-code-input"
                  />
                </label>
              </div>
            </details>
            <div className="settings-actions">
              <button
                type="button"
                className="ghost"
                onClick={handleAppriseTest}
                disabled={testingApprise}
                data-testid="apprise-test-send"
              >
                {testingApprise ? "Sending…" : "Send Apprise test"}
              </button>
            </div>
            <InlineAlert
              type={appriseTestStatus?.type}
              message={appriseTestStatus?.message}
              testId="apprise-test-status"
              onDismiss={() => setAppriseTestStatus(null)}
            />
          </div>
        </SettingsPanel>

        <div className="mail-settings-save-bar">
          <InlineAlert
            type={saveStatus?.type}
            message={saveStatus?.message}
            testId="mail-status"
            onDismiss={() => setSaveStatus(null)}
          />
          <div className="settings-actions">
            <button type="submit" className="primary" disabled={saving} data-testid="mail-save">
              {saving ? "Saving…" : "Save"}
            </button>
            <span className="settings-field-hint">Saves outbound email and installation Apprise together.</span>
          </div>
        </div>
      </form>

      <SettingsPanel
        title="Weekly newsletter"
        lead="Push this week’s personalized newsletter now — same content as the scheduled send. Only opted-in members are included."
        testId="mail-newsletter-panel"
      >
        <label className="settings-field">
          <span>Send to</span>
          <select
            value={newsletterScope}
            onChange={(e) => setNewsletterScope(e.target.value)}
            data-testid="mail-newsletter-scope"
          >
            {NEWSLETTER_SCOPES.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </label>
        {newsletterScope === "users" ? (
          <fieldset className="settings-field" data-testid="mail-newsletter-members">
            <legend>Members</legend>
            {members.length === 0 ? (
              <p className="settings-field-hint">No household members loaded.</p>
            ) : (
              <ul className="settings-checklist">
                {members.map((member) => (
                  <li key={member.id}>
                    <label>
                      <input
                        type="checkbox"
                        checked={selectedIds.includes(member.id)}
                        onChange={() => toggleMember(member.id)}
                        data-testid={`mail-newsletter-member-${member.id}`}
                      />
                      <span>
                        {member.label}
                        {member.optedIn ? "" : " (not opted in)"}
                      </span>
                    </label>
                  </li>
                ))}
              </ul>
            )}
          </fieldset>
        ) : null}
        <div className="settings-actions">
          <button
            type="button"
            className="primary"
            onClick={handleSendNewsletter}
            disabled={sendingNewsletter}
            data-testid="mail-newsletter-send"
          >
            {sendingNewsletter ? "Sending…" : "Send weekly newsletter now"}
          </button>
        </div>
        <InlineAlert
          type={newsletterStatus?.type}
          message={newsletterStatus?.message}
          testId="mail-newsletter-status"
          onDismiss={() => setNewsletterStatus(null)}
        />
      </SettingsPanel>
    </div>
  );
}
