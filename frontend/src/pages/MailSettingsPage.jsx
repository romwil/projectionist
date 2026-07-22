import { useEffect, useState } from "react";
import {
  generateWeeklyNewsletter,
  getSettings,
  listUsers,
  saveSettings,
  testMailSend,
} from "../api/client";
import SettingsPageHeader from "../components/settings/SettingsPageHeader";
import SettingsPanel from "../components/settings/SettingsPanel";
import SettingsToggle from "../components/settings/SettingsToggle";
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

export default function MailSettingsPage() {
  const [mail, setMail] = useState({
    enabled: false,
    provider: "off",
    from_email: "",
    from_name: "CuratorX",
    smtp_host: "",
    smtp_port: 587,
    smtp_username: "",
    smtp_password: "",
    smtp_use_tls: true,
    resend_api_key: "",
    subject_prefix: "[CuratorX]",
    footer_text: "",
    logo_url: "",
    smtp_password_set: false,
    resend_api_key_set: false,
  });
  const [testTo, setTestTo] = useState("");
  const [status, setStatus] = useState(null);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
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
        setReady(true);
      })
      .catch((error) => {
        setStatus({ type: "error", message: error.message || "Could not load settings." });
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

  function toggleMember(id) {
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  }

  async function handleSave(event) {
    event.preventDefault();
    setSaving(true);
    setStatus(null);
    try {
      const current = await getSettings();
      const result = await saveSettings({
        ...current,
        mail: {
          enabled: Boolean(mail.enabled),
          provider: mail.provider || "off",
          from_email: mail.from_email || "",
          from_name: mail.from_name || "CuratorX",
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
      });
      setMail((prev) => ({ ...prev, ...(result.mail || {}), smtp_password: "", resend_api_key: "" }));
      setStatus({ type: "success", message: "Mail settings saved." });
    } catch (error) {
      setStatus({ type: "error", message: error.message || "Could not save." });
    } finally {
      setSaving(false);
    }
  }

  async function handleTest() {
    setTesting(true);
    setStatus(null);
    try {
      const result = await testMailSend({ to_email: testTo.trim() || undefined });
      setStatus({
        type: "success",
        message: `Test sent via ${result.provider} to ${result.to_email}.`,
      });
    } catch (error) {
      setStatus({ type: "error", message: error.message || "Test send failed." });
    } finally {
      setTesting(false);
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
        <SettingsPageHeader title="Mail">Loading…</SettingsPageHeader>
      </div>
    );
  }

  return (
    <div className="settings-stack" data-testid="admin-mail">
      <SettingsPageHeader title="Mail">
        Configure SMTP or Resend so CuratorX can email recommendations, arrivals, and digests.
        Secrets are stored like other settings (owner-only, file mode 0600).
      </SettingsPageHeader>

      <form onSubmit={handleSave}>
        <SettingsPanel title="Transport">
          <SettingsToggle
            id="mail-enabled"
            checked={Boolean(mail.enabled)}
            onChange={(v) => patchMail({ enabled: v })}
            label="Enable outbound mail"
            help="When off, notifications stay in the in-app inbox only."
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
          <label className="settings-field">
            <span>From email</span>
            <input
              type="email"
              value={mail.from_email || ""}
              onChange={(e) => patchMail({ from_email: e.target.value })}
              data-testid="mail-from-email"
            />
          </label>
          <label className="settings-field">
            <span>From name</span>
            <input
              type="text"
              value={mail.from_name || ""}
              onChange={(e) => patchMail({ from_name: e.target.value })}
              data-testid="mail-from-name"
            />
          </label>
        </SettingsPanel>

        {mail.provider === "smtp" ? (
          <SettingsPanel title="SMTP">
            <label className="settings-field">
              <span>Host</span>
              <input
                type="text"
                value={mail.smtp_host || ""}
                onChange={(e) => patchMail({ smtp_host: e.target.value })}
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
              <span>Password{mail.smtp_password_set ? " (saved — leave blank to keep)" : ""}</span>
              <input
                type="password"
                value={mail.smtp_password || ""}
                onChange={(e) => patchMail({ smtp_password: e.target.value })}
                data-testid="mail-smtp-password"
                autoComplete="new-password"
                placeholder={mail.smtp_password_set ? "••••••••" : ""}
              />
            </label>
            <SettingsToggle
              id="mail-smtp-tls"
              checked={mail.smtp_use_tls !== false}
              onChange={(v) => patchMail({ smtp_use_tls: v })}
              label="Use STARTTLS"
              testId="mail-smtp-tls-toggle"
            />
          </SettingsPanel>
        ) : null}

        {mail.provider === "resend" ? (
          <SettingsPanel title="Resend">
            <label className="settings-field">
              <span>API key{mail.resend_api_key_set ? " (saved — leave blank to keep)" : ""}</span>
              <input
                type="password"
                value={mail.resend_api_key || ""}
                onChange={(e) => patchMail({ resend_api_key: e.target.value })}
                data-testid="mail-resend-api-key"
                autoComplete="new-password"
                placeholder={mail.resend_api_key_set ? "••••••••" : "re_…"}
              />
            </label>
          </SettingsPanel>
        ) : null}

        <SettingsPanel title="Template">
          <label className="settings-field">
            <span>Subject prefix</span>
            <input
              type="text"
              value={mail.subject_prefix || ""}
              onChange={(e) => patchMail({ subject_prefix: e.target.value })}
              data-testid="mail-subject-prefix"
            />
          </label>
          <label className="settings-field">
            <span>Footer text</span>
            <textarea
              rows={3}
              value={mail.footer_text || ""}
              onChange={(e) => patchMail({ footer_text: e.target.value })}
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
        </SettingsPanel>

        <SettingsPanel title="Test send">
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
          <button
            type="button"
            className="ghost"
            onClick={handleTest}
            disabled={testing}
            data-testid="mail-test-send"
          >
            {testing ? "Sending…" : "Send test email"}
          </button>
        </SettingsPanel>

        {status ? (
          <p
            className={`status ${status.type === "error" ? "status-error" : "status-success"}`}
            data-testid="mail-status"
          >
            {status.message}
          </p>
        ) : null}

        <div className="settings-actions">
          <button type="submit" className="primary" disabled={saving} data-testid="mail-save">
            {saving ? "Saving…" : "Save mail settings"}
          </button>
        </div>
      </form>

      <SettingsPanel title="Weekly newsletter">
        <p className="settings-field-hint">
          Push this week’s personalized newsletter now — same content as the scheduled send.
          Only people who opted in under Settings → Notifications are included; inbox and email
          channel prefs still apply.
        </p>
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
        <button
          type="button"
          className="primary"
          onClick={handleSendNewsletter}
          disabled={sendingNewsletter}
          data-testid="mail-newsletter-send"
        >
          {sendingNewsletter ? "Sending…" : "Send weekly newsletter now"}
        </button>
        {newsletterStatus ? (
          <p
            className={`status ${newsletterStatus.type === "error" ? "status-error" : "status-success"}`}
            data-testid="mail-newsletter-status"
          >
            {newsletterStatus.message}
          </p>
        ) : null}
      </SettingsPanel>
    </div>
  );
}
