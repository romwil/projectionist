import { useEffect, useRef, useState } from "react";
import {
  getPlayabilityReport,
  getPlayabilityTitles,
  refreshPlayabilityReport,
} from "../../api/client";
import { detectBrowserPlaybackProfile } from "../../lib/enginePlayback";
import { playabilityNotice } from "../../lib/playabilityNotice";

const TIER_ORDER = [
  "direct",
  "remux",
  "audio",
  "captions-pending",
  "needs-ocr",
  "source-transcode",
  "not-playable",
];

const PROFILE_LABELS: Record<string, string> = {
  "apple-tv-4k-3": "Apple TV",
  safari: "Safari",
  chrome: "Chrome",
  web: "This browser",
};

type Share = { count?: number; share?: number; label?: string };
type TitleRow = {
  rating_key?: string;
  title?: string;
  tier?: string;
  label?: string;
  reason?: string;
};
type ProfileReport = {
  profile?: string;
  title_count?: number;
  shares?: Record<string, Share>;
  top_reasons?: { reason?: string; count?: number }[];
  titles?: TitleRow[];
  hardware?: string;
};
type PlayabilityReportBody = {
  message?: string;
  title_count?: number;
  complete?: boolean;
  running?: boolean;
  planned_from_plex?: number;
  confirmed_by_ffprobe?: number;
  profiles?: ProfileReport[];
};

function profileLabel(id: string) {
  return PROFILE_LABELS[id] || id;
}

function TierShare({
  profileId,
  tier,
  share,
  titleCount,
}: {
  profileId: string;
  tier: string;
  share: Share;
  titleCount: number;
}) {
  const count = Number(share.count || 0);
  const detailsRef = useRef<HTMLDetailsElement>(null);
  const [open, setOpen] = useState(false);
  const [rows, setRows] = useState<TitleRow[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const node = detailsRef.current;
    if (!node) return undefined;
    const onToggle = () => {
      const next = node.open;
      setOpen(next);
      if (next) setLoading(true);
    };
    node.addEventListener("toggle", onToggle);
    return () => node.removeEventListener("toggle", onToggle);
  }, [count]);

  useEffect(() => {
    if (!open) return undefined;
    let live = true;
    getPlayabilityTitles(profileId, tier, 0)
      .then((payload) => {
        if (!live) return;
        const body = payload as { titles?: TitleRow[]; total?: number };
        setRows(Array.isArray(body.titles) ? body.titles : []);
        setTotal(Number(body.total || 0));
      })
      .catch(() => {
        if (!live) return;
        setRows([]);
        setTotal(0);
      })
      .finally(() => {
        if (live) setLoading(false);
      });
    return () => {
      live = false;
    };
  }, [open, profileId, tier]);

  async function showMore() {
    try {
      const payload = await getPlayabilityTitles(profileId, tier, rows.length);
      const body = payload as { titles?: TitleRow[]; total?: number };
      const next = Array.isArray(body.titles) ? body.titles : [];
      setRows((current) => current.concat(next));
      setTotal(Number(body.total || 0));
    } catch {
      // The rows already on screen stay. The next open tries again.
    }
  }

  if (count <= 0) {
    return (
      <li>
        <span>
          {share.label || tier}: 0 of {titleCount}
        </span>
      </li>
    );
  }

  return (
    <li>
      <details ref={detailsRef}>
        <summary>
          {share.label || tier}: {count} of {titleCount}
        </summary>
        {loading && rows.length === 0 ? (
          <p className="field-help">Loading titles…</p>
        ) : (
          <ul className="playability-titles">
            {rows.map((row) => (
              <li key={row.rating_key} data-testid={`playability-title-${row.rating_key}`}>
                <strong>{row.title || row.rating_key}</strong>
                <span className="field-help">{row.reason}</span>
              </li>
            ))}
          </ul>
        )}
        {rows.length > 0 && rows.length < total ? (
          <button type="button" onClick={() => void showMore()}>
            Show more
          </button>
        ) : null}
      </details>
    </li>
  );
}

/**
 * Owner view of the library playability report. The server dry-runs the
 * planner. This panel does not start a transcode.
 */
export default function PlayabilityReport() {
  const [report, setReport] = useState<PlayabilityReportBody | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let live = true;
    getPlayabilityReport({ view: "progress" })
      .then((payload) => {
        if (live) setReport(payload as PlayabilityReportBody);
      })
      .catch((err: { message?: string }) => {
        if (live) setError(err?.message || "Couldn’t load the playability report.");
      });
    return () => {
      live = false;
    };
  }, []);

  useEffect(() => {
    if (!report?.running) return undefined;
    let live = true;
    const timer = window.setInterval(() => {
      getPlayabilityReport({ view: "progress" })
        .then((payload) => {
          if (live) setReport(payload as PlayabilityReportBody);
        })
        .catch(() => {
          // The next tick tries again. Opening this page did not start the walk.
        });
    }, 3000);
    return () => {
      live = false;
      window.clearInterval(timer);
    };
  }, [report?.running]);

  async function refresh() {
    setBusy(true);
    setError("");
    try {
      let profile = null;
      try {
        profile = await detectBrowserPlaybackProfile();
      } catch {
        profile = null;
      }
      await refreshPlayabilityReport(profile);
      const next = await getPlayabilityReport({ view: "progress" });
      setReport(next as PlayabilityReportBody);
    } catch (err) {
      setError(
        (err as { message?: string })?.message || "Couldn’t refresh the playability report.",
      );
    } finally {
      setBusy(false);
    }
  }

  const profiles = report?.profiles || [];
  const loading = report === null && !error;
  const notice = error ? "" : playabilityNotice(report);

  return (
    <div className="playability-report" data-testid="playability-report">
      <h4>Library playability</h4>
      <p className="field-help">
        Which tier would play each title: serve the file, remux, audio-only, captions that are not
        ready yet, picture captions, ask the media source to transcode, or not playable through the
        engine. Refresh plans from the stream metadata Plex already has, then confirms with ffprobe
        in the background. It does not start on its own, and it does not transcode.
      </p>
      <button
        type="button"
        data-testid="playability-refresh"
        disabled={busy}
        onClick={() => void refresh()}
      >
        {busy ? "Checking the library…" : "Refresh report"}
      </button>
      {loading ? (
        <p className="status status-secondary" data-testid="playability-loading">
          Loading the playability report…
        </p>
      ) : null}
      {error ? (
        <p className="status status-error" data-testid="playability-error">
          {error}
        </p>
      ) : null}
      {report && (report.running || report.planned_from_plex || report.confirmed_by_ffprobe) ? (
        <p className="field-help" data-testid="playability-progress">
          Planned from Plex metadata: {report.planned_from_plex || 0} titles. Confirmed by ffprobe:{" "}
          {report.confirmed_by_ffprobe || 0}.{report.running ? " Still running." : ""}
        </p>
      ) : null}
      {notice && profiles.length === 0 ? (
        <p className="status status-secondary" data-testid="playability-empty">
          {notice}
        </p>
      ) : null}
      {notice && profiles.length > 0 ? (
        <p className="status status-secondary" data-testid="playability-stopped">
          {notice}
        </p>
      ) : null}
      {profiles.map((profile) => {
        const id = String(profile.profile || "");
        const shares = profile.shares || {};
        const titleCount = Number(profile.title_count || 0);
        return (
          <section key={id} className="playability-profile" data-testid={`playability-${id}`}>
            <h5>{profileLabel(id)}</h5>
            <p className="field-help">{titleCount} titles</p>
            <ul className="playability-shares">
              {TIER_ORDER.map((tier) => {
                const share = shares[tier];
                if (!share) return null;
                return (
                  <TierShare
                    key={tier}
                    profileId={id}
                    tier={tier}
                    share={share}
                    titleCount={titleCount}
                  />
                );
              })}
            </ul>
            {profile.top_reasons?.length ? (
              <ul className="playability-reasons">
                {profile.top_reasons.map((row) => (
                  <li key={row.reason}>
                    {row.reason}
                    {row.count ? ` · ${row.count}` : ""}
                  </li>
                ))}
              </ul>
            ) : null}
            {profile.hardware ? (
              <p className="field-help" data-testid={`playability-hardware-${id}`}>
                {profile.hardware}
              </p>
            ) : null}
          </section>
        );
      })}
    </div>
  );
}
