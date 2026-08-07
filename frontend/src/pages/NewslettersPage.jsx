import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getFeatures } from "../api/client";
import WeeklyNewsletterPanel from "../components/admin/WeeklyNewsletterPanel";
import YearInReviewAdminPanel from "../components/admin/YearInReviewAdminPanel";
import SettingsPageHeader from "../components/settings/SettingsPageHeader";

/**
 * Ops → Newsletters: weekly member newsletter push + Year in Review send-test.
 * Always renders both panels for owners (same AdminLayout gate as Mail) —
 * including on iPad / mobile Safari widths. No sticky chrome on this page.
 * Transport (SMTP/Resend/Apprise) stays on Admin → Mail — never silently omit
 * these sections when mail is off; show an honest inbox-only note instead.
 *
 * Path: Admin → Ops → Newsletters (`/admin/newsletters`).
 */
export default function NewslettersPage() {
  const [mailConfigured, setMailConfigured] = useState(null);

  useEffect(() => {
    getFeatures()
      .then((features) => {
        setMailConfigured(Boolean(features?.notifications?.mail_configured));
      })
      .catch(() => setMailConfigured(null));
  }, []);

  // Always mount both panels. mailConfigured only drives honest hint copy.
  return (
    <div className="settings-stack" data-testid="admin-newsletters">
      <SettingsPageHeader title="Newsletters">
        Push the weekly member newsletter and generate a Year in Review test reel. Outbound email
        transport is configured under <Link to="/admin/mail">Mail</Link>. Member opt-in lives under{" "}
        <Link to="/settings/notifications">Settings → Notifications</Link>.
      </SettingsPageHeader>

      {mailConfigured === false ? (
        <p className="settings-field-hint" data-testid="newsletters-mail-not-configured">
          Outbound email is not configured yet. Newsletter and Year in Review can still deliver to
          the in-app inbox; email will send once you enable SMTP or Resend under{" "}
          <Link to="/admin/mail">Mail</Link>.
        </p>
      ) : null}

      <WeeklyNewsletterPanel mailConfigured={mailConfigured} />
      <YearInReviewAdminPanel testIdPrefix="newsletters" mailConfigured={mailConfigured} />
    </div>
  );
}
