import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { generateWeeklyNewsletter, listUsers } from "../../api/client";
import InlineAlert from "../InlineAlert";
import SettingsPanel from "../settings/SettingsPanel";
import {
  NEWSLETTER_SCOPES,
  newsletterConfirmMessage,
  newsletterResultMessage,
} from "../../lib/weeklyNewsletter.js";

/**
 * Owner on-demand weekly newsletter push (self / selected / all opt-ins).
 * Always visible on Ops → Newsletters — never gated on mail/SMTP.
 */
export default function WeeklyNewsletterPanel({
  testIdPrefix = "newsletters",
  mailConfigured = null,
}) {
  const [newsletterScope, setNewsletterScope] = useState("self");
  const [members, setMembers] = useState([]);
  const [selectedIds, setSelectedIds] = useState([]);
  const [sendingNewsletter, setSendingNewsletter] = useState(false);
  const [newsletterStatus, setNewsletterStatus] = useState(null);
  const [membersError, setMembersError] = useState(null);

  useEffect(() => {
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
        setMembersError(null);
      })
      .catch((error) => {
        setMembers([]);
        setMembersError(error?.message || "Could not load household members.");
      });
  }, []);

  function toggleMember(id) {
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
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

  const optedInCount = members.filter((m) => m.optedIn).length;

  return (
    <SettingsPanel
      title="Weekly newsletter"
      lead="Push this week’s personalized newsletter now — same content as the scheduled send. Only opted-in members are included."
      testId={`${testIdPrefix}-newsletter-panel`}
    >
      <p className="settings-field-hint" data-testid={`${testIdPrefix}-newsletter-prereqs`}>
        Members opt in under <Link to="/settings/notifications">Settings → Notifications</Link>
        {members.length > 0 ? (
          <>
            {" "}
            · {optedInCount} of {members.length} loaded members currently opted in
          </>
        ) : null}
        {mailConfigured === false ? (
          <>
            {" "}
            · Email off until <Link to="/admin/mail">Mail</Link> is configured (inbox still works)
          </>
        ) : null}
      </p>

      {membersError ? (
        <InlineAlert
          type="error"
          message={membersError}
          testId={`${testIdPrefix}-newsletter-members-error`}
        />
      ) : null}

      <label className="settings-field">
        <span>Send to</span>
        <select
          value={newsletterScope}
          onChange={(e) => setNewsletterScope(e.target.value)}
          data-testid={`${testIdPrefix}-newsletter-scope`}
        >
          {NEWSLETTER_SCOPES.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </label>
      {newsletterScope === "users" ? (
        <fieldset className="settings-field" data-testid={`${testIdPrefix}-newsletter-members`}>
          <legend>Members</legend>
          {members.length === 0 ? (
            <p className="settings-field-hint">
              {membersError
                ? "Household members unavailable — try again after fixing the error above."
                : "No household members loaded."}
            </p>
          ) : (
            <ul className="settings-checklist">
              {members.map((member) => (
                <li key={member.id}>
                  <label>
                    <input
                      type="checkbox"
                      checked={selectedIds.includes(member.id)}
                      onChange={() => toggleMember(member.id)}
                      data-testid={`${testIdPrefix}-newsletter-member-${member.id}`}
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
          data-testid={`${testIdPrefix}-newsletter-send`}
        >
          {sendingNewsletter ? "Sending…" : "Send weekly newsletter now"}
        </button>
      </div>
      <InlineAlert
        type={newsletterStatus?.type}
        message={newsletterStatus?.message}
        testId={`${testIdPrefix}-newsletter-status`}
        onDismiss={() => setNewsletterStatus(null)}
      />
    </SettingsPanel>
  );
}
