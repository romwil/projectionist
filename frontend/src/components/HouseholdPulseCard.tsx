import { useEffect, useState } from "react";
import { getHouseholdPulse } from "../api/client";
import {
  guardrailStatusCopy,
  guardrailValueText,
  sparklineLabel,
  sparklinePoints,
  weekOverWeek,
  type HouseholdPulse,
} from "../lib/householdPulse";

/** Admin Overview: north-star and guardrails from on-box events, household totals only. */
export default function HouseholdPulseCard() {
  const [pulse, setPulse] = useState<HouseholdPulse | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    getHouseholdPulse()
      .then((next) => {
        if (!cancelled) setPulse(next as unknown as HouseholdPulse);
      })
      .catch((err: { message?: string }) => {
        if (!cancelled) setError(err?.message || "Couldn't load the household pulse.");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const star = pulse?.north_star;
  const trend = star ? weekOverWeek(star.this_week, star.last_week) : null;

  return (
    <section
      className="config-section household-pulse"
      data-testid="household-pulse"
      aria-labelledby="household-pulse-title"
    >
      <h2 id="household-pulse-title">Household pulse</h2>
      <p className="wizard-note">
        Weekly totals from this server only. Nothing is sent anywhere, and no one member is singled out.
      </p>
      {error ? (
        <p className="wizard-note" role="status">
          {error}
        </p>
      ) : !pulse || !star || !trend ? (
        <p className="wizard-note">Counting this week…</p>
      ) : (
        <>
          {pulse.telemetry_enabled === false ? (
            <p className="wizard-note" data-testid="household-pulse-off">
              Activity counts are turned off on this server, so these numbers stop growing.
            </p>
          ) : null}
          <div className="household-pulse-star">
            <span className="household-pulse-value" data-testid="household-pulse-north-star">
              {star.this_week}
            </span>
            <div className="household-pulse-star-text">
              <span className="owner-ops-row-title">{star.label} this week</span>
              <span className={`owner-ops-row-detail trend-${trend.direction}`}>{trend.text}</span>
            </div>
            <svg
              className="household-pulse-spark"
              width="96"
              height="24"
              viewBox="0 0 96 24"
              role="img"
              aria-label={sparklineLabel(star.weekly)}
            >
              <polyline fill="none" stroke="currentColor" strokeWidth="2" points={sparklinePoints(star.weekly)} />
            </svg>
          </div>
          <ul className="owner-ops-list" data-testid="household-pulse-guardrails">
            {pulse.guardrails.map((guard) => (
              <li key={guard.id} className={`owner-ops-row pulse-${guard.status}`}>
                <div className="owner-ops-row-text">
                  <span className="owner-ops-row-title">{guard.label}</span>
                  <span className="owner-ops-row-detail">{guardrailValueText(guard)}</span>
                </div>
                <span className="owner-ops-chip" data-testid={`household-pulse-${guard.id}`}>
                  {guardrailStatusCopy(guard.status)}
                </span>
              </li>
            ))}
          </ul>
          {pulse.box ? (
            <p className="wizard-note" data-testid="household-pulse-box">
              Right now: {Number(pulse.box.write_queue_depth) || 0} database writes waiting · slowest page requests{" "}
              {pulse.box.api_p95_ms != null ? `${Math.round(Number(pulse.box.api_p95_ms))} ms` : "not measured yet"}{" "}
              (p95 since restart)
            </p>
          ) : null}
        </>
      )}
    </section>
  );
}
