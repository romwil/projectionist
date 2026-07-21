import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getLibraryKnowledgeCoverage, listMediaIssues } from "../api/client";
import { buildHealthHeroTiles } from "../lib/ownerHealth.js";

/**
 * At-a-glance owner "Library health" hero. Reuses the dashboard's existing
 * health/streak fetches (passed as props) and adds only knowledge coverage +
 * open-issue count so it doesn't duplicate data fetching.
 */
export default function OwnerHealthHero({ health, streak }) {
  const [coverage, setCoverage] = useState(null);
  const [openIssues, setOpenIssues] = useState(null);

  useEffect(() => {
    let cancelled = false;
    getLibraryKnowledgeCoverage()
      .then((data) => !cancelled && setCoverage(data))
      .catch(() => !cancelled && setCoverage(null));
    listMediaIssues({ status: "open" })
      .then((data) => {
        if (cancelled) return;
        const count = typeof data?.count === "number" ? data.count : (data?.items || []).length;
        setOpenIssues(count);
      })
      .catch(() => !cancelled && setOpenIssues(null));
    return () => {
      cancelled = true;
    };
  }, []);

  const streakCount =
    streak?.streak ?? streak?.session_count_30d ?? streak?.count ?? streak?.sessions ?? 0;

  const tiles = buildHealthHeroTiles({
    health,
    coverage,
    streak: streakCount,
    openIssues,
  });

  return (
    <section className="owner-health-hero" data-testid="owner-health-hero">
      <div className="owner-health-hero-head">
        <div>
          <p className="eyebrow">At a glance</p>
          <h2 className="dash-title">Library health</h2>
        </div>
      </div>
      <div className="owner-health-grid">
        {tiles.map((tile) => (
          <Link
            key={tile.id}
            to={tile.to}
            className={`owner-health-tile tone-${tile.tone}`}
            data-testid={`owner-health-tile-${tile.id}`}
          >
            <span className="owner-health-tile-value">{tile.value}</span>
            <span className="owner-health-tile-label">{tile.label}</span>
            <span className="owner-health-tile-detail">{tile.detail}</span>
          </Link>
        ))}
      </div>
    </section>
  );
}
