import { useEffect, useState } from "react";
import { getPlayabilityReport, refreshPlayabilityReport } from "../../api/client";
import { detectBrowserPlaybackProfile } from "../../lib/enginePlayback";

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
type TitleRow = { rating_key?: string; title?: string; tier?: string; label?: string; reason?: string };
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
  profiles?: ProfileReport[];
};

function profileLabel(id: string) {
  return PROFILE_LABELS[id] || id;
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
    getPlayabilityReport()
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
      const next = await refreshPlayabilityReport(profile);
      setReport(next as PlayabilityReportBody);
    } catch (err) {
      setError((err as { message?: string })?.message || "Couldn’t refresh the playability report.");
    } finally {
      setBusy(false);
    }
  }

  const profiles = report?.profiles || [];
  const loading = report === null && !error;

  return (
    <div className="playability-report" data-testid="playability-report">
      <h4>Library playability</h4>
      <p className="field-help">
        Which tier would play each title: serve the file, remux, audio-only, captions that are not
        ready yet, picture captions, ask the media source to transcode, or not playable through the
        engine. Refresh walks the library with the cached probe. It does not transcode.
      </p>
      <button type="button" data-testid="playability-refresh" disabled={busy} onClick={() => void refresh()}>
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
      {!error && report && profiles.length === 0 ? (
        <p className="status status-secondary" data-testid="playability-empty">
          {report.message || "No playability report yet. Refresh to walk the library."}
        </p>
      ) : null}
      {profiles.map((profile) => {
        const id = String(profile.profile || "");
        const shares = profile.shares || {};
        const titles = profile.titles || [];
        return (
          <section key={id} className="playability-profile" data-testid={`playability-${id}`}>
            <h5>{profileLabel(id)}</h5>
            <p className="field-help">{profile.title_count || 0} titles</p>
            <ul className="playability-shares">
              {TIER_ORDER.map((tier) => {
                const share = shares[tier];
                if (!share) return null;
                const count = Number(share.count || 0);
                const rows = titles.filter((row) => row.tier === tier);
                return (
                  <li key={tier}>
                    {count > 0 && rows.length ? (
                      <details>
                        <summary>
                          {share.label || tier}: {count} of {profile.title_count || titles.length}
                        </summary>
                        <ul className="playability-titles">
                          {rows.map((row) => (
                            <li key={row.rating_key} data-testid={`playability-title-${row.rating_key}`}>
                              <strong>{row.title || row.rating_key}</strong>
                              <span className="field-help">{row.reason}</span>
                            </li>
                          ))}
                        </ul>
                      </details>
                    ) : (
                      <span>
                        {share.label || tier}: {count} of {profile.title_count || 0}
                      </span>
                    )}
                  </li>
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
