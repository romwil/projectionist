import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getKinshipMissList } from "../api/client";
import { formatKinshipMissHit, kinshipMissWhyLabel } from "../lib/kinshipMiss.js";
import { titleDetailPath } from "../lib/titleLinks.js";
import SectionHelp from "./SectionHelp.jsx";

/**
 * Human list of titles someone opened to an empty More Like This / Related /
 * bridge shelf. Demand, not a grade — no auto-repair.
 */
export default function KinshipMissList() {
  const [payload, setPayload] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getKinshipMissList({ limit: 50 })
      .then((data) => {
        if (cancelled) return;
        setPayload(data);
        setError("");
      })
      .catch((err) => {
        if (cancelled) return;
        setPayload(null);
        setError(err.message || "Could not load empty-shelf demand.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const items = Array.isArray(payload?.items) ? payload.items : [];

  return (
    <section
      className="dash-panel kinship-miss-panel"
      data-testid="kinship-miss-list"
      aria-label="Empty-shelf demand"
    >
      <div className="grooming-panel-title-row">
        <h3 className="dash-panel-title">Empty More Like This</h3>
        <SectionHelp label="About empty-shelf demand" testId="kinship-miss-section-help">
          <p>
            These are titles someone opened when More Like This, Related titles, or a
            recommendation bridge had no named peers. Hit counts are demand, not a
            grade. Idle catch-up prefers them — nothing is auto-repaired.
          </p>
        </SectionHelp>
      </div>
      <p className="status status-secondary kinship-miss-blurb">
        {payload?.note ||
          "Demand, not a grade. Idle catch-up prefers these titles. Nothing is auto-repaired."}
      </p>
      {loading ? (
        <div className="dash-skeleton" aria-label="Loading empty-shelf demand">
          <div className="dash-skeleton-bar" />
          <div className="dash-skeleton-bar short" />
        </div>
      ) : error ? (
        <p className="dash-panel-error">{error}</p>
      ) : items.length ? (
        <ul className="kinship-miss-items">
          {items.map((item) => {
            const href = item.href || titleDetailPath(item);
            const body = (
              <>
                {item.poster_url ? (
                  <img
                    className="kinship-miss-poster"
                    src={item.poster_url}
                    alt=""
                    width="40"
                    height="60"
                  />
                ) : (
                  <span className="kinship-miss-poster kinship-miss-poster-empty" />
                )}
                <span className="kinship-miss-copy">
                  <span className="kinship-miss-title">
                    {item.title}
                    {item.year ? ` (${item.year})` : ""}
                  </span>
                  <span className="kinship-miss-meta">
                    {kinshipMissWhyLabel(item.why_queued || item.reason)} ·{" "}
                    {formatKinshipMissHit(item.hit_count)}
                    {item.last_miss ? ` · last ${item.last_miss}` : ""}
                  </span>
                </span>
              </>
            );
            return (
              <li key={item.item_id} className="kinship-miss-item">
                {href ? (
                  <Link to={href} className="kinship-miss-link">
                    {body}
                  </Link>
                ) : (
                  <div className="kinship-miss-link">{body}</div>
                )}
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="dash-empty">No empty-shelf demand queued.</p>
      )}
    </section>
  );
}
