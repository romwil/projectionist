import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getLibraryKnowledgeCoverage, getPurgeCandidates, listMediaIssues } from "../api/client";
import { buildHealthHeroTiles, buildLibraryHealthStory } from "../lib/ownerHealth.js";

type MediaIssuesPayload = {
  count?: number;
  items?: unknown[];
};

type PurgePayload = unknown[] | { candidates?: unknown[]; items?: unknown[] };

type OwnerHealthHeroProps = {
  health?: unknown;
};

/**
 * At-a-glance owner health: one Monday pass story plus tiles for Named kinship,
 * issues, purge pressure, and Scheduled Tasks catch-up.
 */
export default function OwnerHealthHero({ health }: OwnerHealthHeroProps) {
  const [coverage, setCoverage] = useState<unknown | null>(null);
  const [openIssues, setOpenIssues] = useState<number | null>(null);
  const [purgeCount, setPurgeCount] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    getLibraryKnowledgeCoverage()
      .then((data: unknown) => !cancelled && setCoverage(data))
      .catch(() => !cancelled && setCoverage(null));
    listMediaIssues({ status: "open" })
      .then((data: MediaIssuesPayload) => {
        if (cancelled) return;
        const count = typeof data?.count === "number" ? data.count : (data?.items || []).length;
        setOpenIssues(count);
      })
      .catch(() => !cancelled && setOpenIssues(null));
    getPurgeCandidates()
      .then((data: PurgePayload) => {
        if (cancelled) return;
        const list = Array.isArray(data) ? data : data?.candidates ?? data?.items ?? [];
        setPurgeCount(Array.isArray(list) ? list.length : null);
      })
      .catch(() => !cancelled && setPurgeCount(null));
    return () => {
      cancelled = true;
    };
  }, []);

  const story = buildLibraryHealthStory({
    health,
    coverage,
    openIssues,
    purgeCount,
  });
  const tiles = buildHealthHeroTiles({ health: health as any, coverage: coverage as any,
    openIssues,
    purgeCount,
  });

  return (
    <section className="owner-health-hero" data-testid="owner-health-hero" aria-label="Monday pass">
      {story ? (
        <div className="owner-health-hero-head" data-testid="owner-health-story">
          <div>
            <h2 className="owner-health-story-headline">{story.headline}</h2>
            <p className={`owner-health-story-body tone-${story.tone}`}>{story.body}</p>
          </div>
          <Link to="/admin/scheduled-tasks" className="app-topbar-link" data-testid="owner-health-catchup">
            Scheduled Tasks catch-up
          </Link>
        </div>
      ) : null}
      <div className="owner-health-grid">
        {tiles.map((tile: { id: string; to: string; tone: string; value: React.ReactNode; label: React.ReactNode; detail: React.ReactNode }) => (
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
