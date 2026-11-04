import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import {
  completeMondayPass,
  getOwnerOpsOverview,
  runMondayCatchUp,
  setOwnerChecklistMark,
} from "../api/client";
import {
  checklistProgress,
  formatLastProbe,
  secretStateCopy,
  summarizeNeedsAttention,
} from "../lib/ownerOps.js";
import { taskDisplayName } from "../lib/scheduledTasks.js";
import HouseholdPulseCard from "./HouseholdPulseCard";
import "./OwnerOpsOverview.css";
import Button from "./Button";

type OwnerOpsOverviewProps = {
  onOpenWizard?: () => void;
  /** Rendered between Needs attention and the Monday pass (the at-a-glance tiles). */
  children?: ReactNode;
};

function formatWhen(epochSeconds: unknown) {
  const n = Number(epochSeconds);
  if (!Number.isFinite(n) || n <= 0) return "";
  return new Date(n * 1000).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

const STEP_STATUS_COPY: Record<string, string> = {
  done: "Done",
  reviewed: "Reviewed",
  pending: "To do",
};

/**
 * Admin Overview stewardship surface. One Needs attention list rolls up
 * secrets, failed tasks, setup gaps, and this week's Monday pass.
 * State lives on the server (SQLite), so it survives reloads and devices.
 */
export default function OwnerOpsOverview({ onOpenWizard, children }: OwnerOpsOverviewProps) {
  const [data, setData] = useState<any | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    try {
      setData(await getOwnerOpsOverview());
      setError("");
    } catch (err) {
      setError((err as { message?: string })?.message || "Couldn't load the Monday pass.");
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    getOwnerOpsOverview()
      .then((next) => {
        if (cancelled) return;
        setData(next);
        setError("");
      })
      .catch((err) => {
        if (!cancelled) setError((err as { message?: string })?.message || "Couldn't load the Monday pass.");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const { hash } = useLocation();
  const loaded = Boolean(data);
  useEffect(() => {
    const id = hash.replace(/^#/, "");
    if (!loaded || !id) return;
    document.getElementById(id)?.scrollIntoView({ block: "start" });
  }, [hash, loaded]);

  async function act(key: string, fn: () => Promise<unknown>, message = "") {
    if (busy) return;
    setBusy(key);
    setNotice("");
    try {
      await fn();
      if (message) setNotice(message);
      await load();
    } catch (err) {
      setNotice((err as { message?: string })?.message || "That didn't work. Try again.");
    } finally {
      setBusy("");
    }
  }

  const attention = summarizeNeedsAttention(data?.needs_attention);
  const monday = data?.monday;
  const setup = data?.setup;
  const secrets = data?.secrets;
  const activity = data?.activity_7d;
  const progress = checklistProgress(setup?.items);

  return (
    <>
      <section
        className={`config-section owner-ops-attention tone-${attention.tone}`}
        data-testid="owner-needs-attention"
        aria-labelledby="owner-needs-attention-title"
      >
        <h2 id="owner-needs-attention-title">{data ? attention.headline : "Needs attention"}</h2>
        {error ? (
          <p className="wizard-note" role="status" data-testid="owner-ops-error">
            {error}
          </p>
        ) : !data ? (
          <p className="wizard-note">Checking the household…</p>
        ) : attention.count ? (
          <ul className="owner-ops-list" data-testid="owner-needs-attention-list">
            {attention.items.map((item: any) => (
              <li key={item.id} className={`owner-ops-row severity-${item.severity}`} data-testid={`needs-attention-${item.id}`}>
                <div className="owner-ops-row-text">
                  <span className="owner-ops-row-title">{item.title}</span>
                  <span className="owner-ops-row-detail">{item.detail}</span>
                </div>
                <Link className="btn-link" to={item.to}>
                  Open
                </Link>
              </li>
            ))}
          </ul>
        ) : (
          <p className="wizard-note">Keys read, tasks ran, and this week&apos;s pass is done.</p>
        )}
      </section>

      {children}

      <HouseholdPulseCard />

      {monday ? (
        <section className="config-section owner-ops-monday" id="monday-pass" data-testid="monday-pass-checklist">
          <div className="owner-ops-head">
            <div>
              <h2>Monday pass</h2>
              <p className="wizard-note">
                About 20 minutes, in this order. Steps tick themselves when the number is healthy;
                otherwise mark them reviewed.
              </p>
            </div>
            <p className="owner-ops-stamp" data-testid="monday-pass-stamp">
              {monday.completed_at
                ? `Done this week · ${formatWhen(monday.completed_at)}`
                : monday.last_completed_at
                  ? `Last done ${formatWhen(monday.last_completed_at)}`
                  : "Not done yet"}
            </p>
          </div>
          <ol className="owner-ops-list owner-ops-steps">
            {(monday.steps || []).map((step: any) => {
              const done = step.status !== "pending";
              return (
                <li key={step.id} className={`owner-ops-row status-${step.status}`} data-testid={`monday-step-${step.id}`}>
                  <span className="material-symbols-outlined owner-ops-check" aria-hidden="true">
                    {done ? "check_circle" : "radio_button_unchecked"}
                  </span>
                  <div className="owner-ops-row-text">
                    <span className="owner-ops-row-title">
                      <Link to={step.to}>{step.label}</Link>
                      {step.metric ? <span className="owner-ops-metric">{step.metric}</span> : null}
                    </span>
                    <span className="owner-ops-row-detail">{step.detail}</span>
                  </div>
                  <span className="owner-ops-chip" data-testid={`monday-step-status-${step.id}`}>
                    {STEP_STATUS_COPY[step.status] || step.status}
                  </span>
                  <div className="owner-ops-row-actions">
                    {step.id === "catchup" && step.status === "pending" ? (
                      <Button
                        variant="secondary"
                        size="sm"
                        data-testid="monday-catchup-run"
                        disabled={Boolean(busy)}
                        onClick={() =>
                          act(
                            "catchup",
                            async () => {
                              const result: any = await runMondayCatchUp();
                              const names = (result?.queued || []).map(taskDisplayName).join(", ");
                              setNotice(names ? `Queued: ${names}` : "");
                            },
                          )
                        }
                      >
                        {busy === "catchup" ? "Queueing…" : "Run catch-up"}
                      </Button>
                    ) : null}
                    {step.status === "pending" ? (
                      <Button
                        variant="secondary"
                        size="sm"
                        data-testid={`monday-step-review-${step.id}`}
                        disabled={Boolean(busy)}
                        onClick={() => act(step.id, () => setOwnerChecklistMark("monday", step.id, "reviewed"))}
                      >
                        Mark reviewed
                      </Button>
                    ) : step.status === "reviewed" || (step.status === "done" && step.marked_at) ? (
                      <Button
                        variant="secondary"
                        size="sm"
                        data-testid={`monday-step-undo-${step.id}`}
                        disabled={Boolean(busy)}
                        onClick={() => act(step.id, () => setOwnerChecklistMark("monday", step.id, "pending"))}
                      >
                        Undo
                      </Button>
                    ) : null}
                  </div>
                </li>
              );
            })}
          </ol>
          <div className="config-actions">
            <Button
              variant="primary"
              data-testid="monday-pass-complete"
              disabled={Boolean(busy) || !monday.ready || Boolean(monday.completed_at)}
              onClick={() => act("complete", () => completeMondayPass(), "Monday pass done. See you next week.")}
            >
              {monday.completed_at ? "Pass done" : "Mark pass done"}
            </Button>
          </div>
          {notice ? (
            <p className="wizard-note" role="status" data-testid="owner-ops-notice">
              {notice}
            </p>
          ) : null}
          {activity ? (
            <p className="wizard-note owner-ops-activity" data-testid="owner-ops-activity">
              On this server, last 7 days: {Number(activity.chat_turns) || 0} chat turns ·{" "}
              {Number(activity.plays) || 0} plays in Projectionist · {Number(activity.plays_from_picks) || 0} from a
              pick. Counted here; nothing leaves your server.
            </p>
          ) : null}
        </section>
      ) : null}

      {setup ? (
        <section className="config-section owner-ops-setup" id="setup-checklist" data-testid="stewardship-checklist">
          <div className="owner-ops-head">
            <div>
              <h2>Setup &amp; stewardship</h2>
              <p className="wizard-note">
                Do these in any order. Rows tick when the server can see the work is done. Skip what
                your household doesn&apos;t need; you can bring a row back anytime.
              </p>
            </div>
            <p className="owner-ops-stamp" data-testid="stewardship-progress">
              {progress.done} of {progress.total} done
              {progress.skipped ? ` · ${progress.skipped} skipped` : ""}
            </p>
          </div>
          <ul className="owner-ops-list">
            {(setup.items || []).map((item: any) => (
              <li key={item.id} className={`owner-ops-row status-${item.status}`} data-testid={`setup-item-${item.id}`}>
                <span className="material-symbols-outlined owner-ops-check" aria-hidden="true">
                  {item.status === "done" ? "check_circle" : item.status === "skipped" ? "do_not_disturb_on" : "radio_button_unchecked"}
                </span>
                <div className="owner-ops-row-text">
                  <span className="owner-ops-row-title">
                    <Link to={item.to}>{item.label}</Link>
                    {item.optional ? <span className="owner-ops-optional">Optional</span> : null}
                  </span>
                  <span className="owner-ops-row-detail">{item.detail}</span>
                </div>
                <span className="owner-ops-chip">
                  {item.status === "done" ? "Done" : item.status === "skipped" ? "Skipped" : "To do"}
                </span>
                <div className="owner-ops-row-actions">
                  {item.status === "pending" ? (
                    <Button
                      variant="secondary"
                      size="sm"
                      data-testid={`setup-item-skip-${item.id}`}
                      disabled={Boolean(busy)}
                      onClick={() => act(item.id, () => setOwnerChecklistMark("setup", item.id, "skipped"))}
                    >
                      Skip
                    </Button>
                  ) : item.status === "skipped" ? (
                    <Button
                      variant="secondary"
                      size="sm"
                      data-testid={`setup-item-restore-${item.id}`}
                      disabled={Boolean(busy)}
                      onClick={() => act(item.id, () => setOwnerChecklistMark("setup", item.id, "pending"))}
                    >
                      Restore
                    </Button>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
          {onOpenWizard ? (
            <div className="config-actions">
              <Button variant="secondary" data-testid="rerun-wizard" onClick={onOpenWizard}>
                Open the first-run wizard
              </Button>
            </div>
          ) : null}
        </section>
      ) : null}

      {secrets ? (
        <section
          className={`config-section owner-ops-secrets tone-${secrets.status}`}
          id="secrets-connections"
          data-testid="secrets-connections-card"
        >
          <h2>Secrets &amp; connections</h2>
          <p className="wizard-note" data-testid="secrets-key-line">
            {secrets.unreadable_fields?.length
              ? `${secrets.unreadable_fields.length} saved key${secrets.unreadable_fields.length === 1 ? "" : "s"} can't be read with the current secrets key. That usually means the key changed after a restore.`
              : secrets.key_source === "dedicated"
                ? "Saved keys read cleanly with your dedicated secrets key. Keep that key with your backups."
                : "Saved keys read cleanly. They're locked with a key derived from this server's session secret, so a restore needs that secret too. A dedicated PROJECTIONIST_SECRETS_KEY is safer."}
          </p>
          <ul className="owner-ops-list owner-ops-services">
            {(secrets.services || []).map((service: any) => {
              const copy = secretStateCopy(service.state);
              return (
                <li key={service.id} className={`owner-ops-row tone-${copy.tone}`} data-testid={`secrets-service-${service.id}`}>
                  <span className="owner-ops-row-title">{service.label}</span>
                  <span className={`owner-ops-chip tone-${copy.tone}`} data-testid={`secrets-service-state-${service.id}`}>
                    {copy.label}
                  </span>
                  <span className="owner-ops-row-detail">{formatLastProbe(service.last_tested_at)}</span>
                </li>
              );
            })}
          </ul>
          <div className="config-actions">
            <Link to="/admin/connections" className="btn-link" data-testid="secrets-open-connections">
              Open Connections to test
            </Link>
          </div>
        </section>
      ) : null}
    </>
  );
}
