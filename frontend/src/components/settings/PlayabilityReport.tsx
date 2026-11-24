import { useEffect, useRef, useState } from "react";
import {
  getPlayabilityReport,
  getPlayabilityTitles,
  markQualityTargetReplaced,
  queueQualityCopy,
  refreshPlayabilityReport,
} from "../../api/client";
import { detectBrowserPlaybackProfile } from "../../lib/enginePlayback";
import {
  gpuDecisionLine,
  playabilityNotice,
  sourceBreakdownLine,
} from "../../lib/playabilityNotice";

const TIER_ORDER = [
  "direct",
  "remux",
  "try",
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
  source_breakdown?: {
    video_transcode?: number;
    codec?: number;
    codecs?: Record<string, number>;
    level?: number | null;
    bit_depth?: number | null;
    resolution?: number;
    hdr?: number | null;
  };
};
type AboveTargetRow = {
  rating_key?: string;
  title?: string;
  resolution?: string;
  codec?: string;
  file_size?: number;
  path?: string;
};
type AboveTarget = {
  title?: string;
  count?: number;
  ceiling?: string;
  titles?: AboveTargetRow[];
};
type PlayabilityReportBody = {
  message?: string;
  title_count?: number;
  complete?: boolean;
  running?: boolean;
  planned_from_plex?: number;
  confirmed_by_ffprobe?: number;
  profiles?: ProfileReport[];
  gpu?: { safari?: number | null; apple_tv?: number | null };
  quality_ceiling?: string;
  above_target?: AboveTarget;
};

const CODEC_LABELS: Record<string, string> = {
  hevc: "HEVC",
  h264: "H.264",
  av1: "AV1",
  vp9: "VP9",
  vc1: "VC-1",
};

function codecLabel(name: string) {
  const key = String(name || "")
    .trim()
    .toLowerCase();
  return CODEC_LABELS[key] || name;
}

function formatBytes(bytes: number): string {
  const value = Number(bytes) || 0;
  const gib = value / (1024 * 1024 * 1024);
  if (Math.abs(gib) >= 0.1) return `${gib.toFixed(1)} GiB`;
  const mib = value / (1024 * 1024);
  if (Math.abs(mib) >= 0.1) return `${Math.round(mib)} MiB`;
  return `${value} B`;
}

function targetSummary(count: number): string {
  if (count === 1) return "1 title is above your quality target.";
  return `${count} titles are above your quality target.`;
}

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
export default function PlayabilityReport({ listRevision = 0 }: { listRevision?: number }) {
  const [report, setReport] = useState<PlayabilityReportBody | null>(null);
  const [error, setError] = useState("");
  const [actionError, setActionError] = useState("");
  const [busy, setBusy] = useState(false);
  const [busyKey, setBusyKey] = useState("");

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
  }, [listRevision]);

  async function runTargetAction(ratingKey: string, action: "copy" | "replaced") {
    setBusyKey(`${action}:${ratingKey}`);
    setActionError("");
    try {
      if (action === "copy") await queueQualityCopy(ratingKey);
      else await markQualityTargetReplaced(ratingKey);
      const next = await getPlayabilityReport({ view: "progress" });
      setReport(next as PlayabilityReportBody);
    } catch (err) {
      setActionError(
        (err as { message?: string })?.message ||
          (action === "copy" ? "Couldn’t queue that copy." : "Couldn’t mark that title."),
      );
    } finally {
      setBusyKey("");
    }
  }

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
  const gpuLine = gpuDecisionLine(report?.gpu);
  const above = report?.above_target;
  const aboveCount = Number(above?.count || 0);
  const aboveRows = Array.isArray(above?.titles) ? above.titles : [];

  return (
    <div className="playability-report" data-testid="playability-report">
      <h4>Library playability</h4>
      <p className="field-help">
        Which tier would play each title: serve the file, remux, try the remux, audio-only, captions
        that are not ready yet, picture captions, ask the media source to transcode, or not playable
        through the engine. Refresh plans from the stream metadata Plex already has, then confirms
        with ffprobe in the background. It does not start on its own, and it does not transcode.
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
      {gpuLine ? (
        <p className="field-help" data-testid="playability-gpu">
          {gpuLine}
        </p>
      ) : null}
      {report ? (
        <section data-testid="above-quality-target">
          <h4>Above your quality target</h4>
          <p className="field-help" data-testid="above-quality-target-count">
            {targetSummary(aboveCount)}
          </p>
          {actionError ? (
            <p className="status status-error" data-testid="above-quality-target-error">
              {actionError}
            </p>
          ) : null}
          {aboveRows.length ? (
            <ul className="playability-titles">
              {aboveRows.map((row) => {
                const key = String(row.rating_key || "");
                const rowBusy = busyKey.endsWith(`:${key}`);
                return (
                  <li key={key} data-testid={`above-target-${key}`}>
                    <strong>{row.title || key}</strong>
                    <span className="field-help">{row.resolution}</span>
                    <span className="field-help">{codecLabel(String(row.codec || ""))}</span>
                    <span className="field-help">{formatBytes(Number(row.file_size || 0))}</span>
                    <span className="field-help">{row.path}</span>
                    <button
                      type="button"
                      data-testid={`quality-copy-${key}`}
                      disabled={rowBusy}
                      onClick={() => void runTargetAction(key, "copy")}
                    >
                      Make a 1080p copy
                    </button>
                    <button
                      type="button"
                      data-testid={`quality-replaced-${key}`}
                      disabled={rowBusy}
                      onClick={() => void runTargetAction(key, "replaced")}
                    >
                      Mark as replaced
                    </button>
                  </li>
                );
              })}
            </ul>
          ) : null}
        </section>
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
            {sourceBreakdownLine(profile.source_breakdown) ? (
              <p className="field-help" data-testid={`playability-source-${id}`}>
                {sourceBreakdownLine(profile.source_breakdown)}
              </p>
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
