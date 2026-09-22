import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { cancelYearInReview, generateYearInReview, getYearInReviewStatus } from "../../api/client";
import { yirPathFromGenerateResult } from "../../lib/yearInReview";
import AdminExecutionCard from "../AdminExecutionCard";
import InlineAlert from "../InlineAlert";
import SettingsPanel from "../settings/SettingsPanel";
import SettingsToggle from "../settings/SettingsToggle";

/**
 * Owner self-generate / send-test for Year in Review.
 * Always visible on Ops → Newsletters — never gated on mail/SMTP or calendar window.
 */
export default function YearInReviewAdminPanel({
  testIdPrefix = "newsletters",
  mailConfigured = null,
}) {
  const [sendingYir, setSendingYir] = useState(false);
  const [yirNotify, setYirNotify] = useState(true);
  const [yirStatus, setYirStatus] = useState(null);
  const [yirPath, setYirPath] = useState(null);
  const [yirJob, setYirJob] = useState(null);

  useEffect(() => {
    let cancelled = false;
    async function poll() {
      try {
        const snap = await getYearInReviewStatus();
        if (cancelled) return;
        setYirJob(snap);
        setSendingYir(Boolean(snap?.busy));
        const result = snap?.result;
        if (!snap?.busy && result) {
          const path = yirPathFromGenerateResult(result);
          if (path) setYirPath(path);
          const year = result.year;
          const delivered = Number(result.delivered) || 0;
          if (result.status === "empty" || (!path && Number(result.skipped_empty) > 0)) {
            setYirStatus({
              type: "error",
              message: year
                ? `Not enough tracked finishes for ${year} yet (year to date). Keep watching, then try again.`
                : "Not enough tracked finishes for this year yet.",
            });
          } else if (path) {
            setYirStatus({
              type: "success",
              message: `Ready for ${year}. Delivered to ${delivered} inbox${delivered === 1 ? "" : "es"}.`,
            });
          }
        }
      } catch {
        /* keep last snapshot */
      }
    }
    poll();
    const interval = setInterval(poll, 2000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  async function handleGenerateYir() {
    if (
      !window.confirm(
        yirNotify
          ? "Generate your Year in Review reel now and notify your inbox (and email if enabled)?"
          : "Generate your Year in Review reel now without sending a notification?",
      )
    ) {
      return;
    }
    setSendingYir(true);
    setYirStatus(null);
    setYirPath(null);
    try {
      const snap = await generateYearInReview({ scope: "self", notify: Boolean(yirNotify) });
      setYirJob(snap);
    } catch (error) {
      setYirStatus({
        type: "error",
        message: error.message || "Could not generate Year in Review.",
      });
      setSendingYir(false);
    }
  }

  return (
    <SettingsPanel
      title="Year in Review"
      lead="Generate your own year-to-date cinema reel for a quick test (send-test). Scheduled tease/drop tasks still run for opted-in members."
      testId={`${testIdPrefix}-yir-panel`}
    >
      <p className="settings-field-hint" data-testid={`${testIdPrefix}-yir-prereqs`}>
        Test generate uses the current calendar year (year to date). Requires a mapped Plex
        identity and enough tracked finishes for this year
        {mailConfigured === false ? (
          <>
            {" "}
            · Email off until <Link to="/admin/mail">Mail</Link> is configured (inbox still works)
          </>
        ) : null}
        . With notify on, you’ll get the same Inbox item as a normal Year in Review delivery.
      </p>
      <SettingsToggle
        id={`${testIdPrefix}-yir-notify`}
        checked={yirNotify}
        onChange={setYirNotify}
        label="Notify my inbox when ready"
        help="Creates the same inbox notification as scheduled delivery (with a durable link). Turn off to build the reel without notifying."
        testId={`${testIdPrefix}-yir-notify-toggle`}
      />
      <div className="settings-actions">
        <button
          type="button"
          className="primary"
          onClick={handleGenerateYir}
          disabled={sendingYir || Boolean(yirJob?.busy)}
          data-testid={`${testIdPrefix}-yir-self-generate`}
        >
          {yirJob?.busy ? "Generating…" : "Generate my Year in Review"}
        </button>
      </div>
      <AdminExecutionCard
        job={yirJob}
        testId={`${testIdPrefix}-yir-progress`}
        phaseLabels={{ generating: "Generating reel", done: "Reel ready" }}
        onCancel={async () => {
          try {
            setYirJob(await cancelYearInReview());
          } catch (error) {
            setYirStatus({ type: "error", message: error.message || "Could not cancel." });
          }
        }}
      />
      <InlineAlert
        type={yirStatus?.type}
        message={yirStatus?.message}
        testId={`${testIdPrefix}-yir-status`}
        onDismiss={() => {
          setYirStatus(null);
          setYirPath(null);
        }}
      />
      {yirPath && yirStatus?.type === "success" ? (
        <p className="settings-field-hint" data-testid={`${testIdPrefix}-yir-link`}>
          <Link to={yirPath}>Open Year in Review</Link>
          {yirNotify ? (
            <>
              {" "}
              · or reopen from <Link to="/inbox">Inbox</Link>
            </>
          ) : null}
        </p>
      ) : null}
    </SettingsPanel>
  );
}
