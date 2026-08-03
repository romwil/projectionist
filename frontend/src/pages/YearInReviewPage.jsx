import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getAuthMe, getYearInReview } from "../api/client";
import { useAuthGate } from "../components/UserMenu";
import {
  chapterDurationMs,
  nextChapterIndex,
  prevChapterIndex,
  shareCardText,
  shouldAutoAdvance,
} from "../lib/yearInReview.js";

function usePrefersReducedMotion() {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return undefined;
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReduced(Boolean(mq.matches));
    update();
    mq.addEventListener?.("change", update);
    return () => mq.removeEventListener?.("change", update);
  }, []);
  return reduced;
}

export default function YearInReviewPage() {
  const { year: yearParam } = useParams();
  const year = Number(yearParam);
  const { authReady, role } = useAuthGate();
  const [user, setUser] = useState(null);
  const [reel, setReel] = useState(null);
  const [status, setStatus] = useState(null);
  const [error, setError] = useState(null);
  const [index, setIndex] = useState(0);
  const [paused, setPaused] = useState(false);
  const [shareNote, setShareNote] = useState(null);
  const cardRef = useRef(null);
  const prefersReducedMotion = usePrefersReducedMotion();

  useEffect(() => {
    if (!authReady) return undefined;
    let cancelled = false;
    getAuthMe()
      .then((payload) => {
        if (!cancelled) setUser(payload?.user || null);
      })
      .catch(() => {
        if (!cancelled) setUser(null);
      });
    return () => {
      cancelled = true;
    };
  }, [authReady]);

  useEffect(() => {
    if (!authReady) return undefined;
    const effectiveRole = user?.role || role;
    if (effectiveRole === "guest") {
      setError("Guests don’t get a Year in Review — ask the owner for a member invite.");
      return undefined;
    }
    if (!Number.isFinite(year) || year < 2000) {
      setError("That year doesn’t look right.");
      return undefined;
    }
    let cancelled = false;
    getYearInReview(year)
      .then((payload) => {
        if (cancelled) return;
        setReel(payload?.reel || null);
        setStatus(payload?.status || null);
        setIndex(0);
        setError(null);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err?.message || "Year in Review isn’t ready yet.");
      });
    return () => {
      cancelled = true;
    };
  }, [authReady, user, role, year]);

  const chapters = Array.isArray(reel?.chapters) ? reel.chapters : [];
  const chapter = chapters[index] || null;

  useEffect(() => {
    if (!chapter || !shouldAutoAdvance({ paused, prefersReducedMotion })) return undefined;
    const ms = chapterDurationMs(chapters, index);
    const timer = window.setTimeout(() => {
      setIndex((current) => nextChapterIndex(current, chapters.length));
    }, ms);
    return () => window.clearTimeout(timer);
  }, [chapter, chapters, index, paused, prefersReducedMotion]);

  const handleShare = useCallback(async () => {
    if (!chapter?.shareable) return;
    const text = shareCardText(chapter, year);
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
        setShareNote("Copied this beat to the clipboard.");
      } else {
        setShareNote(text);
      }
    } catch {
      setShareNote("Couldn’t copy — try selecting the text.");
    }
  }, [chapter, year]);

  if (!authReady) {
    return (
      <main className="yir-page">
        <p className="muted">Loading…</p>
      </main>
    );
  }

  if (error) {
    return (
      <main className="yir-page">
        <div className="yir-empty">
          <h1 className="yir-brand">Projectionist</h1>
          <p>{error}</p>
          <Link to="/chat">Back to chat</Link>
        </div>
      </main>
    );
  }

  if (!reel || !chapter) {
    return (
      <main className="yir-page">
        <div className="yir-empty">
          <h1 className="yir-brand">Projectionist</h1>
          <p>
            Your reel isn’t ready yet. Opt in under Settings → Notifications, then ask the owner to
            generate.
          </p>
          <Link to="/settings/notifications">Notification settings</Link>
        </div>
      </main>
    );
  }

  return (
    <main className={`yir-page ${prefersReducedMotion ? "yir-reduced" : ""}`} data-testid="yir-page">
      <header className="yir-chrome">
        <Link to="/chat" className="yir-back">
          ← Chat
        </Link>
        <p className="yir-brand">Projectionist · {year}</p>
        <button type="button" className="yir-pause" onClick={() => setPaused((p) => !p)}>
          {paused ? "Play" : "Pause"}
        </button>
      </header>

      <section className="yir-stage" aria-live="polite">
        <article className="yir-card" ref={cardRef} data-kind={chapter.kind} key={chapter.id || index}>
          <p className="yir-kicker">{status === "tease" ? "Early peek" : "Year in Review"}</p>
          <h1 className="yir-title">{chapter.title}</h1>
          <p className="yir-body">{chapter.body}</p>
          {chapter.stat_lines?.length > 0 && (
            <ul className="yir-stats">
              {chapter.stat_lines.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          )}
          {chapter.posters?.length > 0 && (
            <div className="yir-posters" aria-hidden="true">
              {chapter.posters.slice(0, 4).map((poster) => (
                <div key={`${poster.title}-${poster.poster_url || ""}`} className="yir-poster">
                  {poster.poster_url ? <img src={poster.poster_url} alt="" /> : <span>{poster.title}</span>}
                </div>
              ))}
            </div>
          )}
        </article>
      </section>

      <nav className="yir-controls" aria-label="Reel controls">
        <button
          type="button"
          onClick={() => setIndex((i) => prevChapterIndex(i, chapters.length))}
          disabled={index <= 0}
        >
          Back
        </button>
        <div className="yir-dots" role="tablist" aria-label="Chapters">
          {chapters.map((ch, i) => (
            <button
              key={ch.id || i}
              type="button"
              className={`yir-dot ${i === index ? "is-active" : ""}`}
              aria-label={`Chapter ${i + 1}`}
              aria-current={i === index ? "true" : undefined}
              onClick={() => setIndex(i)}
            />
          ))}
        </div>
        <button
          type="button"
          onClick={() => setIndex((i) => nextChapterIndex(i, chapters.length))}
          disabled={index >= chapters.length - 1}
        >
          Next
        </button>
      </nav>

      {chapter.shareable && (
        <div className="yir-share">
          <button type="button" onClick={handleShare}>
            Copy this beat
          </button>
          {shareNote && <p className="muted">{shareNote}</p>}
        </div>
      )}

      {reel.honesty?.footnote && <p className="yir-footnote muted">{reel.honesty.footnote}</p>}
    </main>
  );
}
